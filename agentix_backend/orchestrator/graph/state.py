from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import JsonValue

from orchestrator.core.plan_schemas import (
    ExecutionError, ExecutionPlan, ExecutionSummary, PlannerDecision, TaskResult, TaskStatus,
)


def merge_task_results(left, right):
    if left.keys() & right.keys():
        raise ValueError('A task produced more than one terminal result.')
    return {**left, **right}


class SupervisorInput(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    request: str
    project_id: int | None
    project_requirements: dict[str, JsonValue]
    plan: ExecutionPlan


class SupervisorState(SupervisorInput):
    user_id: int
    company_id: int
    task_statuses: dict[str, TaskStatus]
    results: Annotated[dict[str, TaskResult], merge_task_results]
    pending_approvals: list[dict[str, JsonValue]]
    errors: list[ExecutionError]
    final_response: str
    metadata: dict[str, JsonValue]
    order: tuple[str, ...]
    ready: list[str]


class PlanningInput(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    request: str
    project_id: int | None
    project_requirements: dict[str, JsonValue]
    results: Annotated[dict[str, TaskResult], merge_task_results]


class PlanningState(PlanningInput):
    decision: PlannerDecision
    plan: ExecutionPlan | None
    errors: list[ExecutionError]
    final_response: str
    metadata: dict[str, JsonValue]
    user_id: int
    company_id: int


class IntegratedInput(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    request: str
    project_id: int | None
    project_requirements: dict[str, JsonValue]
    previous_results: dict[str, TaskResult]


class IntegratedState(SupervisorState):
    previous_results: dict[str, TaskResult]
    decision: PlannerDecision
    execution_summary: ExecutionSummary | None


class PersistentInput(IntegratedInput):
    execution_id: str
    thread_id: str


class PersistentState(IntegratedState):
    execution_id: str
    thread_id: str
    approval_records: dict[str, dict[str, JsonValue]]
    pending_request: dict[str, JsonValue] | None
