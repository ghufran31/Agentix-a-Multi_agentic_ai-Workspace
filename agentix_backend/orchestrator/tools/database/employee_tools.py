from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from workforce.models import (
    Department,
    Employee,
    EmployeeAIProfile,
    EmployeeSkill,
    Skill,
)
from projects.models import Project
from orchestrator.core.approval import approval_registry

from .base import PaginationInput, decimal_value, failure, success


class EmployeeIdInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    employee_id: int = Field(gt=0)


class EmployeeCreateInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    department_id: int = Field(gt=0)
    employee_code: str = Field(min_length=1, max_length=50)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=5000)


class EmployeeUpdateInput(EmployeeIdInput):
    department_id: int | None = Field(default=None, gt=0)
    employee_code: str | None = Field(default=None, min_length=1, max_length=50)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=5000)
    date_of_birth: str | None = Field(default=None)


class EmployeeSearchInput(PaginationInput):
    search: str | None = Field(default=None, max_length=255)
    department_id: int | None = Field(default=None, gt=0)
    skill: str | None = Field(default=None, max_length=150)


class ProfileUpdateInput(EmployeeIdInput):
    availability_status: str | None = Field(default=None)
    current_workload: float | None = Field(default=None, ge=0)
    employment_status: str | None = Field(default=None)
    job_title: str | None = Field(default=None, max_length=150)


class SkillLinkInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    employee_id: int = Field(gt=0)
    skill_id: int = Field(gt=0)
    proficiency: float | None = Field(default=None, ge=0, le=100)
    years_experience: float = Field(default=0, ge=0)


class EmployeeSkillUnlinkInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    employee_id: int = Field(gt=0)
    skill_id: int = Field(gt=0)


class ApprovalInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    approval_id: str = Field(min_length=1)
    approved: bool


def employee_tools(context):
    def employee_queryset():
        return Employee.objects.filter(
            department__company=context.company
        ).select_related('department', 'ai_profile')

    def create_employee(department_id, employee_code, first_name, last_name,
                        email=None, phone=None, address=None):
        try:
            context.require_write()
        except PermissionDenied as exc:
            return failure('employee.create', str(exc))
        department = Department.objects.filter(
            id=department_id, company=context.company
        ).first()
        if not department:
            return failure('employee.create', 'Department not found in your company.')
        if Employee.objects.filter(department=department, employee_code=employee_code).exists():
            return failure('employee.create', 'An employee with that code already exists in the department.')
        with transaction.atomic():
            employee = Employee.objects.create(
                department=department,
                employee_code=employee_code.strip(),
                first_name=first_name.strip(),
                last_name=last_name.strip(),
                email=email,
                phone=phone,
                address=address,
            )
        return success('employee.create', 'Employee created.', {'employee': {
            'id': employee.id, 'employee_code': employee.employee_code,
            'first_name': employee.first_name, 'last_name': employee.last_name,
            'department_id': department.id,
        }})

    def get_employee(employee_id):
        employee = employee_queryset().filter(id=employee_id).first()
        if not employee:
            return failure('employee.get', 'Employee not found in your company.')
        profile = getattr(employee, 'ai_profile', None)
        return success('employee.get', 'Employee retrieved.', {'employee': {
            'id': employee.id, 'employee_code': employee.employee_code,
            'first_name': employee.first_name, 'last_name': employee.last_name,
            'email': employee.email, 'phone': employee.phone, 'department_id': employee.department_id,
            'profile': None if not profile else {
                'availability_status': profile.availability_status,
                'current_workload': decimal_value(profile.current_workload),
                'employment_status': profile.employment_status,
                'job_title': profile.job_title,
            },
        }})

    def list_employees(limit=25, offset=0, search=None, department_id=None, skill=None):
        qs = employee_queryset()
        if department_id:
            qs = qs.filter(department_id=department_id)
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(employee_code__icontains=search)
            )
        if skill:
            qs = qs.filter(skill_assignments__skill__name__icontains=skill)
        qs = qs.distinct()
        total = qs.count()
        rows = list(qs.order_by('id')[offset:offset + limit])
        return success('employee.list', f'Retrieved {len(rows)} employees.', {
            'total': total, 'limit': limit, 'offset': offset,
            'employees': [{
                'id': row.id, 'employee_code': row.employee_code,
                'first_name': row.first_name, 'last_name': row.last_name,
                'department_id': row.department_id,
            } for row in rows],
        })

    def update_employee(employee_id, department_id=None, employee_code=None,
                        first_name=None, last_name=None, email=None, phone=None,
                        address=None, date_of_birth=None):
        try:
            context.require_write()
        except PermissionDenied as exc:
            return failure('employee.update', str(exc))
        employee = employee_queryset().filter(id=employee_id).first()
        if not employee:
            return failure('employee.update', 'Employee not found in your company.')
        changes = {}
        if department_id is not None:
            department = Department.objects.filter(id=department_id, company=context.company).first()
            if not department:
                return failure('employee.update', 'Department not found in your company.')
            incompatible = employee.skill_assignments.exclude(
                skill__company_id=context.company.id
            ).exists()
            if incompatible:
                return failure('employee.update', 'Moving this employee would invalidate skill relationships.')
            changes['department'] = department
        for field, value in (
            ('employee_code', employee_code), ('first_name', first_name),
            ('last_name', last_name), ('email', email), ('phone', phone),
            ('address', address), ('date_of_birth', date_of_birth),
        ):
            if value is not None:
                changes[field] = value.strip() if isinstance(value, str) and field not in ('address',) else value
        department = changes.get('department', employee.department)
        code = changes.get('employee_code', employee.employee_code)
        if Employee.objects.filter(department=department, employee_code=code).exclude(id=employee.id).exists():
            return failure('employee.update', 'An employee with that code already exists in the department.')
        with transaction.atomic():
            for field, value in changes.items():
                setattr(employee, field, value)
            employee.save(update_fields=[field for field in changes])
        return success('employee.update', 'Employee updated.', {
            'employee': {'id': employee.id, 'employee_code': employee.employee_code,
                         'first_name': employee.first_name, 'last_name': employee.last_name,
                         'department_id': employee.department_id},
            'changes': {key: getattr(value, 'id', value) for key, value in changes.items()},
        })

    def delete_employee(employee_id):
        try:
            context.require_write()
        except PermissionDenied as exc:
            return failure('employee.delete', str(exc))
        employee = employee_queryset().filter(id=employee_id).first()
        if not employee:
            return failure('employee.delete', 'Employee not found in your company.')
        pending = approval_registry.prepare(
            operation='employee.delete',
            target={'employee_id': employee.id, 'name': f'{employee.first_name} {employee.last_name}'},
            proposed_changes={'delete_employee': True},
            context=context,
        )
        return success('employee.delete', 'Approval required before deleting this employee.', {
            'pending_approval': {'approval_id': pending.approval_id, 'affected_employee_id': employee.id}
        }, pending_approval={
            'approval_id': pending.approval_id,
            'affected_employee_id': employee.id,
        })

    def get_profile(employee_id):
        employee = employee_queryset().filter(id=employee_id).first()
        if not employee:
            return failure('employee.profile.get', 'Employee not found in your company.')
        profile = getattr(employee, 'ai_profile', None)
        if not profile:
            return failure('employee.profile.get', 'No AI profile exists for this employee.')
        return success('employee.profile.get', 'Employee profile retrieved.', {'profile': {
            'employee_id': employee.id, 'job_title': profile.job_title,
            'availability_status': profile.availability_status,
            'current_workload': decimal_value(profile.current_workload),
            'employment_status': profile.employment_status,
            'experience_years': decimal_value(profile.experience_years),
        }})

    def update_profile(employee_id, availability_status=None, current_workload=None,
                       employment_status=None, job_title=None):
        try:
            context.require_write()
        except PermissionDenied as exc:
            return failure('employee.profile.update', str(exc))
        employee = employee_queryset().filter(id=employee_id).first()
        if not employee:
            return failure('employee.profile.update', 'Employee not found in your company.')
        profile, _ = EmployeeAIProfile.objects.get_or_create(employee=employee)
        changes = {}
        if availability_status is not None:
            if availability_status not in EmployeeAIProfile.AvailabilityStatus.values:
                return failure('employee.profile.update', 'Invalid availability status.')
            changes['availability_status'] = availability_status
        if current_workload is not None:
            changes['current_workload'] = current_workload
        if employment_status is not None:
            if employment_status not in EmployeeAIProfile.EmploymentStatus.values:
                return failure('employee.profile.update', 'Invalid employment status.')
            changes['employment_status'] = employment_status
        if job_title is not None:
            changes['job_title'] = job_title
        with transaction.atomic():
            for field, value in changes.items():
                setattr(profile, field, value)
            profile.save(update_fields=list(changes) or None)
        return success('employee.profile.update', 'Employee profile updated.', {
            'employee_id': employee.id, 'changes': changes,
        })

    def link_skill(employee_id, skill_id, proficiency=None, years_experience=0):
        try:
            context.require_write()
        except PermissionDenied as exc:
            return failure('employee.skill.link', str(exc))
        employee = employee_queryset().filter(id=employee_id).first()
        skill = Skill.objects.filter(id=skill_id, company=context.company).first()
        if not employee:
            return failure('employee.skill.link', 'Employee not found in your company.')
        if not skill:
            return failure('employee.skill.link', 'Skill not found in your company.')
        if employee.department.company_id != skill.company_id:
            return failure('employee.skill.link', 'Employee and skill must belong to the same company.')
        if EmployeeSkill.objects.filter(employee=employee, skill=skill).exists():
            return failure('employee.skill.link', 'This employee already has that skill.')
        with transaction.atomic():
            link = EmployeeSkill.objects.create(
                employee=employee, skill=skill,
                proficiency=proficiency, years_experience=years_experience,
            )
        return success('employee.skill.link', 'Employee skill added.', {'link': {
            'id': link.id, 'employee_id': employee.id, 'skill_id': skill.id,
        }})

    def unlink_skill(employee_id, skill_id):
        try:
            context.require_write()
        except PermissionDenied as exc:
            return failure('employee.skill.unlink', str(exc))
        link = EmployeeSkill.objects.filter(
            employee_id=employee_id,
            skill_id=skill_id,
            employee__department__company=context.company,
            skill__company=context.company,
        ).first()
        if not link:
            return failure('employee.skill.unlink', 'Employee-skill relationship not found.')
        link_id = link.id
        pending = approval_registry.prepare(
            operation='employee.skill.unlink',
            target={'link_id': link_id, 'employee_id': employee_id, 'skill_id': skill_id},
            proposed_changes={'delete_employee_skill': True},
            context=context,
        )
        return success('employee.skill.unlink', 'Approval required to remove this relationship.', {
            'pending_approval': {'approval_id': pending.approval_id, 'link_id': link_id}
        }, pending_approval={
            'approval_id': pending.approval_id,
            'link_id': link_id,
        })

    def approve_action(approval_id, approved):
        item = approval_registry.resolve(
            approval_id, approved=approved, context=context
        )
        if not item:
            return failure('approval.resolve', 'Approval request not found or not authorized.')
        if not approved:
            return success('approval.resolve', 'Action rejected.', {
                'approval_id': approval_id, 'approved': False,
            })
        if item.operation == 'employee.delete':
            employee = employee_queryset().filter(id=item.target['employee_id']).first()
            if not employee:
                return failure('approval.execute', 'Employee is no longer present.')
            employee_id = employee.id
            with transaction.atomic():
                employee.delete()
            return success('approval.execute', 'Employee deleted.', {'employee_id': employee_id})
        if item.operation == 'employee.skill.unlink':
            link = EmployeeSkill.objects.filter(
                id=item.target['link_id'], employee__department__company=context.company,
                skill__company=context.company,
            ).first()
            if not link:
                return failure('approval.execute', 'Employee-skill relationship is no longer present.')
            link.delete()
            return success('approval.execute', 'Employee-skill relationship removed.', item.target)
        if item.operation == 'department.delete':
            department = Department.objects.filter(
                id=item.target['department_id'], company=context.company
            ).first()
            if not department:
                return failure('approval.execute', 'Department is no longer present.')
            department_id = department.id
            with transaction.atomic():
                department.delete()
            return success('approval.execute', 'Department deleted.', {
                'department_id': department_id,
            })
        if item.operation == 'project.delete':
            project = Project.objects.filter(
                id=item.target['project_id'], company=context.company
            ).first()
            if not project:
                return failure('approval.execute', 'Project is no longer present.')
            project_id = project.id
            with transaction.atomic():
                project.delete()
            return success('approval.execute', 'Project deleted.', {
                'project_id': project_id,
            })
        if item.operation == 'skill.delete':
            skill = Skill.objects.filter(
                id=item.target['skill_id'], company=context.company
            ).first()
            if not skill:
                return failure('approval.execute', 'Skill is no longer present.')
            if EmployeeSkill.objects.filter(skill=skill).exists():
                return failure('approval.execute', 'Skill is still used by employee-skill relationships.')
            skill_id = skill.id
            with transaction.atomic():
                skill.delete()
            return success('approval.execute', 'Skill deleted.', {'skill_id': skill_id})
        return failure('approval.execute', 'Unsupported approval operation.')

    return [
        StructuredTool.from_function(create_employee, name='create_employee', description='Create an employee in a department in the authenticated company.', args_schema=EmployeeCreateInput),
        StructuredTool.from_function(get_employee, name='get_employee', description='Get an employee by actual company-scoped ID.', args_schema=EmployeeIdInput),
        StructuredTool.from_function(list_employees, name='list_employees', description='List or search employees in the authenticated company.', args_schema=EmployeeSearchInput),
        StructuredTool.from_function(update_employee, name='update_employee', description='Update an employee using its actual company-scoped ID.', args_schema=EmployeeUpdateInput),
        StructuredTool.from_function(delete_employee, name='delete_employee', description='Prepare employee deletion; explicit approval is required.', args_schema=EmployeeIdInput),
        StructuredTool.from_function(get_profile, name='get_employee_profile', description='Get one employee AI profile.', args_schema=EmployeeIdInput),
        StructuredTool.from_function(update_profile, name='update_employee_profile', description='Update employee availability, workload, employment, or job title.', args_schema=ProfileUpdateInput),
        StructuredTool.from_function(link_skill, name='manage_employee_skills', description='Add or update an employee skill relationship.', args_schema=SkillLinkInput),
        StructuredTool.from_function(unlink_skill, name='unlink_employee_skill', description='Prepare removal of an employee skill relationship; approval is required.', args_schema=EmployeeSkillUnlinkInput),
        StructuredTool.from_function(approve_action, name='resolve_delete_approval', description='Approve or reject a prepared destructive action.', args_schema=ApprovalInput),
    ]
