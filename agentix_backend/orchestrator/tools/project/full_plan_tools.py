import re

from langchain_core.tools import StructuredTool

from .planning_tools import generate_roadmap
from .requirements_tools import DescriptionInput, analyze_description
from .role_tools import identify_roles
from .technology_tools import recommend_stack


NUMBER_WORDS = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
    'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12,
}


def _deadline_weeks(constraints):
    for constraint in constraints:
        text = constraint['description'].casefold()
        match = re.search(
            r'(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|'
            r'ten|eleven|twelve)[\s-]+(day|week|month|year)',
            text,
        )
        if not match:
            continue
        raw, unit = match.groups()
        value = float(raw) if raw[0].isdigit() else float(NUMBER_WORDS[raw])
        return round(value * {'day': 1 / 7, 'week': 1, 'month': 4, 'year': 52}[unit], 1)
    return None


def full_plan_tools(context=None):
    def create_complete_planning_evidence(description):
        analysis = analyze_description(description)
        stack = recommend_stack(
            analysis['project_type'],
            requirements=analysis['explicit_statements'],
            required_technologies=analysis['user_required_technologies'],
        )
        taxonomy = []
        if context is not None:
            from workforce.models import Skill
            taxonomy = list(
                Skill.objects.filter(company=context.company)
                .order_by('id')
                .values('id', 'name', 'category')[:500]
            )
        roles = identify_roles(
            analysis['project_type'],
            technologies=[item['name'] for item in stack['choices']],
            features=analysis['features'],
            taxonomy=taxonomy,
        )
        features = analysis['features'] or [analysis['project_type'].title()]
        roadmap = generate_roadmap(
            features,
            deadline_weeks=_deadline_weeks(analysis['constraints']),
            constraints=[item['description'] for item in analysis['constraints']],
        )
        return {
            'requirements_analysis': analysis,
            'technology_stack': stack,
            'roles_and_skills': roles,
            'roadmap': roadmap,
            'persistence_performed': False,
        }

    return [
        StructuredTool.from_function(
            create_complete_planning_evidence,
            name='create_complete_planning_evidence',
            description=(
                'Create complete deterministic planning evidence for a broad project '
                'request in one call: requirements, technology, roles, skills, and '
                'roadmap. This never saves a project.'
            ),
            args_schema=DescriptionInput,
        )
    ]
