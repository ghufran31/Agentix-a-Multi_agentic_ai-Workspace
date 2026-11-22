import re

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field


class DescriptionInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    description: str = Field(min_length=3, max_length=30000)


class SpecificationPreparationInput(DescriptionInput):
    project_name: str | None = Field(default=None, max_length=255)
    project_type: str | None = Field(default=None, max_length=150)


FEATURE_PATTERNS = {
    'Authentication': ('authentication', 'login', 'registration', 'sign up'),
    'Payments': ('payment', 'checkout', 'billing'),
    'Order management': ('order', 'cart'),
    'Real-time tracking': ('tracking', 'real-time', 'realtime'),
    'Admin dashboard': ('admin dashboard', 'administration portal'),
    'Notifications': ('notification', 'push notification'),
    'Search': ('search', 'filtering'),
    'Reporting': ('report', 'analytics'),
    'Customer application': ('customer app', 'customer portal'),
    'Rider application': ('rider app', 'driver app', 'courier app'),
    'Content feed': ('feed', 'posts', 'social media'),
    'User profiles': ('profile', 'social media'),
    'Messaging': ('messaging', 'chat'),
    'Department management': ('department', 'university management'),
    'Student management': ('student', 'university management'),
}


TECHNOLOGIES = (
    'Flutter', 'Django REST Framework', 'Django', 'FastAPI', 'PostgreSQL',
    'React', 'React Native', 'Vue', 'Angular', 'Redis', 'Celery', 'Docker',
    'Kubernetes', 'AWS', 'Azure', 'Google Cloud',
)


def _sentences(text):
    return [
        item.strip(' -\t')
        for item in re.split(r'(?<=[.!?])\s+|[\r\n]+|;\s*', text)
        if item.strip(' -\t')
    ]


def analyze_description(description):
    lowered = description.casefold()
    features = [
        name for name, phrases in FEATURE_PATTERNS.items()
        if any(phrase in lowered for phrase in phrases)
    ]
    technologies = [name for name in TECHNOLOGIES if name.casefold() in lowered]
    if 'Django REST Framework' in technologies and 'Django' in technologies:
        technologies.remove('Django')
    constraints = []
    deadline_match = re.search(
        r'\b(?:within\s+)?(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|'
        r'eight|nine|ten|eleven|twelve)[\s-]+(day|week|month|year)s?\b',
        lowered,
    )
    if deadline_match:
        constraints.append({
            'category': 'timeline',
            'description': deadline_match.group(0),
            'source': 'user',
        })
    project_type = 'software application'
    for candidate in (
        'e-commerce', 'food delivery', 'social media', 'university management',
        'mobile', 'web', 'dashboard', 'api',
    ):
        if candidate in lowered:
            project_type = candidate
            break
    essential_missing = []
    if len(description.split()) < 8 and not features:
        essential_missing.append({
            'field': 'core_users_and_workflows',
            'question': 'Who are the primary users and what core outcome must they achieve?',
            'impact': 'The core scope cannot yet be distinguished reliably.',
            'essential': True,
        })
    return {
        'project_type': project_type,
        'explicit_statements': _sentences(description),
        'features': features,
        'user_required_technologies': technologies,
        'constraints': constraints,
        'missing_essential_information': essential_missing,
    }


def prepare_specification(description, project_name=None, project_type=None):
    analysis = analyze_description(description)
    name = project_name or f'{analysis["project_type"].title()} Project'
    return {
        'name': name[:255],
        'description': description,
        'project_type': project_type or analysis['project_type'],
        'normalized_features': [
            {
                'name': feature,
                'description': f'Provide {feature.casefold()} capabilities.',
                'priority': 'must',
                'source': 'user',
            }
            for feature in analysis['features']
        ],
        'explicit_requirements': analysis['explicit_statements'],
        'constraints': analysis['constraints'],
        'missing_information': analysis['missing_essential_information'],
        'persistence_performed': False,
    }


def requirements_tools():
    return [
        StructuredTool.from_function(
            analyze_description,
            name='analyze_project_description',
            description=(
                'Deterministically extract explicit statements, features, named '
                'technologies, constraints, and essential gaps from a project request.'
            ),
            args_schema=DescriptionInput,
        ),
        StructuredTool.from_function(
            prepare_specification,
            name='prepare_project_specification',
            description=(
                'Normalize a project request into a validated specification draft. '
                'This never creates or saves a project.'
            ),
            args_schema=SpecificationPreparationInput,
        ),
    ]
