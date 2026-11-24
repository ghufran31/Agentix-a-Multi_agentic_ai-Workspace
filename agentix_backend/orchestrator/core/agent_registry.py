from dataclasses import dataclass, replace
from datetime import date
from typing import Callable, Mapping

from pydantic import BaseModel, Field, JsonValue, field_validator, model_validator

from orchestrator.agents.database.schemas import DatabaseAgentResult
from orchestrator.agents.matching.schemas import MatchingAgentResult, MatchingRequest
from orchestrator.agents.project.schemas import (
    ProjectAgentOutput,
    ProjectAgentResult,
    ProjectSpecification,
    parse_iso_deadline,
)
from orchestrator.agents.research.schemas import ResearchRequest, ResearchResult
from orchestrator.tools.database.project_tools import ProjectIdInput
from .execution_context import ExecutionContext
from .plan_schemas import Contract, TaskResult

MockExecutor = Callable[[BaseModel, Mapping[str, TaskResult], ExecutionContext], BaseModel]


class PlanningInput(Contract):
    task: str = Field(min_length=1, max_length=4000)
    explicit_deadline: str | None = Field(
        default=None, pattern=r'^\d{4}-\d{2}-\d{2}$',
    )

    @field_validator('explicit_deadline', mode='before')
    @classmethod
    def validate_explicit_deadline(cls, value):
        if value is not None:
            parse_iso_deadline(value)
        return value


class ProjectCreateInput(Contract):
    specification: JsonValue
    top_n: int = Field(default=5, ge=1, le=25)
    trusted_deadline: str | None = Field(
        default=None, pattern=r'^\d{4}-\d{2}-\d{2}$',
    )

    @field_validator('trusted_deadline', mode='before')
    @classmethod
    def validate_trusted_deadline(cls, value):
        if value is not None:
            parse_iso_deadline(value)
        return value

    @model_validator(mode='after')
    def validate_project_specification(self):
        if isinstance(self.specification, dict) and 'outcome' in self.specification:
            output = ProjectAgentOutput.model_validate(self.specification, strict=True)
            if output.outcome != 'specification' or output.specification is None:
                raise ValueError('Project creation requires a validated specification.')
            specification = output.specification
        else:
            specification = ProjectSpecification.model_validate(self.specification, strict=True)
        specification_deadline = (
            specification.deadline.isoformat() if specification.deadline else None
        )
        if specification_deadline != self.trusted_deadline:
            raise ValueError('The specification deadline must match the trusted user deadline.')
        return self


class ProjectCreateOutput(Contract):
    project_id: int
    name: str
    description: str | None = None
    deadline: date | None = None
    specification: JsonValue | None = None
    requirements_created: int = Field(ge=0)
    matched_skills: list[str] = Field(default_factory=list)
    unresolved_skills: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    duplicate_recovered: bool = False

    @field_validator('deadline', mode='before')
    @classmethod
    def validate_deadline(cls, value):
        return parse_iso_deadline(value)


@dataclass(frozen=True)
class Capability:
    name: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    permissions: frozenset[str] = frozenset()
    approval_required: bool = False
    mock_executor: MockExecutor | None = None
    real_adapter: Callable | None = None


@dataclass(frozen=True)
class Agent:
    identifier: str
    name: str
    description: str
    capabilities: tuple[Capability, ...]


class AgentRegistry:
    def __init__(self):
        self._agents = {}
        self._capabilities = {}

    def register(self, agent: Agent):
        names = [capability.name for capability in agent.capabilities]
        if (agent.identifier in self._agents or len(set(names)) != len(names)
                or any(name in self._capabilities for name in names)):
            raise ValueError('Duplicate agent or capability')
        self._agents[agent.identifier] = agent
        self._capabilities.update({cap.name: (agent, cap) for cap in agent.capabilities})

    def lookup(self, name: str):
        return self._capabilities[name]

    def bind_real_adapter(self, name: str, adapter: Callable):
        agent, capability = self._capabilities[name]
        updated = replace(capability, real_adapter=adapter)
        self._capabilities[name] = (agent, updated)
        replacement = tuple(
            updated if item.name == name else item
            for item in agent.capabilities
        )
        self._agents[agent.identifier] = replace(agent, capabilities=replacement)

    def visible(self, context: ExecutionContext, *, allow_approvals=False):
        return {
            name: (agent, cap) for name, (agent, cap) in self._capabilities.items()
            if name in context.allowed_capabilities and cap.permissions <= context.permissions
            and (allow_approvals or not cap.approval_required)
        }


def specialist_registry(mock_executors: Mapping[str, MockExecutor] | None = None):
    """Declare a scoped subset of capabilities. No live adapters are installed."""
    registry = AgentRegistry()
    mock_executors = dict(mock_executors or {})
    for agent in (
        Agent('database', 'Database', 'Company-scoped Django ORM tools', (
            Capability('database.get_project', ProjectIdInput, DatabaseAgentResult,
                       frozenset({'projects.read'})),
            Capability('database.create_project', ProjectCreateInput, ProjectCreateOutput,
                       frozenset({'projects.write'}), approval_required=True),
        )),
        Agent('project', 'Project Planning', 'Structured proposals and clarification', (
            Capability('project.plan', PlanningInput, ProjectAgentResult),
        )),
        Agent('matching', 'Employee Matching', 'Saved-project employee ranking', (
            Capability('matching.rank', MatchingRequest, MatchingAgentResult,
                       frozenset({'projects.read', 'workforce.read'})),
        )),
        Agent('research', 'Research', 'Public web research and evidence', (
            Capability('research.search', ResearchRequest, ResearchResult),
        )),
    ):
        capabilities = tuple(
            replace(capability, mock_executor=mock_executors.pop(capability.name, None))
            for capability in agent.capabilities
        )
        registry.register(replace(agent, capabilities=capabilities))
    if mock_executors:
        raise ValueError('Mock executor registered for an unknown capability.')
    return registry
