from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field


class TechnologyRecommendationInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    project_type: str = Field(min_length=1, max_length=150)
    requirements: list[str] = Field(default_factory=list, max_length=100)
    required_technologies: list[str] = Field(default_factory=list, max_length=30)


class FrameworkComparisonInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    frameworks: list[str] = Field(min_length=2, max_length=6)
    priorities: list[str] = Field(default_factory=list, max_length=20)


def _required(required, *names):
    lowered = {item.casefold(): item for item in required}
    for name in names:
        if name.casefold() in lowered:
            return lowered[name.casefold()]
    return None


def recommend_stack(project_type, requirements=None, required_technologies=None):
    requirements = requirements or []
    required = required_technologies or []
    text = ' '.join([project_type, *requirements]).casefold()
    choices = []

    frontend = _required(required, 'Flutter', 'React Native', 'React', 'Vue', 'Angular')
    if frontend:
        layer = 'mobile' if frontend in ('Flutter', 'React Native') else 'frontend'
    elif any(word in text for word in ('mobile', 'rider', 'customer app', 'ios', 'android')):
        frontend, layer = 'Flutter', 'mobile'
    else:
        frontend, layer = 'React', 'frontend'
    choices.append({
        'layer': layer, 'name': frontend, 'purpose': 'User interface',
        'rationale': 'Honors the requested client technology.' if frontend in required
        else 'Provides a mature component ecosystem and maintainable client delivery.',
        'source': 'user_required' if frontend in required else 'recommended',
        'alternatives': ['React Native'] if frontend == 'Flutter' else ['Vue'],
    })

    backend = _required(required, 'Django REST Framework', 'Django', 'FastAPI')
    if not backend:
        backend = 'Django REST Framework'
    choices.append({
        'layer': 'backend', 'name': backend, 'purpose': 'Application API and domain logic',
        'rationale': 'Honors the requested backend technology.' if backend in required
        else 'Offers mature authentication, ORM, administration, and API tooling.',
        'source': 'user_required' if backend in required else 'recommended',
        'alternatives': ['FastAPI'] if backend != 'FastAPI' else ['Django REST Framework'],
    })

    database = _required(required, 'PostgreSQL') or 'PostgreSQL'
    choices.append({
        'layer': 'database', 'name': database, 'purpose': 'Transactional data storage',
        'rationale': 'Honors the requested database.' if database in required
        else 'Provides strong relational integrity, transactions, and indexing.',
        'source': 'user_required' if database in required else 'recommended',
        'alternatives': [],
    })
    if any(word in text for word in ('real-time', 'realtime', 'tracking', 'feed', 'chat')):
        choices.append({
            'layer': 'cache', 'name': 'Redis',
            'purpose': 'Caching and transient real-time state',
            'rationale': 'Reduces database load and supports low-latency event workflows.',
            'source': 'recommended', 'alternatives': [],
        })
    return {
        'choices': choices,
        'architecture_style': 'Modular API-backed application with independently deployable clients',
        'notes': [
            'Recommendations are based only on supplied requirements and known tradeoffs; no live research was performed.'
        ],
    }


TRADEOFFS = {
    'django': ('Batteries-included web framework', 'More framework structure and baseline overhead'),
    'django rest framework': ('Mature Django API ecosystem', 'Serializer and framework conventions add complexity'),
    'fastapi': ('Strong typing and efficient async APIs', 'Fewer built-in business application facilities'),
    'flutter': ('One UI toolkit across mobile platforms', 'Dart expertise and platform integration may be needed'),
    'react native': ('JavaScript ecosystem and native bridges', 'Native dependency upgrades can require care'),
    'react': ('Large web ecosystem and flexible composition', 'Requires explicit architecture choices'),
}


def compare_frameworks(frameworks, priorities=None):
    return {
        'priorities': priorities or [],
        'frameworks': [
            {
                'name': name,
                'strength': TRADEOFFS.get(name.casefold(), ('Mature general-purpose option', 'Fit depends on team and constraints'))[0],
                'tradeoff': TRADEOFFS.get(name.casefold(), ('Mature general-purpose option', 'Fit depends on team and constraints'))[1],
            }
            for name in frameworks
        ],
        'live_research_performed': False,
    }


def technology_tools():
    return [
        StructuredTool.from_function(
            recommend_stack, name='recommend_technology_stack',
            description='Recommend a technology stack while preserving user-required technologies and explaining each choice.',
            args_schema=TechnologyRecommendationInput,
        ),
        StructuredTool.from_function(
            compare_frameworks, name='compare_frameworks',
            description='Compare named frameworks using known technical tradeoffs; this does not perform live research.',
            args_schema=FrameworkComparisonInput,
        ),
    ]
