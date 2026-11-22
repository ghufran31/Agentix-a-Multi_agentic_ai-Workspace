from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field


class RoadmapInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    features: list[str] = Field(min_length=1, max_length=100)
    deadline_weeks: float | None = Field(default=None, gt=0, le=260)
    constraints: list[str] = Field(default_factory=list, max_length=50)


def generate_roadmap(features, deadline_weeks=None, constraints=None):
    constraints = constraints or []
    total = deadline_weeks or max(8.0, min(32.0, 6.0 + len(features) * 1.5))
    weights = [0.12, 0.18, 0.42, 0.18, 0.10]
    phase_names = [
        'Discovery and scope', 'Architecture and experience design',
        'Incremental implementation', 'System validation', 'Release and handover',
    ]
    objectives = [
        'Confirm users, workflows, acceptance criteria, and delivery scope.',
        'Validate architecture, data boundaries, interfaces, and user experience.',
        'Deliver prioritized features in testable vertical increments.',
        'Verify integration, security, performance, and user acceptance.',
        'Deploy safely, document operations, and complete knowledge transfer.',
    ]
    milestones = []
    for index, (name, objective, weight) in enumerate(zip(phase_names, objectives, weights)):
        duration = max(0.5, round(total * weight, 1))
        milestones.append({
            'name': name,
            'objective': objective,
            'deliverables': [
                ', '.join(features[:10]) if index == 2 else f'{name} acceptance evidence'
            ],
            'dependencies': [] if index == 0 else [phase_names[index - 1]],
            'estimated_duration_weeks': duration,
        })
    risks = [
        {
            'risk': 'Scope growth',
            'likelihood': 'medium',
            'impact': 'high',
            'mitigation': 'Prioritize requirements and require change-impact review.',
        },
        {
            'risk': 'Integration uncertainty',
            'likelihood': 'medium',
            'impact': 'medium',
            'mitigation': 'Prototype high-risk integrations early and use contract tests.',
        },
    ]
    if deadline_weeks and sum(item['estimated_duration_weeks'] for item in milestones) > deadline_weeks + 0.5:
        risks.append({
            'risk': 'Timeline compression',
            'likelihood': 'high',
            'impact': 'high',
            'mitigation': 'Reduce scope, add parallel capacity, or renegotiate the deadline.',
        })
    return {
        'milestones': milestones,
        'risks': risks,
        'assumptions': [
            'Required stakeholders are available for timely review.',
            'External service access is available before integration work begins.',
        ],
        'constraints': constraints,
        'estimated_total_weeks': round(sum(item['estimated_duration_weeks'] for item in milestones), 1),
    }


def planning_tools():
    return [
        StructuredTool.from_function(
            generate_roadmap,
            name='generate_project_roadmap',
            description='Generate development phases, milestones, dependencies, risks, and assumptions for known features.',
            args_schema=RoadmapInput,
        )
    ]
