# Supervisor Phase 01

`orchestrator.graph.builder.build_graph(registry, limits=...)` compiles a
reusable LangGraph for server-supplied mock plans. Reuse the returned runnable
across requests and supply a new state and trusted context on every invocation.

| State area | Fields |
| --- | --- |
| Request | `messages`, `request`, `project_id`, `project_requirements`, `plan` |
| Identity | `user_id` and `company_id`, copied from trusted runtime context |
| Execution | `task_statuses`, `results`, `pending_approvals`, `errors`, `metadata`, `final_response` |
| Scheduler | `order` and `ready` |

Create `ExecutionContext.from_django(...)` with an authenticated, server-resolved
company context and server-owned capability and permission allowlists. The plan
cannot choose its identity or grant permissions. The graph has no checkpoint
store. The caller owns conversation history and authorizes any project data
included in the input.

## Registration

Each `AgentRegistry` entry defines an agent ID, name, and description. Each
`Capability` defines unique name, Pydantic inputs and outputs, required
permissions, approval requirement, and optional mock executor. Register
additional instances using `AgentRegistry.register(Agent(...))` without editing
the graph. `visible(context)` exposes only allowed capabilities whose permissions
are present and which need no approval. Metadata without a mock cannot execute.

| Initial capability | Input → output |
| --- | --- |
| `database.get_project` | `ProjectIdInput` → `DatabaseAgentResult` |
| `project.plan` | `PlanningInput` → `ProjectAgentResult` |
| `matching.rank` | `MatchingRequest` → `MatchingAgentResult` |
| `research.search` | `ResearchRequest` → `ResearchResult` |

`specialist_registry()` registers metadata only. For tests, pass a capability
name to mock callable mapping to `specialist_registry`. Each mock receives
validated inputs, copies of its direct dependency results, and the runtime
context. Return valid output or raise to signal failure. See the
[specialist contracts](../orchitecture_agent_docs/README.md).

## Validation and execution

`ExecutionPlan` contains a goal and tasks with ID, capability, description,
literal inputs, dependencies, and optional field references. A reference maps
an input field to an exact `{task_id, field}` on a direct prerequisite's declared
top-level output. The graph checks simple incompatible JSON types up front and
validates the complete resolved input before invoking the mock. Values are
read from validated results. Nested paths are outside this phase.

Plans reject unknown or unauthorized capabilities, unsupported approvals,
missing or duplicate dependencies, duplicate task IDs, cycles, invalid inputs
and references, and excess task count or depth. Defaults are 32 tasks and
12 dependency levels. The hard task limit is 64.

`validate → schedule → Send(execute…) → schedule → finish`. Each scheduling
wave marks ready tasks running before dispatch. Workers publish only a
task-keyed result. The reducer merges disjoint result keys, and the scheduler
updates statuses once the wave joins. Failed or blocked prerequisites block
downstream work while independent tasks can finish. Each terminal
`TaskResult` identifies the task, agent, and capability and contains validated
JSON output or an error. Executed tasks include elapsed time.

Run `python manage.py test orchestrator.test_graph_foundation` from
`agentix_backend`. Concurrency tests use a thread barrier to prove overlap.
All 20 focused tests passed. The full orchestrator run passed 73 tests
on process-local SQLite, including 55 existing regressions and the first
18 foundation tests. The final focused run covered the two added tests.
Real planning, dispatch, approvals, persistence, streaming, and UI remain
outside Phase 01.
