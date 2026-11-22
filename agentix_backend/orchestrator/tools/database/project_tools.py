from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from agents.models import AIAgent
from projects.models import Project, ProjectMember, ProjectRequirement
from workforce.models import Employee
from orchestrator.core.approval import approval_registry

from .base import PaginationInput, failure, success


class ProjectIdInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: int = Field(gt=0)


class ProjectCreateInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    status: str = Field(default='draft', max_length=50)
    priority: str = Field(default='medium', max_length=50)
    start_date: str | None = None
    deadline: str | None = None


class ProjectUpdateInput(ProjectIdInput):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    status: str | None = Field(default=None, max_length=50)
    priority: str | None = Field(default=None, max_length=50)
    start_date: str | None = None
    deadline: str | None = None


class ProjectSearchInput(PaginationInput):
    search: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, max_length=50)


class RequirementInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: int = Field(gt=0)
    requirement: str = Field(min_length=1, max_length=10000)
    required_skills: str | None = None
    required_roles: str | None = None
    priority: str = Field(default='medium', max_length=50)
    deadline: str | None = None


class MemberInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: int = Field(gt=0)
    employee_id: int | None = Field(default=None, gt=0)
    ai_agent_id: int | None = Field(default=None, gt=0)
    role: str | None = Field(default=None, max_length=150)
    member_type: str = Field(min_length=1, max_length=50)
    status: str = Field(default='active', max_length=50)


def project_tools(context):
    def project_queryset():
        return Project.objects.filter(company=context.company)

    def create_project(name, description=None, status='draft', priority='medium',
                       start_date=None, deadline=None):
        try:
            context.require_write()
        except PermissionDenied as exc:
            return failure('project.create', str(exc))
        with transaction.atomic():
            project = Project.objects.create(
                company=context.company, name=name, description=description,
                status=status, priority=priority,
                start_date=start_date or None, deadline=deadline or None,
            )
        return success('project.create', 'Project created.', {'project': {
            'id': project.id, 'name': project.name, 'status': project.status,
        }})

    def get_project(project_id):
        project = project_queryset().filter(id=project_id).first()
        if not project:
            return failure('project.get', 'Project not found in your company.')
        requirements = list(project.requirements.order_by('id')[:25])
        return success('project.get', 'Project retrieved.', {'project': {
            'id': project.id, 'name': project.name, 'description': project.description,
            'status': project.status, 'priority': project.priority,
            'start_date': project.start_date.isoformat() if project.start_date else None,
            'deadline': project.deadline.isoformat() if project.deadline else None,
            'requirements': [{
                'id': row.id, 'requirement': row.requirement,
                'required_skills': row.required_skills,
                'required_roles': row.required_roles,
            } for row in requirements],
        }})

    def list_projects(limit=25, offset=0, search=None, status=None):
        qs = project_queryset()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
        if status:
            qs = qs.filter(status__iexact=status)
        total = qs.count()
        rows = list(qs.order_by('id')[offset:offset + limit])
        return success('project.list', f'Retrieved {len(rows)} projects.', {
            'total': total, 'limit': limit, 'offset': offset,
            'projects': [{'id': row.id, 'name': row.name, 'status': row.status,
                          'priority': row.priority} for row in rows],
        })

    def update_project(project_id, name=None, description=None, status=None,
                       priority=None, start_date=None, deadline=None):
        try:
            context.require_write()
        except PermissionDenied as exc:
            return failure('project.update', str(exc))
        project = project_queryset().filter(id=project_id).first()
        if not project:
            return failure('project.update', 'Project not found in your company.')
        changes = {}
        for field, value in (
            ('name', name), ('description', description), ('status', status),
            ('priority', priority), ('start_date', start_date), ('deadline', deadline),
        ):
            if value is not None:
                changes[field] = value
        with transaction.atomic():
            for field, value in changes.items():
                setattr(project, field, value or None)
            project.save(update_fields=list(changes) or None)
        return success('project.update', 'Project updated.', {
            'project': {'id': project.id, 'name': project.name},
            'changes': changes,
        })

    def delete_project(project_id):
        try:
            context.require_write()
        except PermissionDenied as exc:
            return failure('project.delete', str(exc))
        project = project_queryset().filter(id=project_id).first()
        if not project:
            return failure('project.delete', 'Project not found in your company.')
        pending = approval_registry.prepare(
            operation='project.delete',
            target={'project_id': project.id, 'name': project.name},
            proposed_changes={'delete_project': True},
            context=context,
        )
        return success('project.delete', 'Approval required before deleting this project.', {
            'pending_approval': {'approval_id': pending.approval_id, 'project_id': project.id}
        }, pending_approval={
            'approval_id': pending.approval_id,
            'project_id': project.id,
        })

    def add_requirement(project_id, requirement, required_skills=None,
                         required_roles=None, priority='medium', deadline=None):
        try:
            context.require_write()
        except PermissionDenied as exc:
            return failure('project.requirement.create', str(exc))
        project = project_queryset().filter(id=project_id).first()
        if not project:
            return failure('project.requirement.create', 'Project not found in your company.')
        with transaction.atomic():
            row = ProjectRequirement.objects.create(
                project=project, requirement=requirement,
                required_skills=required_skills, required_roles=required_roles,
                priority=priority, deadline=deadline or None,
            )
        return success('project.requirement.create', 'Project requirement created.', {
            'requirement': {'id': row.id, 'project_id': project.id,
                            'requirement': row.requirement}
        })

    def assign_member(project_id, employee_id=None, ai_agent_id=None,
                      role=None, member_type='member', status='active'):
        try:
            context.require_write()
        except PermissionDenied as exc:
            return failure('project.member.assign', str(exc))
        if (employee_id is None) == (ai_agent_id is None):
            return failure('project.member.assign', 'Exactly one of employee_id or ai_agent_id is required.')
        project = project_queryset().filter(id=project_id).first()
        if not project:
            return failure('project.member.assign', 'Project not found in your company.')
        employee = Employee.objects.filter(
            id=employee_id, department__company=context.company
        ).first() if employee_id else None
        agent = AIAgent.objects.filter(
            id=ai_agent_id, company=context.company
        ).first() if ai_agent_id else None
        if employee_id and not employee:
            return failure('project.member.assign', 'Employee not found in the project company.')
        if ai_agent_id and not agent:
            return failure('project.member.assign', 'AI agent not found in the project company.')
        with transaction.atomic():
            member = ProjectMember.objects.create(
                project=project, employee=employee, ai_agent=agent,
                role=role, member_type=member_type, status=status,
            )
        return success('project.member.assign', 'Project member assigned.', {
            'member': {'id': member.id, 'project_id': project.id,
                       'employee_id': employee_id, 'ai_agent_id': ai_agent_id}
        })

    return [
        StructuredTool.from_function(create_project, name='create_project', description='Create a project in the authenticated company.', args_schema=ProjectCreateInput),
        StructuredTool.from_function(get_project, name='get_project', description='Get project details and bounded requirements by actual company-scoped ID.', args_schema=ProjectIdInput),
        StructuredTool.from_function(list_projects, name='list_projects', description='List or search projects in the authenticated company.', args_schema=ProjectSearchInput),
        StructuredTool.from_function(update_project, name='update_project', description='Update an existing project.', args_schema=ProjectUpdateInput),
        StructuredTool.from_function(delete_project, name='delete_project', description='Prepare project deletion; explicit approval is required.', args_schema=ProjectIdInput),
        StructuredTool.from_function(add_requirement, name='create_project_requirement', description='Add a requirement to a project in the authenticated company.', args_schema=RequirementInput),
        StructuredTool.from_function(assign_member, name='assign_project_member', description='Assign exactly one same-company employee or AI agent to a project.', args_schema=MemberInput),
    ]
