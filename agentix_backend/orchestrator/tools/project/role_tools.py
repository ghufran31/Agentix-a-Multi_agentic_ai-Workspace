from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field


class RoleSkillInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    project_type: str = Field(min_length=1, max_length=150)
    technologies: list[str] = Field(default_factory=list, max_length=30)
    features: list[str] = Field(default_factory=list, max_length=100)


ROLE_SKILLS = {
    'Product Manager': ['Requirements Analysis', 'Agile Planning'],
    'UI/UX Designer': ['User Research', 'Figma'],
    'Backend Engineer': ['API Design', 'Python', 'Database Design'],
    'Frontend Engineer': ['Frontend Architecture', 'Automated Testing'],
    'Mobile Engineer': ['Mobile Architecture', 'Automated Testing'],
    'QA Engineer': ['Test Automation', 'API Testing'],
    'DevOps Engineer': ['CI/CD', 'Docker', 'Cloud Infrastructure'],
}


def identify_roles(project_type, technologies=None, features=None, taxonomy=None):
    technologies = technologies or []
    features = features or []
    text = ' '.join([project_type, *technologies, *features]).casefold()
    role_names = ['Product Manager', 'UI/UX Designer', 'Backend Engineer', 'QA Engineer']
    role_names.append(
        'Mobile Engineer'
        if any(item in text for item in ('flutter', 'react native', 'mobile', 'ios', 'android'))
        else 'Frontend Engineer'
    )
    role_names.append('DevOps Engineer')

    tech_role = 'Mobile Engineer' if 'Mobile Engineer' in role_names else 'Frontend Engineer'
    dynamic_skills = {
        'Backend Engineer': [item for item in technologies if item.casefold() in (
            'django', 'django rest framework', 'fastapi', 'postgresql', 'redis'
        )],
        tech_role: [item for item in technologies if item.casefold() in (
            'flutter', 'react native', 'react', 'vue', 'angular'
        )],
    }
    roles = []
    all_skills = []
    for role_name in role_names:
        skills = list(dict.fromkeys(ROLE_SKILLS[role_name] + dynamic_skills.get(role_name, [])))
        roles.append({
            'name': role_name,
            'responsibilities': [f'Own {role_name.casefold()} deliverables and quality.'],
            'skills': skills,
            'suggested_count': 1,
        })
        for skill in skills:
            all_skills.append((skill, role_name))

    taxonomy_by_name = {
        item['name'].casefold(): item for item in (taxonomy or [])
    }
    skills = []
    for name in dict.fromkeys(item[0] for item in all_skills):
        match = taxonomy_by_name.get(name.casefold())
        roles_for_skill = [role for skill, role in all_skills if skill == name]
        skills.append({
            'name': name,
            'category': match.get('category') or 'Technical' if match else 'Technical',
            'roles': roles_for_skill,
            'taxonomy_status': 'existing' if match else 'proposed',
            'existing_skill_id': match['id'] if match else None,
        })
    return {'roles': roles, 'skills': skills}


def role_tools(context=None):
    def map_roles_and_skills(project_type, technologies=None, features=None):
        taxonomy = []
        if context is not None:
            from workforce.models import Skill
            taxonomy = list(
                Skill.objects.filter(company=context.company)
                .order_by('id')
                .values('id', 'name', 'category')[:500]
            )
        return identify_roles(
            project_type, technologies=technologies, features=features,
            taxonomy=taxonomy,
        )

    return [
        StructuredTool.from_function(
            map_roles_and_skills,
            name='identify_project_roles_and_skills',
            description=(
                'Identify technical roles and skills, matching skills against the '
                'authorized company taxonomy when a company context is available.'
            ),
            args_schema=RoleSkillInput,
        )
    ]
