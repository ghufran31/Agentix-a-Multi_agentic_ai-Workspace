from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_.-]+$')]
TaskStatus = Literal['pending', 'running', 'done', 'failed', 'blocked']


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class OutputRef(Contract):
    task_id: Identifier
    field: Identifier


class PlannedTask(Contract):
    task_id: Identifier
    capability: Identifier
    description: str = Field(min_length=1, max_length=1000)
    inputs: dict[str, JsonValue] = Field(default_factory=dict, max_length=32)
    references: dict[str, OutputRef] = Field(default_factory=dict, max_length=32)
    depends_on: list[Identifier] = Field(default_factory=list, max_length=64)


class ExecutionPlan(Contract):
    goal: str = Field(min_length=1, max_length=1000)
    tasks: list[PlannedTask] = Field(min_length=1, max_length=64)


class ExecutionError(Contract):
    code: str
    message: str


class TaskResult(Contract):
    task_id: Identifier
    agent: Identifier
    capability: Identifier
    status: Literal['done', 'failed', 'blocked']
    output: dict[str, JsonValue] | None = None
    error: ExecutionError | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_terminal_state(self):
        if self.status == 'done':
            if self.output is None or self.error is not None:
                raise ValueError('Completed tasks require output and no error.')
        elif self.error is None or self.output is not None:
            raise ValueError('Failed and blocked tasks require an error and no output.')
        return self


class PlannerDecision(Contract):
    outcome: Literal['direct_response', 'plan', 'clarification', 'unsupported', 'planning_error']
    response: str = Field(min_length=1, max_length=4000)
    plan: ExecutionPlan | None = None

    @model_validator(mode='after')
    def check_plan(self):
        if (self.outcome == 'plan') != (self.plan is not None):
            raise ValueError('Only the plan outcome carries an execution plan.')
        return self


class ExecutionSummary(Contract):
    request: str
    goal: str
    plan: ExecutionPlan
    status: Literal['done', 'partial', 'failed']
    completed: list[TaskResult]
    failed: list[TaskResult]
    blocked: list[TaskResult]
    errors: list[ExecutionError]
