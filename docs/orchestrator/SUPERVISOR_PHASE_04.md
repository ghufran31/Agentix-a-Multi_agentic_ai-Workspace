# Supervisor Phase 04

Use `build_integrated_graph(specialist_registry(), mode='real')` for explicit
real execution. The default remains `mode='mock'`, which requires an explicit
mock planner and registered mock executors. For controlled integration runs,
real mode can take an injected planner to test dispatch without using the
configured Supervisor model. Planning-only and Phase 01 entry points remain.

| Real capability | Input | Adapter and validated result |
| --- | --- | --- |
| `database.get_project` | `ProjectIdInput` | Invoke only the existing scoped `get_project` tool. Wrap its `ToolExecutionResult` in `DatabaseAgentResult`. |
| `matching.rank` | `MatchingRequest` | Invoke only `rank_project_employees`. Validate `MatchingResponse`, then wrap it in `MatchingAgentResult`. |
| `project.plan` | `PlanningInput` | Call `execute_project_task(None, task)` for general planning, without company taxonomy access. A valid specification is a successful `ProjectAgentResult`. |
| `research.search` | `ResearchRequest` | Call `execute_research(question)`. Accept an `ok` or `partial` `ResearchResult` with findings grounded in returned source URLs. |

Database and Matching call deterministic tools and consume no LLM tokens.
Project and Research use the existing specialist model settings. The
Supervisor does not pass predecessor payloads into specialists implicitly.
Validated references populate only the fields explicitly declared by the plan.

## Authorization and failure handling

Build `ExecutionContext` on the server from an authenticated Django caller
and authorized company. Real mode filters the planner catalog to the approved
capability contracts. Preflight checks permissions and rejects the whole plan
if any capability has no matching real adapter or requires approval.
The worker rechecks capability permissions and resolves an active Django
user and company membership immediately before calling the specialist.
Database and Matching receive a fresh read-only Django context and continue
to scope project and employee queries inside their own tools.

Outputs are revalidated before publication. Missing projects, insufficient
planning outcomes, unavailable research, provider errors, timeouts, and
invalid output produce structured failures. Dependent tasks are blocked and
independent work continues. Real mode never retries via mock execution.
Usage included by specialists is retained in task metadata when available.

Provider timeouts rely on the existing client settings. The synchronous
graph does not forcibly interrupt running ORM queries or XGBoost inference.
There are no write adapters, approval interrupts, persistent sessions, or UI.

Run `python manage.py test orchestrator.test_real_dispatch` from
`agentix_backend` against an isolated Django test database. Tests include
real scoped ORM reads and XGBoost inference on fixtures, alongside mocked
network boundaries and parallel/dependent dispatch.

## Verification

All nine adapter tests and all 107 orchestrator tests passed on isolated,
in-memory SQLite. Django checks and Git diff hygiene passed.

Two controlled integration runs used an injected planner, so no OpenRouter
requests were made. Project lookup and ranking both succeeded on disposable
fixtures with no LLM use. Employee IDs 2 and 1 scored 0.2738877534866333 and
0.14778979122638702, respectively. The Python-documentation research turn
returned `research_failed` because there were no validated findings. It
reported two Groq responses using `openai/gpt-oss-120b`, 1,734 tokens, and
one Tavily request using one credit. No citations were published. The
Research happy path was subsequently verified during stabilization.

## Stabilization verification

A traced replay of the Python documentation request showed five successful
Tavily results and a successful read redirected to `https://docs.python.org/3/`.
The next Groq tool-enabled request returned HTTP 400 `tool_use_failed` before
a summary reached Pydantic. Mocked tests separately reproduced rejection of
a citation that omitted the root slash and imprecise parser diagnostics.

Research now hands off after a successful page retrieval to one separate
structured synthesis call without research tools. The synthesis uses up to
eight observed excerpts and prefers fetched pages. Every citation must match
evidence sent to synthesis. A bare origin URL can match the observed root
with a trailing slash, and the final citation uses the exact observed URL.
Paths, query strings, fragments, and schemes still require exact matches.
The adapter preserves allowlisted failure codes without exposing provider
bodies.

| Stabilization run | Outcome | Groq | Tavily |
| --- | --- | --- | --- |
| Research diagnostic | HTTP 400 `tool_use_failed` after successful search and page read | 2 responses, 1 rejected request, 1,734 reported tokens | 1 request, 1 credit |
| Research retest | Done with a validated citation to `https://docs.python.org/` | 3 responses, 3,678 tokens | 1 request, 1 credit |
| Project specification | `project_planning_failed`, no validated specification returned | Agent reported 3 requests and 2 responses, 5,447 observed tokens | None |

The Project adapter passed a full mocked test through the Supervisor with
a validated specification and no persistence. Live Project verification
remains incomplete. All 112 orchestrator tests passed on in-memory SQLite
and all 22 focused tests passed. Django checks and `git diff --check` passed.
The live runs used an injected Supervisor planner and mocked the membership
lookup. No OpenRouter requests or database writes were made during those runs.
