from django.core.exceptions import PermissionDenied
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from companies.models import CompanyUser

from .base import PaginationInput, failure, success


class CompanyUpdateInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str | None = Field(default=None, max_length=255)
    industry: str | None = Field(default=None, max_length=150)
    description: str | None = Field(default=None, max_length=10000)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=10000)


class MembershipInput(PaginationInput):
    pass


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra='forbid')


def company_tools(context):
    def get_company():
        company = context.company
        return success('company.get', 'Company retrieved.', {'company': {
            'id': company.id, 'name': company.name, 'industry': company.industry,
            'description': company.description, 'email': company.email,
            'phone': company.phone, 'address': company.address,
        }})

    def update_company(name=None, industry=None, description=None,
                       email=None, phone=None, address=None):
        if context.role != CompanyUser.Role.OWNER:
            return failure('company.update', 'Only the company owner may update company details.')
        company = context.company
        changes = {}
        for field, value in (
            ('name', name), ('industry', industry), ('description', description),
            ('email', email), ('phone', phone), ('address', address),
        ):
            if value is not None:
                changes[field] = value
        for field, value in changes.items():
            setattr(company, field, value)
        if changes:
            company.save(update_fields=list(changes))
        return success('company.update', 'Company updated.', {
            'company': {'id': company.id, 'name': company.name},
            'changes': changes,
        })

    def list_members(limit=25, offset=0):
        qs = CompanyUser.objects.filter(company=context.company).select_related('user')
        total = qs.count()
        rows = list(qs.order_by('id')[offset:offset + limit])
        return success('company.members', f'Retrieved {len(rows)} memberships.', {
            'total': total, 'limit': limit, 'offset': offset,
            'members': [{'membership_id': row.id, 'user_id': row.user_id,
                         'role': row.role} for row in rows],
        })

    return [
        StructuredTool.from_function(get_company, name='get_company', description='Get authorized information for the authenticated company.', args_schema=EmptyInput),
        StructuredTool.from_function(update_company, name='update_company', description='Update company details only as the owner.', args_schema=CompanyUpdateInput),
        StructuredTool.from_function(list_members, name='list_company_members', description='List paginated members of the authenticated company.', args_schema=MembershipInput),
    ]
