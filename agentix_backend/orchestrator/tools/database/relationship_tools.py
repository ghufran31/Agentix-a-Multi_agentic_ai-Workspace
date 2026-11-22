from django.db.models import Count
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict

from workforce.models import Department, Employee
from projects.models import Project

from .base import PaginationInput, failure, success


class SummaryInput(PaginationInput):
    pass


class DuplicateInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: str


def relationship_tools(context):
    def department_employee_summary(limit=25, offset=0):
        rows = list(
            Department.objects.filter(company=context.company)
            .annotate(employee_count=Count('employees'))
            .order_by('-employee_count', 'id')[offset:offset + limit]
        )
        total = Department.objects.filter(company=context.company).count()
        return success('summary.department_employees', 'Department employee counts retrieved.', {
            'total': total, 'limit': limit, 'offset': offset,
            'departments': [{'department_id': row.id, 'name': row.name,
                             'employee_count': row.employee_count} for row in rows],
        })

    def project_member_summary(limit=25, offset=0):
        rows = list(
            Project.objects.filter(company=context.company)
            .annotate(member_count=Count('members'))
            .order_by('id')[offset:offset + limit]
        )
        total = Project.objects.filter(company=context.company).count()
        return success('summary.project_members', 'Project member counts retrieved.', {
            'total': total, 'limit': limit, 'offset': offset,
            'projects': [{'project_id': row.id, 'name': row.name,
                          'member_count': row.member_count} for row in rows],
        })

    def detect_duplicates(kind):
        kind = kind.lower().strip()
        duplicates = []
        if kind == 'employees':
            seen = {}
            for employee in Employee.objects.filter(
                department__company=context.company
            ).only('employee_code', 'first_name', 'last_name', 'department_id').order_by('id'):
                key = (employee.first_name.lower(), employee.last_name.lower(), employee.employee_code.lower())
                seen.setdefault(key, []).append(employee.id)
            duplicates = [{'ids': ids, 'count': len(ids)}
                          for ids in seen.values() if len(ids) > 1][:100]
        elif kind == 'projects':
            seen = {}
            for project in Project.objects.filter(company=context.company).only('name').order_by('id'):
                seen.setdefault(project.name.lower(), []).append(project.id)
            duplicates = [{'ids': ids, 'count': len(ids)}
                          for ids in seen.values() if len(ids) > 1][:100]
        else:
            return failure('duplicates.detect', 'Unsupported duplicate kind. Use employees or projects.')
        return success('duplicates.detect', f'Duplicate {kind} detected.', {
            'kind': kind, 'duplicates': duplicates,
        })

    return [
        StructuredTool.from_function(department_employee_summary, name='summarize_department_employees', description='Count employees per department in the authenticated company.', args_schema=SummaryInput),
        StructuredTool.from_function(project_member_summary, name='summarize_project_members', description='Count assigned members per project in the authenticated company.', args_schema=SummaryInput),
        StructuredTool.from_function(detect_duplicates, name='detect_duplicates', description='Detect bounded duplicate employee or project records within the authenticated company.', args_schema=DuplicateInput),
    ]
