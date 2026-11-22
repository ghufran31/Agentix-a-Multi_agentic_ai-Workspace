from django.core.exceptions import PermissionDenied
from django.db import transaction
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from workforce.models import EmployeeSkill, Skill
from orchestrator.core.approval import approval_registry

from .base import PaginationInput, failure, success


class SkillIdInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    skill_id: int = Field(gt=0)


class SkillCreateInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=150)
    category: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=5000)


class SkillUpdateInput(SkillIdInput):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    category: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=5000)


class SkillSearchInput(PaginationInput):
    search: str | None = Field(default=None, max_length=150)
    category: str | None = Field(default=None, max_length=100)


def skill_tools(context):
    def create_skill(name, category=None, description=None):
        try:
            context.require_write()
        except PermissionDenied as exc:
            return failure('skill.create', str(exc))
        if Skill.objects.filter(company=context.company, name__iexact=name).exists():
            return failure('skill.create', 'A skill with that name already exists.')
        with transaction.atomic():
            skill = Skill.objects.create(
                company=context.company, name=name.strip(),
                category=category, description=description,
            )
        return success('skill.create', 'Skill created.', {'skill': {
            'id': skill.id, 'name': skill.name, 'category': skill.category,
        }})

    def list_skills(limit=25, offset=0, search=None, category=None):
        qs = Skill.objects.filter(company=context.company)
        if search:
            qs = qs.filter(name__icontains=search)
        if category:
            qs = qs.filter(category__iexact=category)
        total = qs.count()
        rows = list(qs.order_by('id')[offset:offset + limit])
        return success('skill.list', f'Retrieved {len(rows)} skills.', {
            'total': total, 'limit': limit, 'offset': offset,
            'skills': [{'id': row.id, 'name': row.name, 'category': row.category,
                        'description': row.description} for row in rows],
        })

    def get_skill(skill_id):
        skill = Skill.objects.filter(id=skill_id, company=context.company).first()
        if not skill:
            return failure('skill.get', 'Skill not found in your company.')
        return success('skill.get', 'Skill retrieved.', {'skill': {
            'id': skill.id, 'name': skill.name, 'category': skill.category,
            'description': skill.description,
        }})

    def update_skill(skill_id, name=None, category=None, description=None):
        try:
            context.require_write()
        except PermissionDenied as exc:
            return failure('skill.update', str(exc))
        skill = Skill.objects.filter(id=skill_id, company=context.company).first()
        if not skill:
            return failure('skill.update', 'Skill not found in your company.')
        changes = {}
        if name is not None:
            changes['name'] = name.strip()
        if category is not None:
            changes['category'] = category
        if description is not None:
            changes['description'] = description
        if 'name' in changes and Skill.objects.filter(
            company=context.company, name__iexact=changes['name']
        ).exclude(id=skill.id).exists():
            return failure('skill.update', 'A skill with that name already exists.')
        with transaction.atomic():
            for field, value in changes.items():
                setattr(skill, field, value)
            skill.save(update_fields=list(changes) or None)
        return success('skill.update', 'Skill updated.', {
            'skill': {'id': skill.id, 'name': skill.name, 'category': skill.category},
            'changes': changes,
        })

    def delete_skill(skill_id):
        try:
            context.require_write()
        except PermissionDenied as exc:
            return failure('skill.delete', str(exc))
        skill = Skill.objects.filter(id=skill_id, company=context.company).first()
        if not skill:
            return failure('skill.delete', 'Skill not found in your company.')
        if EmployeeSkill.objects.filter(skill=skill).exists():
            return failure(
                'skill.delete',
                'Skill cannot be deleted while employee-skill relationships exist.',
            )
        pending = approval_registry.prepare(
            operation='skill.delete',
            target={'skill_id': skill.id, 'name': skill.name},
            proposed_changes={'delete_skill': True},
            context=context,
        )
        return success('skill.delete', 'Approval required before deleting this skill.', {
            'pending_approval': {'approval_id': pending.approval_id, 'skill_id': skill.id}
        }, pending_approval={
            'approval_id': pending.approval_id,
            'skill_id': skill.id,
        })

    return [
        StructuredTool.from_function(create_skill, name='create_skill', description='Create a company-scoped skill.', args_schema=SkillCreateInput),
        StructuredTool.from_function(list_skills, name='list_skills', description='List and search skills in the authenticated company.', args_schema=SkillSearchInput),
        StructuredTool.from_function(get_skill, name='get_skill', description='Get a skill by actual company-scoped ID.', args_schema=SkillIdInput),
        StructuredTool.from_function(update_skill, name='update_skill', description='Update a company-scoped skill.', args_schema=SkillUpdateInput),
        StructuredTool.from_function(delete_skill, name='delete_skill', description='Delete a skill only when it has no employee relationships.', args_schema=SkillIdInput),
    ]
