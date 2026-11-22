from django.core.exceptions import PermissionDenied
from django.db import transaction
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from agents.models import AIAgent
from projects.models import Project
from recommendations.models import Recommendation
from workforce.models import Employee

from .base import PaginationInput, decimal_value, failure, success


class RecommendationCreateInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: int = Field(gt=0)
    employee_id: int | None = Field(default=None, gt=0)
    ai_agent_id: int | None = Field(default=None, gt=0)
    recommended_role: str | None = Field(default=None, max_length=150)
    score: float = Field(ge=0)
    rank: int = Field(ge=1)
    reason: str | None = None
    status: str = Field(default='pending', max_length=50)


class RecommendationIdInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    recommendation_id: int = Field(gt=0)


class RecommendationListInput(PaginationInput):
    project_id: int | None = Field(default=None, gt=0)


def recommendation_tools(context):
    def create_recommendation(project_id, employee_id=None, ai_agent_id=None,
                              recommended_role=None, score=0, rank=1,
                              reason=None, status='pending'):
        try:
            context.require_write()
        except PermissionDenied as exc:
            return failure('recommendation.create', str(exc))
        if (employee_id is None) == (ai_agent_id is None):
            return failure('recommendation.create', 'Exactly one of employee_id or ai_agent_id is required.')
        project = Project.objects.filter(id=project_id, company=context.company).first()
        if not project:
            return failure('recommendation.create', 'Project not found in your company.')
        employee = Employee.objects.filter(
            id=employee_id, department__company=context.company
        ).first() if employee_id else None
        agent = AIAgent.objects.filter(id=ai_agent_id, company=context.company).first() if ai_agent_id else None
        if employee_id and not employee:
            return failure('recommendation.create', 'Employee not found in the project company.')
        if ai_agent_id and not agent:
            return failure('recommendation.create', 'AI agent not found in the project company.')
        with transaction.atomic():
            row = Recommendation.objects.create(
                project=project, employee=employee, ai_agent=agent,
                recommended_role=recommended_role, score=score, rank=rank,
                reason=reason, status=status,
            )
        return success('recommendation.create', 'Recommendation record created.', {
            'recommendation': {'id': row.id, 'project_id': project.id,
                               'employee_id': employee_id, 'ai_agent_id': ai_agent_id,
                               'score': decimal_value(row.score), 'rank': row.rank}
        })

    def list_recommendations(limit=25, offset=0, project_id=None):
        qs = Recommendation.objects.filter(project__company=context.company)
        if project_id:
            qs = qs.filter(project_id=project_id)
        total = qs.count()
        rows = list(qs.order_by('rank', 'id')[offset:offset + limit])
        return success('recommendation.list', f'Retrieved {len(rows)} recommendations.', {
            'total': total, 'limit': limit, 'offset': offset,
            'recommendations': [{'id': row.id, 'project_id': row.project_id,
                                 'employee_id': row.employee_id, 'ai_agent_id': row.ai_agent_id,
                                 'score': decimal_value(row.score), 'rank': row.rank,
                                 'status': row.status} for row in rows],
        })

    def get_recommendation(recommendation_id):
        row = Recommendation.objects.filter(
            id=recommendation_id, project__company=context.company
        ).first()
        if not row:
            return failure('recommendation.get', 'Recommendation not found in your company.')
        return success('recommendation.get', 'Recommendation retrieved.', {
            'recommendation': {'id': row.id, 'project_id': row.project_id,
                               'employee_id': row.employee_id, 'ai_agent_id': row.ai_agent_id,
                               'recommended_role': row.recommended_role,
                               'score': decimal_value(row.score), 'rank': row.rank,
                               'reason': row.reason, 'status': row.status}
        })

    return [
        StructuredTool.from_function(create_recommendation, name='create_recommendation', description='Create a company-scoped recommendation record; this does not generate or score recommendations.', args_schema=RecommendationCreateInput),
        StructuredTool.from_function(list_recommendations, name='list_recommendations', description='List recommendation records for company projects.', args_schema=RecommendationListInput),
        StructuredTool.from_function(get_recommendation, name='get_recommendation', description='Get a recommendation record by actual company-scoped ID.', args_schema=RecommendationIdInput),
    ]
