import json
from datetime import date
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field

from orchestrator.agents.project.schemas import ProjectSpecification


class MappedRequirement(BaseModel):
    model_config = ConfigDict(extra='forbid')

    requirement: str = Field(min_length=1, max_length=2000)
    required_skills: list[str] = Field(default_factory=list, max_length=100)
    required_roles: list[str] = Field(default_factory=list, max_length=50)
    priority: str = Field(default='medium', max_length=50)


class ProjectDatabaseMapping(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    deadline: date | None = None
    status: str = Field(default='draft', max_length=50)
    priority: str = Field(default='medium', max_length=50)
    requirements: list[MappedRequirement] = Field(default_factory=list, max_length=150)
    matched_skills: list[str] = Field(default_factory=list, max_length=100)
    unresolved_skills: list[str] = Field(default_factory=list, max_length=100)
    unresolved_roles: list[str] = Field(default_factory=list, max_length=50)
    warnings: list[str] = Field(default_factory=list, max_length=50)


def map_project_specification(specification, *, company):
    if isinstance(specification, dict):
        specification = ProjectSpecification.model_validate(specification, strict=True)

    existing_names = {
        skill.name.strip().casefold(): skill.name.strip()
        for skill in company.skills.all()
    }
    matched_skills = []
    unresolved_skills = []
    for skill in specification.required_skills:
        name = skill.name.strip()
        canonical_name = existing_names.get(name.casefold())
        if canonical_name is not None:
            matched_skills.append(canonical_name)
        else:
            unresolved_skills.append(name)

    role_names = [role.name.strip() for role in specification.required_roles]
    if not role_names:
        warnings = ['No required roles were provided by the specification.']
    else:
        warnings = []

    requirements = []
    for index, requirement in enumerate(specification.functional_requirements):
        related_features = set(requirement.related_features)
        feature_skills = []
        feature_roles = []
        for skill_name in (
            skill.name.strip() for skill in specification.required_skills
        ):
            feature_skills.append(skill_name)
        for role in specification.required_roles:
            if not role.skills:
                continue
            if related_features and role.name not in role_names:
                continue
            feature_roles.append(role.name)
        requirements.append(MappedRequirement(
            requirement=requirement.description,
            required_skills=feature_skills or matched_skills,
            required_roles=feature_roles or role_names,
            priority='medium' if requirement.priority in ('should', 'could') else 'high',
        ))

    if len(requirements) > 150:
        warnings.append('Some functional requirements were omitted because the persistence limit is 150.')
        requirements = requirements[:150]

    return ProjectDatabaseMapping(
        name=specification.name,
        description=specification.description,
        deadline=specification.deadline,
        status='draft',
        priority='medium',
        requirements=requirements,
        matched_skills=list(dict.fromkeys(matched_skills)),
        unresolved_skills=list(dict.fromkeys(unresolved_skills)),
        unresolved_roles=[],
        warnings=warnings + (
            ['Unresolved skills are saved as requested text and are not linked to company skill records.']
            if unresolved_skills else []
        ),
    )


def canonical_mapping_payload(mapping):
    payload = mapping.model_dump(mode='json', exclude_none=False)
    encoded = json.dumps(
        payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
    )
    return payload, sha256(encoded.encode('utf-8')).hexdigest()
