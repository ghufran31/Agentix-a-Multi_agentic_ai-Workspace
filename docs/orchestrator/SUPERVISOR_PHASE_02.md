# Supervisor Phase 02

Use `build_planning_graph(specialist_registry())` from
`orchestrator.graph.builder`. Compile it once and invoke it with
`request`, optional `messages`, `project_id`, `project_requirements`, and
previous `results`, plus an `ExecutionContext` supplied as LangGraph runtime
context. The caller must authorize the project and all history it supplies.

The graph appends the current user and assistant messages, preserves previous
results, and ends after one planning node. The original Phase 01
`build_graph()` remains the entry point for mock task execution.

| `PlannerDecision.outcome` | Meaning |
| --- | --- |
| `direct_response` | Conversation or capability explanation |
| `plan` | Validated `ExecutionPlan` available for inspection |
| `clarification` | Essential information is missing |
| `unsupported` | Request exceeds available capabilities |
| `planning_error` | Provider, parsing, or validation failure |

All outcomes have a `response`. Only `plan` carries a plan. The state also
returns `final_response`, structured `errors`, and `metadata` with invocation
and response counts, model name, and usage when available.

The prompt sees the authorized capability catalog and each input schema.
Server validation applies the Phase 01 limits, authorization rules, and
dependency checks. Independent tasks omit dependencies. A task may reference
a declared top-level output from a direct prerequisite. Previous turn results
are preserved, but only recent task IDs, capability names, and statuses go
into the model prompt. They cannot be referenced as inputs to the new plan.
Project lookup and matching use the caller's authorized current project ID.

The factory uses `SUPERVISOR_LLM_PROVIDER` and `SUPERVISOR_LLM_MODEL` from
Django settings. The configured OpenRouter route uses tool-backed structured
output and local Pydantic validation. Groq uses its existing structured output
path. There is no automatic paid fallback or planner retry.

Run `python manage.py test orchestrator.test_supervisor_planner
orchestrator.test_graph_foundation` from `agentix_backend`. See
[Phase 01](SUPERVISOR_PHASE_01.md) for the mock execution contracts.

Phase 02 plans are proposals only. Phase 03 can consume validated plans once
real dispatch and result validation are implemented. The planner does not
persist history, run specialists, or ask for approval decisions.

## Verification

The 13 Phase 02 tests and 20 Phase 01 tests passed. The combined orchestrator
suite passed all 88 tests on in-memory SQLite, including 55 existing
regressions. Django checks and diff hygiene passed.

The single-agent e-commerce plan request used `openrouter/free` and returned
HTTP 429. The graph returned `planning_error` with code `rate_limited` and
no plan. One request was attempted and no model response, routed model, or
token usage was reported. The dependent project lookup and matching scenario
was skipped after the rate limit. Both plan shapes passed the offline tests.
Live planning still needs verification before relying on it in Phase 03.
