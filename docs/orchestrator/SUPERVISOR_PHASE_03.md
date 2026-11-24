# Supervisor Phase 03

Use `build_integrated_graph(registry, planner=mock_planner)` from
`orchestrator.graph.builder`. Compile once and invoke with a new request and
server-owned `ExecutionContext`. Supply an explicit mock planner and bind
mock executors to capabilities in the registry.

The graph begins with the Phase 02 decision node. Direct replies,
clarifications, unsupported requests and planning errors terminate there.
Only a plan that passes both planning validation and mock execution
preflight can reach the Phase 01 scheduler. A missing mock binding,
unauthorized capability, or approval requirement rejects the plan before
any task runs. `build_planning_graph()` remains the inspection-only entry
point. `build_graph()` still accepts server-supplied mock plans.

## State and execution

- Input accepts `request`, optional conversation `messages`, authorized
  `project_id` and `project_requirements`, and `previous_results`.
- History remains separate from the current `results` map, so task IDs can
  repeat across turns without reusing old results. Only current-plan direct
  prerequisites can supply referenced fields.
- The scheduler marks ready tasks running before dispatch. LangGraph
  `Send` runs independent tasks concurrently. Workers validate resolved
  inputs and outputs and publish one result keyed by task ID. The reducer
  rejects duplicate terminal results. The scheduler joins the wave before
  dispatching downstream work.
- An executor signals failure by raising. Invalid output also fails the task.
  Dependent tasks are blocked, and independent tasks continue. There is no
  automatic retry. Plan size, dependency depth, and graph step limits bound
  the number of tasks and scheduling waves.

## Observation

Executed plans produce an `ExecutionSummary` containing the original request,
plan goal, validated plan, status (`done`, `partial`, or `failed`), grouped
completed, failed, and blocked task results, and errors. Complete structured
outputs remain in the summary and current result map. The final assistant
message is formatted in plan order from those results, with bounded output
previews. No model call is used to summarize execution.

Run `python manage.py test orchestrator.test_integrated_graph` from
`agentix_backend`. Tests prove actual overlap with a thread barrier and cover
fan-in, output references, invalid and unauthorized plans, approval
rejection, history isolation, failure propagation, and termination.

All 10 integrated tests and the 33 Phase 01 and Phase 02 tests passed.
The complete orchestrator suite passed all 98 tests using process-local
SQLite. Django system checks and Git diff hygiene passed. The run made no
LLM provider calls or writes to PostgreSQL.

This phase verifies the integrated control flow with mocks. Real agent
adapters still need authorization and outcome mapping before live dispatch.
OpenRouter planning remains unverified after the Phase 02 rate limit. Mock
executors are expected to return promptly; the graph does not forcibly
interrupt a hanging callable. There is no persistence, approvals UI, or
frontend.
