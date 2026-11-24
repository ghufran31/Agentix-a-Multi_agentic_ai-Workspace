from typing import NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from orchestrator.core.execution_context import ExecutionContext
from orchestrator.core.plan_schemas import (
    PlannedTask, PlannerDecision, TaskResult,
)
from orchestrator.core.plan_validator import PlanLimits
from orchestrator.core.specialist_dispatch import real_capabilities

from .approvals import approval_node
from .planner import planning_node
from .state import (
    PersistentInput, PersistentState, IntegratedInput, IntegratedState, PlanningInput, PlanningState, SupervisorInput, SupervisorState,
)
from .nodes import begin_turn, execute_task, finish_turn, initialize_turn
from .scheduling import route_tasks, schedule_tasks


class WorkerInput(TypedDict):
    task: PlannedTask
    prerequisites: dict[str, TaskResult]
    approval: NotRequired[dict]
    thread_id: NotRequired[str | None]
    execution_id: NotRequired[str | None]


def build_planning_graph(registry, *, limits=PlanLimits(), planner=None):
    """Planning-only entry point. All validated outcomes terminate before dispatch."""
    graph = StateGraph(PlanningState, input_schema=PlanningInput, context_schema=ExecutionContext)
    graph.add_node('plan_turn', planning_node(registry, limits, planner))
    graph.add_edge(START, 'plan_turn')
    graph.add_edge('plan_turn', END)
    return graph.compile()


def build_graph(registry, *, limits=PlanLimits()):
    """Compile a reusable mock executor. The caller provides trusted runtime context."""
    return _build_execution_graph(registry, limits)


def build_integrated_graph(registry, *, planner=None, limits=PlanLimits(), mode='mock'):
    """Compile conversational execution. Real adapters require explicit opt-in."""
    if mode not in {'mock', 'real'}:
        raise ValueError('Execution mode must be mock or real.')
    if (mode == 'mock' or planner is not None) and not callable(getattr(planner, 'invoke', None)):
        raise ValueError('Phase 03 requires an explicit mock planner with an invoke method.')
    return _build_execution_graph(registry, limits, planner, mode=mode)


def build_persistent_graph(registry, *, checkpointer, mode='mock', planner=None,
                           limits=PlanLimits(), approval_ttl=900):
    if checkpointer is None or mode not in {'mock', 'real', 'planning'}:
        raise ValueError('A checkpointer and supported mode are required.')
    if mode == 'mock' and not callable(getattr(planner, 'invoke', None)):
        raise ValueError('Mock mode requires an injected planner.')
    if not 0 < approval_ttl <= 86400:
        raise ValueError('Approval lifetime must be between zero and 86400 seconds.')
    return _build_execution_graph(registry, limits, planner, mode=mode,
                                  checkpointer=checkpointer, approval_ttl=approval_ttl)


def _build_execution_graph(registry, limits, planner=None, *, mode=None,
                           checkpointer=None, approval_ttl=900):
    integrated = mode is not None
    real = mode == 'real'
    persistent = checkpointer is not None
    approvals = persistent and mode in ('mock', 'real')
    state_schema = PersistentState if persistent else IntegratedState if integrated else SupervisorState

    def initialize(state: SupervisorInput, runtime: Runtime[ExecutionContext]):
        initialized = initialize_turn(
            state, runtime, registry, limits,
            integrated=integrated, real=real,
            persistent=persistent, approvals=approvals,
        )
        if integrated and initialized['errors']:
            initialized['plan'] = None
            initialized['decision'] = PlannerDecision(
                outcome='planning_error',
                response=f'The proposed plan cannot run in {mode} mode.',
            )
        return initialized

    def schedule(state: SupervisorState, runtime: Runtime[ExecutionContext]):
        return schedule_tasks(
            state, runtime, registry,
            approvals=approvals, approval_ttl=approval_ttl,
        )

    def execute(state: WorkerInput, runtime: Runtime[ExecutionContext]):
        return execute_task(
            state, runtime, registry,
            persistent=persistent, real=real, approvals=approvals,
        )

    def finish(state: SupervisorState):
        return finish_turn(state, integrated=integrated, mode=mode)

    graph = StateGraph(
        state_schema,
        input_schema=PersistentInput if persistent else IntegratedInput if integrated else SupervisorInput,
        context_schema=ExecutionContext,
    )
    graph.add_node('validate', initialize, input_schema=state_schema if integrated else SupervisorInput)
    graph.add_node('schedule', schedule, input_schema=state_schema)
    graph.add_node('execute', execute)
    graph.add_node('finish', finish, input_schema=state_schema)
    if integrated:
        graph.add_node('plan_turn', planning_node(
            registry, limits, planner, execute_mock=mode != 'planning',
            allow_approvals=approvals, use_previous_results=persistent,
            capability_filter=real_capabilities if real else None,
            remember_request=persistent and real,
        ))
        if persistent:
            graph.add_node('begin_turn', begin_turn)
            graph.add_edge(START, 'begin_turn')
            graph.add_edge('begin_turn', 'plan_turn')
        else:
            graph.add_edge(START, 'plan_turn')
        graph.add_conditional_edges(
            'plan_turn', lambda state: state['decision'].outcome,
            {outcome: 'validate' if outcome == 'plan' and mode != 'planning' else END for outcome in (
                'direct_response', 'plan', 'clarification', 'unsupported', 'planning_error',
            )},
        )
    else:
        graph.add_edge(START, 'validate')
    graph.add_edge('validate', 'schedule')
    destinations = ['execute', 'finish']
    if approvals:
        graph.add_node('approval_gate', approval_node(registry))
        graph.add_edge('approval_gate', 'schedule')
        destinations.append('approval_gate')
    graph.add_conditional_edges('schedule', route_tasks, destinations)
    graph.add_edge('execute', 'schedule')
    graph.add_edge('finish', END)
    steps = 2 * limits.max_depth + (8 if integrated else 6)
    if persistent:
        steps += 1 + 4 * limits.max_tasks
    return graph.compile(checkpointer=checkpointer).with_config(recursion_limit=steps)
