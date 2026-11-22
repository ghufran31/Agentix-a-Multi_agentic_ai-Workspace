from datetime import date

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from projects.models import Project
from companies.models import CompanyUser
from django.core.exceptions import PermissionDenied
from workforce.models import Employee
from orchestrator.ml_engine.ranking import rank_project_candidates
from orchestrator.ml_engine.feature_extractor import FeatureError, parse_terms
from orchestrator.agents.matching.schemas import MatchingRequest, MatchingResponse

BATCH_SIZE = 100

class ProjectInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: int = Field(gt=0)

def context_tools(context):
    def authorize():
        if not context or not context.user.is_authenticated or not CompanyUser.objects.filter(
            user_id=context.user.pk, user__is_active=True, company_id=context.company.pk
        ).exists():
            raise PermissionDenied('Active company membership required.')

    def get_project_matching_context(project_id):
        authorize()
        project = Project.objects.filter(id=project_id, company=context.company).prefetch_related('requirements').first()
        if not project:
            return failure('Project not found in your company.', 'not_found')
        requirements = list(project.requirements.order_by('id').values('requirement', 'required_skills', 'required_roles', 'priority', 'deadline'))
        if len(requirements) != project.requirements.count():
            return {'success': False, 'error': 'Project requirements are incomplete.'}
        return {'success': True, 'project': {'id': project.id, 'name': project.name, 'priority': project.priority, 'deadline': project.deadline.isoformat() if project.deadline else None, 'requirements': requirements}}

    def rank_project(project_id, top_n=5, available_only=False, role_filter=None, skill_filter=None):
        authorize()
        project = Project.objects.filter(id=project_id, company=context.company).prefetch_related('requirements').first()
        if not project:
            return failure('Project not found in your company.', 'not_found')
        try:
            requirements = list(project.requirements.all())
            skills = set().union(*(parse_terms(row.required_skills) for row in requirements))
            roles = set().union(*(parse_terms(row.required_roles) for row in requirements))
        except FeatureError:
            return failure('Project skills or roles are malformed.')
        if not skills or not roles or not project.deadline:
            return failure('Project requires explicit skills, roles, and a deadline.')
        employees_qs = Employee.objects.filter(department__company=context.company).select_related('department', 'ai_profile').prefetch_related('skill_assignments__skill').order_by('id')
        total = employees_qs.count()
        requested = {value.strip().casefold() for value in (skill_filter or [])}
        ranked, exclusions = [], []
        seen = cursor = eligible_count = 0
        evaluation_date = date.today()
        while batch := list(employees_qs.filter(pk__gt=cursor)[:BATCH_SIZE]):
            cursor = batch[-1].pk
            seen += len(batch)
            selected = []
            for employee in batch:
                profile = getattr(employee, 'ai_profile', None)
                owned = {item.skill.name.strip().casefold()
                         for item in employee.skill_assignments.all()
                         if item.skill.company_id == project.company_id}
                if (available_only and profile and profile.availability_status != 'available'
                    or role_filter and profile and role_filter.casefold() not in (profile.job_title or '').casefold()
                    or not requested.issubset(owned)):
                    continue
                selected.append(employee)
            batch_ranked, rows = rank_project_candidates(project, selected, evaluation_date)
            eligible_count += len(batch_ranked)
            ranked.extend(batch_ranked)
            ranked.sort(key=lambda row: (-row['positive_probability'], row['employee_id']))
            del ranked[top_n:]
            for row in rows:
                reasons = row['rejection_reasons'] + row['feature_errors']
                if reasons and len(exclusions) < 25:
                    exclusions.append({'employee_id': row['employee_id'], 'reasons': reasons})
        if seen != total:
            return failure('Candidate retrieval count changed. Retry matching.')
        result = []
        for rank, row in enumerate(ranked[:top_n], 1):
            result.append(dict(employee_id=row['employee_id'], employee_name=f"Employee {row['employee_id']}",
                               rank=rank, model_score=row['positive_probability'],
                               matched_skills=row['matched_skills'], missing_skills=row['missing_skills'],
                               availability_status=row['features']['availability_status'],
                               explanation=(
                                   f"Required-skill overlap: {row['features']['skill_match_ratio']:.1%}. "
                                   f"Exact role match: {'yes' if row['features']['role_match'] else 'no'}."
                               )))
        return MatchingResponse(success=True, answer=(
            f'Ranked {len(result)} of {eligible_count} scorable candidates.'
            if result else 'No scorable candidates met the matching criteria.'
        ), candidates=result, exclusions=exclusions, metadata=dict(
            project_id=project_id, candidate_count=total, eligible_count=eligible_count,
            ranked_count=len(result), complete=True,
            model_artifact='agentix_preprocessor.joblib + agentix_xgboost_native.json',
            score_semantics='Positive-class score from synthetic training labels. Uncalibrated.',
        )).model_dump(mode='json')

    def failure(message, code=None):
        return MatchingResponse(success=False, answer=message, error=code or message).model_dump(mode='json')

    return [
        StructuredTool.from_function(get_project_matching_context, name='get_project_matching_context', description='Get authorized company-scoped project requirements.', args_schema=ProjectInput),
        StructuredTool.from_function(rank_project, name='rank_project_employees', description='Retrieve all same-company employees, apply existing eligibility/features/XGBoost ranking, and return a bounded candidate summary.', args_schema=MatchingRequest),
    ]
