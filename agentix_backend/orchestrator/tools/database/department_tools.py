from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from companies.models import CompanyUser
from workforce.models import Department
from orchestrator.core.approval import approval_registry

from .base import PaginationInput, failure, success


class DepartmentIdInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    department_id: int = Field(gt=0)


class DepartmentCreateInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=5000)


class DepartmentUpdateInput(DepartmentIdInput):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=5000)


class DepartmentSearchInput(PaginationInput):
    search: str | None = Field(default=None, max_length=150)


class DepartmentEmployeeInput(DepartmentIdInput):
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


def department_tools(context):
    def create_department(name, description=None):
        try:
            context.require_write()
        except PermissionDenied as exc:
            return failure('department.create', str(exc))
        if Department.objects.filter(company=context.company, name__iexact=name).exists():
            return failure('department.create', 'A department with that name already exists.')
        with transaction.atomic():
            department = Department.objects.create(
                company=context.company, name=name.strip(), description=description
            )
        return success('department.create', 'Department created.', {'department': {
            'id': department.id, 'name': department.name, 'description': department.description,
        }})

    def get_department(department_id):
        department = Department.objects.filter(
            id=department_id, company=context.company
        ).annotate(employee_count=Count('employees')).first()
        if not department:
            return failure('department.get', 'Department not found in your company.')
        return success('department.get', 'Department retrieved.', {'department': {
            'id': department.id, 'name': department.name, 'description': department.description,
            'employee_count': department.employee_count,
        }})

    def list_departments(limit=25, offset=0, search=None):
        qs = Department.objects.filter(company=context.company).annotate(
            employee_count=Count('employees')
        )
        if search:
            qs = qs.filter(name__icontains=search)
        total = qs.count()
        rows = list(qs.order_by('id')[offset:offset + limit])
        return success('department.list', f'Retrieved {len(rows)} departments.', {
            'total': total, 'limit': limit, 'offset': offset,
            'departments': [{
                'id': row.id, 'name': row.name, 'description': row.description,
                'employee_count': row.employee_count,
            } for row in rows],
        })

    def update_department(department_id, name=None, description=None):
        try:
            context.require_write()
        except PermissionDenied as exc:
            return failure('department.update', str(exc))
        department = Department.objects.filter(
            id=department_id, company=context.company
        ).first()
        if not department:
            return failure('department.update', 'Department not found in your company.')
        changes = {}
        if name is not None:
            changes['name'] = name.strip()
        if description is not None:
            changes['description'] = description
        if 'name' in changes and Department.objects.filter(
            company=context.company, name__iexact=changes['name']
        ).exclude(id=department.id).exists():
            return failure('department.update', 'A department with that name already exists.')
        with transaction.atomic():
            for field, value in changes.items():
                setattr(department, field, value)
            department.save(update_fields=list(changes) or None)
        return success('department.update', 'Department updated.', {
            'department': {'id': department.id, 'name': department.name,
                           'description': department.description},
            'changes': changes,
        })

    def delete_department(department_id):
        try:
            context.require_write()
        except PermissionDenied as exc:
            return failure('department.delete', str(exc))
        department = Department.objects.filter(
            id=department_id, company=context.company
        ).prefetch_related('employees').first()
        if not department:
            return failure('department.delete', 'Department not found in your company.')
        employee_count = department.employees.count()
        pending = approval_registry.prepare(
            operation='department.delete',
            target={'department_id': department.id, 'name': department.name},
            proposed_changes={'delete_department': True, 'employee_count': employee_count},
            context=context,
        )
        return success(
            'department.delete',
            'Approval required before deleting this department.',
            {'pending_approval': {
                'approval_id': pending.approval_id,
                'affected_department_id': department.id,
                'affected_employee_count': employee_count,
            }},
            pending_approval={
                'approval_id': pending.approval_id,
                'affected_department_id': department.id,
                'affected_employee_count': employee_count,
            },
        )

    def department_employees(department_id, limit=25, offset=0):
        department = Department.objects.filter(
            id=department_id, company=context.company
        ).first()
        if not department:
            return failure('department.employees', 'Department not found in your company.')
        qs = department.employees.select_related('ai_profile').all()
        total = qs.count()
        employees = list(qs.order_by('id')[offset:offset + limit])
        return success('department.employees', f'Retrieved {len(employees)} employees.', {
            'department_id': department.id, 'total': total, 'limit': limit, 'offset': offset,
            'employees': [{
                'id': employee.id, 'employee_code': employee.employee_code,
                'first_name': employee.first_name, 'last_name': employee.last_name,
            } for employee in employees],
        })

    return [
        StructuredTool.from_function(create_department, name='create_department', description='Create a department in the authenticated company.', args_schema=DepartmentCreateInput),
        StructuredTool.from_function(get_department, name='get_department', description='Get one department in the authenticated company.', args_schema=DepartmentIdInput),
        StructuredTool.from_function(list_departments, name='list_departments', description='List and optionally search departments in the authenticated company.', args_schema=DepartmentSearchInput),
        StructuredTool.from_function(update_department, name='update_department', description='Update an existing department in the authenticated company.', args_schema=DepartmentUpdateInput),
        StructuredTool.from_function(delete_department, name='delete_department', description='Prepare deletion of a department; explicit approval is required.', args_schema=DepartmentIdInput),
        StructuredTool.from_function(department_employees, name='get_department_employees', description='List paginated employees assigned to a department.', args_schema=DepartmentEmployeeInput),
    ]
