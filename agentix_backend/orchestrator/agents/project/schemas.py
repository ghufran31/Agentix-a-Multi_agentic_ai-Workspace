from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


RequirementSource = Literal['user', 'recommended', 'assumed']
Priority = Literal['must', 'should', 'could']


class ProjectFeature(StrictModel):
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(min_length=1, max_length=1000)
    priority: Priority = 'should'
    source: RequirementSource = 'user'


class FunctionalRequirement(StrictModel):
    identifier: str = Field(pattern=r'^FR-[0-9]{3}$')
    description: str = Field(min_length=1, max_length=2000)
    related_features: list[str] = Field(default_factory=list, max_length=25)
    priority: Priority = 'must'
    source: RequirementSource = 'user'


class NonFunctionalRequirement(StrictModel):
    category: Literal[
        'security', 'performance', 'availability', 'scalability',
        'usability', 'maintainability', 'compatibility', 'compliance', 'other',
    ]
    description: str = Field(min_length=1, max_length=2000)
    measurable_target: str | None = Field(default=None, max_length=500)
    source: RequirementSource = 'recommended'


class TechnologyChoice(StrictModel):
    layer: Literal[
        'frontend', 'mobile', 'backend', 'database', 'cache', 'messaging',
        'infrastructure', 'testing', 'monitoring', 'other',
    ]
    name: str = Field(min_length=1, max_length=150)
    purpose: str = Field(min_length=1, max_length=500)
    rationale: str = Field(min_length=1, max_length=1000)
    source: Literal['user_required', 'recommended'] = 'recommended'
    alternatives: list[str] = Field(default_factory=list, max_length=10)


class TechnologyStack(StrictModel):
    choices: list[TechnologyChoice] = Field(min_length=1, max_length=30)
    architecture_style: str = Field(min_length=1, max_length=300)
    notes: list[str] = Field(default_factory=list, max_length=20)


class RequiredSkill(StrictModel):
    name: str = Field(min_length=1, max_length=150)
    category: str = Field(min_length=1, max_length=100)
    roles: list[str] = Field(default_factory=list, max_length=20)
    taxonomy_status: Literal['existing', 'proposed'] = 'proposed'
    existing_skill_id: int | None = Field(default=None, gt=0)

    @model_validator(mode='after')
    def existing_skill_has_id(self):
        if self.taxonomy_status == 'existing' and self.existing_skill_id is None:
            raise ValueError('An existing skill must include existing_skill_id.')
        if self.taxonomy_status == 'proposed' and self.existing_skill_id is not None:
            raise ValueError('A proposed skill cannot include existing_skill_id.')
        return self


class RequiredRole(StrictModel):
    name: str = Field(min_length=1, max_length=150)
    responsibilities: list[str] = Field(min_length=1, max_length=20)
    skills: list[str] = Field(min_length=1, max_length=30)
    suggested_count: int = Field(default=1, ge=1, le=100)


class Milestone(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=1000)
    deliverables: list[str] = Field(min_length=1, max_length=25)
    dependencies: list[str] = Field(default_factory=list, max_length=20)
    estimated_duration_weeks: float = Field(gt=0, le=260)


class ProjectConstraint(StrictModel):
    category: Literal['technology', 'timeline', 'budget', 'scope', 'legal', 'other']
    description: str = Field(min_length=1, max_length=1000)
    source: Literal['user', 'inferred'] = 'user'


class ProjectAssumption(StrictModel):
    description: str = Field(min_length=1, max_length=1000)
    impact_if_false: str = Field(min_length=1, max_length=1000)


class ProjectRisk(StrictModel):
    description: str = Field(min_length=1, max_length=1000)
    likelihood: Literal['low', 'medium', 'high']
    impact: Literal['low', 'medium', 'high']
    mitigation: str = Field(min_length=1, max_length=1000)


class MissingInformation(StrictModel):
    field: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=500)
    impact: str = Field(min_length=1, max_length=1000)
    essential: bool = False


class ProjectSpecification(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=5000)
    project_type: str = Field(min_length=1, max_length=150)
    features: list[ProjectFeature] = Field(min_length=1, max_length=100)
    functional_requirements: list[FunctionalRequirement] = Field(
        min_length=1, max_length=150
    )
    nonfunctional_requirements: list[NonFunctionalRequirement] = Field(
        default_factory=list, max_length=100
    )
    technology_stack: TechnologyStack
    required_roles: list[RequiredRole] = Field(min_length=1, max_length=50)
    required_skills: list[RequiredSkill] = Field(min_length=1, max_length=100)
    milestones: list[Milestone] = Field(min_length=1, max_length=50)
    constraints: list[ProjectConstraint] = Field(default_factory=list, max_length=50)
    assumptions: list[ProjectAssumption] = Field(default_factory=list, max_length=50)
    risks: list[ProjectRisk] = Field(default_factory=list, max_length=50)
    missing_information: list[MissingInformation] = Field(default_factory=list, max_length=50)
    limitations: list[str] = Field(default_factory=list, max_length=30)


class ClarificationOutcome(StrictModel):
    understood_request: str = Field(min_length=1, max_length=3000)
    questions: list[MissingInformation] = Field(min_length=1, max_length=10)
    retained_requirements: list[str] = Field(default_factory=list, max_length=100)


class ProjectAgentOutput(StrictModel):
    outcome: Literal['specification', 'clarification', 'unsupported']
    response: str = Field(min_length=1, max_length=10000)
    specification: ProjectSpecification | None = None
    clarification: ClarificationOutcome | None = None
    persistence_performed: bool = False

    @model_validator(mode='after')
    def validate_outcome(self):
        if self.persistence_performed:
            raise ValueError('The Project Agent cannot perform persistence.')
        if self.outcome == 'specification' and self.specification is None:
            raise ValueError('A specification outcome requires specification data.')
        if self.outcome == 'clarification' and self.clarification is None:
            raise ValueError('A clarification outcome requires clarification data.')
        if self.outcome != 'specification' and self.specification is not None:
            raise ValueError('Only a specification outcome may contain a specification.')
        if self.outcome != 'clarification' and self.clarification is not None:
            raise ValueError('Only a clarification outcome may contain clarification data.')
        return self


class PlanningToolExecution(StrictModel):
    name: str
    input: dict = Field(default_factory=dict)
    output: dict = Field(default_factory=dict)


class ProjectAgentResult(StrictModel):
    answer: str
    success: bool = True
    structured_output: ProjectAgentOutput | None = None
    tool_names: list[str] = Field(default_factory=list)
    tool_executions: list[PlanningToolExecution] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    model_calls: int = Field(default=0, ge=0)
    model_requests: int = Field(default=0, ge=0)
