# Development log

## 2026-11-23 — Dokploy production deployment preparation

Added an ARM64-targeted Django and PostgreSQL/pgvector Compose stack, an
isolated production settings profile, persistent checkpoint provisioning,
and an operations guide. See the [Dokploy deployment guide](deployment/DOKPLOY.md).

## 2026-11-22 — Groq Supervisor root structured-output failure

Recovered a root Pydantic `model_type` error from the failed Flutter
checkpoint. Changed the Groq Supervisor response format to one typed
function call and added safe parser-stage diagnostics. See
[the provider guide](orchestrator/LLM_PROVIDERS.md#supervisor-groq-structured-decision-troubleshooting).

## 2026-11-22 — Supervisor clarification continuity

Preserved the original request and user-provided deadlines in real
conversation checkpoints. Kept project approval on the authenticated graph
interrupt and retained safe plan-validation details in checkpoints.
See [multi-turn deadlines and approval](orchestrator/SUPERVISOR_PHASE_06.md#multi-turn-deadlines-and-write-approval).

## 2026-11-22 — Disposable Supervisor console write testing

Added an opt-in console write flag with live `test_Agentix` checks on the
ORM, checkpoints and journal. Added project approval review and creation
result projections, prepared five synthetic ranking candidates, and verified
22 workflow and console tests without live providers. See
[the browser test guide](orchestrator/SUPERVISOR_PHASE_06.md#disposable-browser-test-for-project-creation).

## 2026-11-22 — Supervisor invalid-plan diagnostics

The prior single live Supervisor response reached the static plan validator
and returned `invalid_plan`; its proposed plan was not persisted, so the exact
rejected rule cannot be reconstructed. No further provider requests were made.

Static validation now emits server-side structured diagnostics with a stable
rule and error code, and safe task/capability/dependency/reference identifiers
where available. Pydantic failures include bounded field locations and error
types, never input values. Public planning and execution errors remain generic.
The Supervisor prompt now documents the valid
`project.plan → database.create_project → matching.rank` chain and its
top-level output references.

Offline verification confirms that the three-task plan passes real-adapter
planning validation; the Project Agent `structured_output` resolves into the
strict creation schema, the create output's `project_id` resolves into
matching, and the trusted deadline remains `2027-03-30`. Approval capability
visibility and the `projects.write`, `projects.read`, and `workforce.read`
permissions remain enforced.

Verification:
- Full orchestrator suite: 186 tests, 177 passed and 9 skipped.
- Django system checks passed.
- `git diff --check` passed.
- No live provider requests or business database writes were made.

## 2026-11-22 — Single live Supervisor workflow attempt

The Supervisor deadline guard now accepts unambiguous month-name dates and
normalizes them to ISO form; the explicit `March 30, 2027` case is covered by
the planner tests. Before creating fixtures, the live runner forced Django
and checkpoint connections to `test_Agentix` and verified both against the
loopback PostgreSQL server. The repository's default `Agentix` connection was
only inspected read-only.

Exactly one user request was sent to Groq (`openai/gpt-oss-120b`). The
Supervisor returned `planning_error` with `invalid_plan` after one response
(1,808 input tokens, 920 output tokens; finish reason `stop`). The structured
plan failed static validation, but the current planner reports only the
generic code, so the specific rejected constraint and a Pydantic location
were not available. No provider HTTP error or rate-limit diagnostic was
reported. The Project Agent did not run; no approval was reached, no project
or requirements were saved, and matching was not invoked. No retry or second
live request was made.

The temporary owner, company, membership, department, 12 skills, five
employees, profiles, and assignments were removed. Exact-ID checks found no
fixture rows; the run's checkpoint, write, and blob rows were zero, and
project/requirement/receipt totals returned to baseline. Focused planner
regressions passed (19 tests); the previously completed full offline suite
remains 171 passed and 9 skipped.

## 2026-11-22 — Project deadline flow and offline verification

Added an optional ISO date deadline to the Project Agent specification,
validated its calendar value, and instructed the agent never to infer or
invent one. The Supervisor binds the deadline only from an explicit user
request, passes it through Project planning and the approved create input,
and rejects a specification that does not match that trusted date. For a
new project-and-matching request without a valid date, it asks before
dispatching agents or opening a write approval. For existing-project matching,
the date is loaded from the authorized company-scoped project record.
The mapper and approved creation transaction save it to `Project.deadline`;
the date is also included in the approval review and durable idempotency
payload. No business schema or matching features changed.

Verification on disposable PostgreSQL `test_Agentix`:
- Full orchestrator suite: 180 tests run, 171 passed, 9 environment-dependent
  tests skipped.
- Django system checks passed.
- `makemigrations --check --dry-run` reported no changes.
- `git diff --check` passed.
- Approved mock workflow persisted the requested deadline and completed
  matching with the existing XGBoost model.
- Missing and invalid deadlines were clarified before Project Agent
  execution or database writes.
- No live provider calls were made; project, requirement, receipt, and
  checkpoint table counts were zero after the run.

## 2026-11-22 — Project workflow verification

Verified the Supervisor project-creation path on the local, isolated
PostgreSQL `test_Agentix` database. Corrected the approval-required capability
visibility, retained trusted execution identity through the write adapter,
required a matching approval record at real dispatch, accepted the validated
Project Agent output envelope for dependent task references, and enforced
company-scoped skill lookup instead of trusting generated taxonomy claims.
Requested skill and role names are saved only in the approved requirement text
fields; no business schema or matching artifacts changed.

Added PostgreSQL coverage for approval pause/resume/rejection, no pre-approval
write, retry and concurrent duplicate recovery, transaction rollback,
conflicting payloads, capability authorization, matching handoff, and
checkpoint cleanup. The matching handoff reaches the saved project ID, but
the existing matcher refuses inference when `Project.deadline` is absent. The
Project Agent schema and requested scenario provide no explicit deadline, so
no date was synthesized and the real-provider test was not started.

Verification:
- 169 orchestrator tests passed; 9 environment-dependent tests were skipped.
- Django system check passed.
- Migration check and disposable-database migration plan showed no pending
  changes.
- `git diff --check` passed.
- PostgreSQL identity was `test_Agentix` on local loopback; all temporary
  business rows and the test's checkpoint rows were absent after cleanup.
- Zero live LLM requests and zero provider tokens were used.

## 2026-11-22 — Project creation and employee matching workflow

Added `database.create_project` to the Supervisor capability registry with a
Pydantic project specification input and strict creation output. A deterministic
mapper converts supported Project Agent fields into `projects` and
`project_requirements` records. It resolves existing company skills, reports
unresolved skills, and preserves the complete specification in workflow results.

Real persistent execution now supports approval gates. Approval review payloads
show the project name, description, roles, skills, saved fields, and persistence
status. Rejection and expiration block dependent matching.

Added `ProjectCreationReceipt` with a company-plus-operation unique constraint.
The operation identity covers company, thread, execution, and task. The stored
canonical mapping enables duplicate recovery and conflicting-payload rejection.
The project and requirements are committed atomically in the same transaction
as the receipt.

Verification:
- 160 orchestrator tests passed; 9 environment-dependent tests were skipped.
- Django system check passed.
- Migration check reported no pending model changes.
- `git diff --check` passed.
- No real provider call was made during implementation.

## 2026-11-22 — Supervisor simplification refactor

Made the agent registry the source of capability schemas and real adapter
bindings. Removed the duplicated `CONTRACTS` table from real dispatch, added
registry-bound real adapters, and replaced the Project Agent's index-based
tool-result pairing with `tool_call_id` correlation.

Extracted Supervisor initialization, execution, finishing, observation,
scheduling, and routing into dedicated graph modules while preserving the
public builder functions and mock, real, planning, and persistent modes.
Updated the orchestrator architecture documentation.

Verification after the refactor:
- 156 orchestrator tests passed; 9 environment-dependent tests were skipped.
- Django `manage.py check` passed.
- `makemigrations --check --dry-run` reported no changes.
- `git diff --check` passed.
- No migrations or business database writes were added.

The exactly-one live Supervisor preflight did not dispatch an API request.
The isolated PostgreSQL `test_Agentix` database contained no active owner
company membership fixture, and creating such a fixture would have written
business data. The live test was stopped before provider invocation.

## 2026-11-22 — Parallel Project synthesis rejection

Recovered HTTP 413 and Groq `rate_limit_exceeded` from the failed Project
branch of a real parallel run. Preserved that specific classification in the
adapter and console, and reproduced it alongside successful mocked Research.
See the [Project Agent guide](orchestrator/PROJECT_AGENT.md#parallel-flutter-request).

## 2026-11-22 — Project structured-output shape and field diagnostics

Distinguished LangChain response envelopes from bare Project specifications.
Enforced strict scalar validation on first parse and added schema-bounded
location and type diagnostics to logs, checkpoints, and console events.
See the [Project Agent guide](orchestrator/PROJECT_AGENT.md#structured-output-field-diagnostics).

## 2026-11-22 — Project Agent diagnostic propagation

Recovered Pydantic `model_type` and finish reason `stop` from the repeated
Flutter request. The console execution API and new SSE entries now preserve
the safe Project error details from the checkpoint. See the
[Project Agent guide](orchestrator/PROJECT_AGENT.md#repeated-flutter-request).

## 2026-11-22 — Flutter Project Agent validation failure

Recovered the failing live console checkpoint and confirmed the Project
Agent received its model responses before failing output validation. Added
safe parser categories, finish reasons, and console stage reporting.
The historical response shape could not be reconstructed. See the
[Project Agent guide](orchestrator/PROJECT_AGENT.md#flutter-console-failure-diagnosis).

## 2026-11-22 — Gemini and Supervisor provider fallback

Added the Gemini Developer API integration and configurable planning-only
fallback between Groq, Gemini, and OpenRouter. All 148 distinct orchestrator
tests passed across disposable PostgreSQL runs. No live provider calls were
made. See [LLM provider configuration](orchestrator/LLM_PROVIDERS.md).

## 2026-11-22 — Supervisor real-mode stabilization

OpenRouter returned two valid decisions. Groq rate-limited Project Agent
synthesis after the tool-planning phase. Added safe stage diagnostics and
validated the read-only console path offline. Across disposable PostgreSQL
runs, 134 distinct tests passed. See
[Supervisor Phase 07](orchestrator/SUPERVISOR_PHASE_07.md).

## 2026-11-22 — Phase 04 stabilization

Traced Research failure to Groq HTTP 400 `tool_use_failed` after a successful
Tavily search and source read. Separated structured synthesis from research
tool use, fixed equivalent root URL grounding, and preserved safe failure
diagnostics. Live Research returned a verified Python documentation citation.
The Project adapter passed a complete mocked specification run, but its one
live test returned no valid specification. All 112 orchestrator tests passed.
See [Phase 04 verification](orchestrator/SUPERVISOR_PHASE_04.md#stabilization-verification)
for usage and limitations.

## 2026-11-22 — Supervisor Phase 04 real specialist adapters

Added an explicit real execution mode with four fixed adapters, active
membership checks, output validation, mapped errors, and provider usage
metadata. The existing mock and planning-only entry points remain.

All 107 orchestrator tests passed on in-memory SQLite, including nine adapter
tests. Django checks and diff hygiene passed. The controlled ORM and
XGBoost integration passed on disposable fixtures. The Research integration
made one Tavily search and received two Groq responses but produced no
validated findings. No OpenRouter requests or production database writes
were made. See [Supervisor Phase 04](orchestrator/SUPERVISOR_PHASE_04.md).

## 2026-11-22 — Supervisor Phase 03 integrated mock execution

Connected planner decisions to the existing validated mock scheduler and
added typed result aggregation and a deterministic assistant reply. Prior
results are kept separate from the current run. Fixed an integrated state
schema mismatch that prevented a mock preflight rejection from surfacing
its final decision.

All 98 orchestrator tests passed on in-memory SQLite, including 10 new
integrated tests. The focused Supervisor run passed all 43 tests. Django
checks and diff hygiene passed. No providers, real specialist agents, or
PostgreSQL writes were used. See
[Supervisor Phase 03](orchestrator/SUPERVISOR_PHASE_03.md).

## 2026-11-22 — Supervisor Phase 02 conversational planner

Added a planning-only LangGraph entry point, five typed conversation outcomes,
an authorized capability catalog, and independent validation of proposed plans.
The original Phase 01 mock executor remains available. Prior messages and results
remain in state, and only bounded history and result metadata enter the prompt.

All 88 orchestrator tests passed on in-memory SQLite, including 13 Phase 02 and
20 Phase 01 tests. Django checks and diff hygiene passed. The first live
`openrouter/free` request returned HTTP 429 and a structured planning error.
The second scenario was skipped. No specialists ran and no external database
was written to. See [Supervisor Phase 02](orchestrator/SUPERVISOR_PHASE_02.md).

## 2026-11-22 — Supervisor Phase 01 foundation

Added the reusable mock-only LangGraph, typed state and task results,
trusted runtime context, specialist capability registry, and deterministic
plan validation. Thread barriers proved independent tasks overlapped
and their validated outputs reached a dependent task after fan-in.

The orchestrator passed 73 tests with in-memory SQLite, including 55
existing regressions. The final focused foundation suite passed 20 tests.
Django checks, the PostgreSQL migration dry run, dependency checks, and
diff hygiene passed. No live agents, provider calls, or PostgreSQL writes
were used. See [Supervisor Phase 01](orchestrator/SUPERVISOR_PHASE_01.md).

## 2026-11-22 — OpenRouter provider

Added the official LangChain OpenRouter adapter to the shared factory. Groq
remains the default. Independent Supervisor and specialist settings select
provider and model. OpenRouter accepts explicitly free routes, requires
requested capabilities, and surfaces sanitized errors without retrying.
OpenRouter structured results use tool arguments validated by Pydantic.

OpenRouter lists Nemotron 3 Ultra and 3.5 Lightning free variants as
tool-capable without native JSON schema. Use `openrouter/free` as an
opt-in smoke-test candidate until a specific model passes live checks.
No OpenRouter credential was configured, so no live requests were sent.
Fifteen offline tests passed, including five factory tests. Mocked HTTP
responses exercised the actual SDK for chat, Pydantic task plans, tool
arguments, usage metadata, and HTTP 429/404/503 without retries.
Dependency and diff checks passed. No database writes were performed.

## 2026-11-22 — Agent 05 Tavily search

Replaced DDGS with Tavily Basic through HTTPX. The search tool preserves
provider source metadata, reports credit usage when available, and surfaces
missing credentials, timeout, authentication, and quota errors. The existing
Tavily environment value was present and left unchanged.

All 10 focused Research Agent tests passed. Django checks, dependency checks,
and diff hygiene passed. The live verification and PostgreSQL regression
commands did not return results after the escalated execution was denied.

## 2026-11-22 — Agent 05 integration diagnostics

Confirmed a direct DDGS timeout and empty results from eight DDGS searches
during the two requested live verification turns. Groq tool calling worked
on the configured model and the earlier HTTP 400 did not reproduce.
Added sanitized provider error fields, retained streamed diagnostics, and
stopped the agent locally after search failure. No live sources were returned.
See [Research Agent live integration findings](orchestrator/RESEARCH_AGENT.md#live-integration-findings).

## 2026-11-22 — Agent 05 Research Agent

Added standalone LangChain research with DDGS DuckDuckGo search, a public
HTTP(S) reader with address pinning and redirect checks, typed findings,
and citation validation against tool evidence from the current turn.
See [Research Agent](orchestrator/RESEARCH_AGENT.md) for command usage.

Attempted exactly two live Groq scenarios, the Flutter update request and
the Django REST Framework versus FastAPI comparison. Each returned
`BadRequestError`. The console observed no model responses or token usage
and could not validate a live report. Direct DuckDuckGo probes for both
topics returned no usable URLs, so live page extraction was not exercised.
Agent 05 remains pending successful live verification.

## 2026-11-22 — Agent 03 conversation fixes

The console retains the last validated matching result until reset. Ranking
comparisons use the saved scores, skill overlap, and exact role-match flags.
The response describes observed features without attributing causality.
Missing projects return a validated `not_found` result.

Two turns ran live against synthetic PostgreSQL fixtures. The follow-up
recovered the prior project but reran ranking and returned no comparison
(1,702 tokens). The invalid project returned `not_found` (1,198 tokens).
The follow-up renderer was corrected afterward and tested locally with both
tool and no-tool responses. The live run used four requests and 2,900 tokens.
The synthetic database created by this run was removed successfully.

## 2026-11-22 — Agent 03 minimal live verification

Ran the existing `test_matching_agent` console on an isolated PostgreSQL
database with synthetic fixtures and the configured `openai/gpt-oss-120b`.
The run used a 768-token completion limit and disabled provider retries.
It sent exactly three prompts and received five Groq responses. Token usage
was 2,672 input and 1,121 output tokens, or 3,793 total. No quota error occurred.

| Prompt | Observed outcome | Requests | Tokens |
| --- | --- | ---: | ---: |
| Find the top 2 employees for project 1. | Ranking tool returned fixture employees 2 and 1 in order, with verified scores 0.2738877534866333 and 0.14778979122638702. | 2 | 1,574 |
| Why is the first employee ranked higher than the second? | No tool call. Console asked for a project ID and supplied no explanation. | 1 | 966 |
| Find employees for project 999999999. | Context tool was called. Console returned an empty failed result, but replaced the missing-project error with a generic request for a project ID. | 2 | 1,253 |

All 38 orchestrator tests passed on a separate fresh PostgreSQL database.
The legacy `ai_model` suite still has two previously observed setup errors
when deserializing its separate joblib artifact (`input stream corrupted`).
The live console database teardown reported two open sessions and left the
synthetic test database in place. Agent 03 remains partially live-verified.

## 2026-11-22 — Independent Project Planning Agent

Implemented Agent 02 with LangChain `create_agent`, the shared Groq factory,
an external system prompt, strict nested project-specification schemas, seven
read-only planning tools, multi-turn input, validated clarification and
unsupported outcomes, company skill-taxonomy matching, and a standalone
scenario console. The agent never writes project data, fabricates saved IDs,
calls the Database Agent, performs employee matching, or modifies `ml_engine`.

Groq rejects native JSON response mode when combined with tools. The runtime
therefore uses a tool-capable conversational pass followed by a tool-free
native JSON-schema validation pass. Live testing found and fixed written and
hyphenated deadline extraction, completion truncation, Groq response-strategy
compatibility, excess validator context, unverified skill taxonomy labels, and
Windows UTF-8 console output.

Verification on the final local implementation:

- 23 focused Project Agent tests passed against PostgreSQL `test_Agentix`.
- All 10 existing Database Agent regression tests passed in the same run (33
  combined tests).
- `manage.py check` passed with no issues.
- `makemigrations --check --dry-run` reported no changes.
- `pip check`, Python compilation, and `git diff --check` passed.
- No `ml_engine` source or artifact was modified.

Live Groq verification used `openai/gpt-oss-120b`. A detailed food-delivery
scenario completed with validated structured output (6 model requests and 6
responses). A basic e-commerce clarification completed (2 requests and 2
responses); a deterministic formatter was then added to show its validated
questions. The technology-selection run made 3 requests: the two tool-agent
responses succeeded, while the JSON-schema validation request was rejected
after the organization reached its 200,000-token daily limit. The remaining
multi-turn, revision, role/skill, planning, persistence-refusal, and long-input
live scenarios could not be run after that provider quota failure. Because the
final risk schema and deterministic clarification formatting were added after
the successful calls, the complete A–I matrix still requires a quota-reset
rerun. Agent 02 therefore remains in verification rather than being marked
2/10 complete. No Agent 03 or Supervisor work was started.

## 2026-11-22 — Real Groq verification

The real Database Agent was tested against the isolated PostgreSQL
`test_Agentix` database using `openai/gpt-oss-120b`.

Six read-only API calls passed for capability explanation, department listing,
Python-skill employee search, active-project listing, department head-count
summarization, and cross-company access denial. Nine subsequent write,
follow-up, approval, and invalid-request calls passed or failed exactly as
intended.

Live verification created department ID 1075 as "AI Development", read it
through conversation memory, renamed it to "AI Research", verified both
states through Django ORM, prepared and rejected deletion, prepared and
approved deletion, and verified that the row was removed through Django ORM.
An invalid department ID was rejected safely.

A tool-result serialization defect was found and fixed. Tool successes now
return JSON-serializable result dictionaries instead of Pydantic instances
that LangChain exposed as non-structured string representations. The
configuration was changed from the unavailable `llama-3.3-70b-versatile`
model ID to `openai/gpt-oss-120b`. No live Groq key or private configuration
was written to the repository.

## 2026-11-22 — Independent Database Agent

Implemented the first specialist Database Agent under the existing
`orchestrator` app. Added the LangChain `create_agent` interface, Groq LLM
factory, external Markdown system prompt, Pydantic execution schemas,
trusted database execution context, company and role authorization, bounded
ORM tool registrations, conversation context handling, and standalone approval
records for destructive operations.

Implemented tools cover departments, employees and AI profiles, employee
skill relationships, skills, projects and requirements/member assignments,
company information and memberships, stored recommendation records,
department/project summaries, and duplicate detection. The agent does not use
raw SQL, call `ml_engine`, generate recommendations, retrain the model,
build a LangGraph Supervisor, or modify the approved business schema.

Verification:
- `python manage.py check`: passed.
- `python manage.py makemigrations --check --dry-run`: no changes detected.
- `python manage.py test orchestrator --keepdb --verbosity 2`: 10 focused tests
  passed against the existing PostgreSQL `test_Agentix` database.
- `python -m pip check`: passed with no broken requirements.
- No live Groq request was sent in automated tests.

## 2026-11-22 — Orchestrator reset to clean baseline

Removed the experimental orchestration implementation from the Django app.
Preserved the ML source, model artifacts, app migrations, and existing
database. Removed the test chat route and Groq settings and trimmed the
requirements manifest to the Django/backend and ML runtime dependencies. The
former orchestration progress and architecture notes are historical only.

Before cleanup, all 13 ML engine loading, prediction, feature, eligibility,
and ranking tests passed. After cleanup, `manage.py check`,
`makemigrations --check --dry-run`, and `pip check` passed. A direct load and
reference prediction returned class 1 with score 0.9938563704. All six ML
source files and both model artifact hashes matched their pre-cleanup values.
Two generated `.pyc` cache files were refreshed by the pre-cleanup test run;
the model code and artifacts were not changed.

## 2026-11-22 — Supervisor developer chat

Added a default-off staff testing route with authenticated session
ownership, live company scope, and CSRF-protected turns and approvals.
See [Phase 09 progress](orchestrator/PROGRESS.md) for verification.

## 2026-11-22 — Employee Matching Agent

Added matching over a verified database prerequisite using the existing
eligibility, feature, inference, and ranking engine. See
[Phase 08 progress](orchestrator/PROGRESS.md) for verification and limitations.

## 2026-11-22 — Trusted caller context and Database Agent

Added verified Django caller context, scoped conversation access, and five
bounded read capabilities for workforce and project data. See
[Phase 07 progress](orchestrator/PROGRESS.md) for verification and limitations.

## 2026-11-22 — Supervisor integration and stabilization

Added end-to-end mock capability tests. Isolated worker invocation from
parent checkpoint configuration and enforced object-shaped handler results.
See [Phase 06 progress](orchestrator/PROGRESS.md) for verification.

## 2026-11-22 — Recovery, limits, and approval

Added structured task failures, bounded retries for explicitly idempotent
capabilities, and configurable scheduling limits. Checkpointed runs now pause
for authorized approval and resume from the saved task records. See
[Phase 05 progress](orchestrator/PROGRESS.md) for verification and limitations.

## 2026-11-22 — Supervisor conversation checkpointing

Added checkpoint injection, an ownership-gated conversation service, and
safe restoration of completed turns. Interrupted executions require
recovery. See [Phase 04 progress](orchestrator/PROGRESS.md).

## 2026-11-22 — Supervisor developer console and SSE

Added staff-only Django conversation and approval endpoints, an HTML console,
and a replayable event journal driven by LangGraph updates. Verified all nine
Phase 06 tests and all 122 prior orchestrator tests across disposable
PostgreSQL runs. See [Supervisor Phase 06](orchestrator/SUPERVISOR_PHASE_06.md)
for startup, event contracts, and recovery limits.

## 2026-11-22 — Supervisor Phase 05 PostgreSQL checkpoints and approvals

Added signed, company-scoped conversation threads, PostgreSQL checkpoint
storage and single-use LangGraph approval interrupts for mock execution.
The isolated PostgreSQL run passed all 122 orchestrator tests, including
10 Phase 05 cases. Real dispatch remains read-only. See
[Supervisor Phase 05](orchestrator/SUPERVISOR_PHASE_05.md) for setup,
verification and recovery limits.

## 2026-11-22 — Dependency-aware Supervisor execution

Added LangGraph task fan-out and result merging, dispatch authorization,
validated handler contracts, and run history. See
[Phase 03 progress](orchestrator/PROGRESS.md) for verification.

## 2026-11-22 — Supervisor planning

Added structured Groq planning, trusted capability filtering, and deterministic
plan validation to the Supervisor graph. See
[Phase 02 progress](orchestrator/PROGRESS.md) for verification.

## 2026-11-22 — Supervisor foundation

Added the deterministic LangGraph foundation and its dependency pins.
All 26 orchestrator tests, Django system checks, and the dependency check
passed. See [Phase 01 progress](orchestrator/PROGRESS.md) for the version
changes and implementation decisions.

## 2026-11-21 — Orchestrator shared LLM Factory

### Changes

- Added `orchestrator/core/config.py`, `llm_factory.py`, `exceptions.py`, and
  package initialization.
- Added Groq configuration through Django settings and environment variables:
  `GROQ_API_KEY`, `GROQ_MODEL_NAME`, and `GROQ_TEMPERATURE`.
- Added the reusable, thread-safe cached `get_llm()` factory for Groq.
- Added LangChain Groq 1.2.1 to the root Python requirements.
- Added factory tests using mocked `ChatGroq` initialization only.
- Did not add agents, LangGraph, shared memory, APIs, models, migrations,
  database writes, or external startup calls.

### Verification

- `python manage.py test orchestrator --verbosity 2`: 19 tests passed.
- `python manage.py check`: passed; no issues reported.
- `python manage.py makemigrations --check --dry-run`: no changes detected.
- `.venv-ml python -m pip check`: no broken requirements found.

## 2026-11-21 — Orchestrator Phase 3 employee matching

### Changes

- Reused the previously tested exploratory feature, eligibility, and ranking
  algorithms inside `orchestrator/ml_engine/`.
- Implemented read-only company-isolated ORM snapshot assembly for project
  candidates, exact 16-feature extraction, owner-specified hard exclusions,
  verified predictor integration, and deterministic probability ranking.
- Kept feature mapping marked `EXPLORATORY_UNVERIFIED`; missing profiles,
  skills, roles, requirements, deadlines, proficiency, and years are blocked
  rather than imputed.
- Added focused synthetic-object tests for exact feature order/calculations,
  eligibility, ranking, company isolation, missing data, and prediction
  integration.
- Did not change Django models, migrations, APIs, recommendations, project
  members, or any database records.

### Verification

- `python manage.py test orchestrator --verbosity 2`: 13 tests passed.
- `python manage.py check`: passed; no issues reported.
- `python manage.py makemigrations --check --dry-run`: no changes detected.
- No compatibility issues were found in the shared Python 3.13 `.venv-ml`.

### Remaining uncertainty

- The original training feature-generation source and label-generation process
  remain unavailable. The implemented text parsing, exact skill matching,
  arithmetic means, role matching, deadline calculation, and unit usage are
  therefore exploratory adaptations of the previously tested implementation,
  not verified production training formulas.

## 2026-11-21 — Orchestrator model loader and predictor

### Changes

- Added cached loading of the fitted preprocessor and native XGBoost artifact
  inside `orchestrator/ml_engine/loader.py`.
- Added exact 16-feature validation and saved-estimator batch prediction inside
  `orchestrator/ml_engine/predictor.py`.
- Did not add feature extraction, eligibility, ranking, database queries,
  APIs, retraining, or model-artifact modifications.

### Verification

- `python manage.py test orchestrator --verbosity 2`: 6 tests passed.
- `python manage.py check`: passed; no issues reported.
- The Colab reference sample produced class `1` with positive probability
  `0.9938563704`, matching the previously verified result.

## 2026-11-21 — Empty orchestrator app

### Changes

- Created the `orchestrator` Django app inside `agentix_backend`.
- Registered `orchestrator` in `INSTALLED_APPS`.
- Left the app without models, migrations, APIs, agents, or other functionality.

### Verification

- `python manage.py check`: passed; no issues reported.
- `python manage.py makemigrations --check --dry-run orchestrator`: passed;
  no migrations or model changes were detected.

## 2026-10-19 — Initial accounts app

### Changes

- Inspected the existing Django project, settings, URL configuration,
  dependencies, virtual environment, repository status, and local PostgreSQL
  listener.
- Added the `accounts` app using Django's existing user model without custom
  user or business models.
- Added registration with Django password validation and hashing; token
  obtain, refresh, and blacklist endpoints; and an authenticated safe profile
  endpoint.
- Configured Simple JWT for 15-minute access tokens, 7-day refresh tokens,
  rotation, and blacklist-after-rotation.
- Moved Django secret and PostgreSQL connection credentials to environment
  variables.
- Added accounts API tests and project documentation, including the approved
  DBML schema.

### Verification

- `python manage.py test accounts --verbosity 1`: **12 tests passed** using
  the PostgreSQL test database. The test runner created and removed
  `test_Agentix`; it did not delete development data.
- The initial test run exposed two test expectation/setup mistakes (the
  duplicate-username fixture used another username, and Simple JWT logout
  responds with HTTP 200). Both tests were corrected, and the full suite
  passed on rerun.
- `python manage.py check`: passed with no issues.
- `python manage.py makemigrations --check --dry-run`: passed with no model
  changes detected.
- `python manage.py migrate --noinput`: applied the pending Simple JWT
  blacklist migrations to the configured database; no business tables were
  introduced.
- `python manage.py showmigrations auth token_blacklist`: all migrations
  applied after migration.
- Resolved all five accounts endpoint paths successfully.

### Known issues

- `DJANGO_SECRET_KEY` must be set in the runtime environment. PostgreSQL
  connection variables are also read from the runtime environment.

## 2026-10-19 — Root dotenv configuration

### Changes

- Added `python-dotenv` and load the repository-root `.env` before reading
  settings.
- Kept PostgreSQL as the database backend and made `DB_PASSWORD` explicitly
  required alongside `DJANGO_SECRET_KEY`. Database name, user, host, and port
  retain their defaults when unset.
- Added a placeholder-only `.env.example` and updated `.gitignore` so `.env`
  remains ignored while `.env.example` can be committed.
- Updated the README with Windows instructions for copying and configuring
  `.env`.

### Verification

- `python manage.py check`: passed with configuration loaded from root
  `.env`, after clearing process environment overrides.
- `python manage.py test accounts --verbosity 1`: all 12 tests passed
  against PostgreSQL using root `.env` configuration; the temporary test
  database was removed by Django.
- `git check-ignore .env`: confirmed the local environment file is ignored.
- `.env.example` is not ignored and contains placeholder values only.

## 2026-10-19 — Companies app

### Changes

- Added only `companies.Company` and `companies.CompanyUser`, mapped to the
  approved `companies` and `company_users` table names and using Django's
  configured user model.
- Added the authenticated company create/list/detail/patch/member APIs.
  Company creation atomically creates an owner membership; membership-scoped
  reads return 404 for inaccessible company IDs.
- Chose owner-only company updates as the least-privilege rule. Admin,
  manager, and member roles may read accessible company data but may not
  update company details.
- Added the initial companies migration and focused API/database tests.

### Verification

- `python manage.py check`: passed.
- `python manage.py makemigrations --check --dry-run`: passed with no changes
  remaining after migration generation.
- `python manage.py migrate --noinput`: applied
  `companies.0001_initial` to PostgreSQL `Agentix`.
- `python manage.py test companies accounts --verbosity 2`: all 23 tests
  passed against PostgreSQL's temporary `test_Agentix` test database.
- Tests cover owner creation and atomic rollback, authorized and unauthorized
  reads, owner/admin/manager/member update permissions, duplicate creator and
  membership prevention, unauthenticated requests, input validation, and
  route resolution.
- No other business app or table was added.

## 2026-10-19 — Workforce app

### Changes

- Added the five approved workforce models with explicit DBML table names,
  relationships, nullability, defaults, and uniqueness constraints.
- Added authenticated CRUD routes for departments, employees, nested
  employee AI profiles, company skills, and employee-skill assignments.
- Scoped workforce reads to the caller's company memberships. Owners,
  admins, and managers can write; members are read-only. Write permission is
  checked against the specific company for object changes.
- Validated relationship IDs against companies where the user has write
  permission and rejected employee-skill links crossing company boundaries.
- Preserved same-company employee-skill integrity when department, employee,
  or skill company relationships are changed.
- Added the initial workforce migration and endpoint, constraint, and
  cross-company authorization tests.

### Verification

- `python manage.py check`: passed with no issues.
- `python manage.py makemigrations --check --dry-run`: passed with no
  ungenerated model changes.
- `python manage.py migrate --noinput`: applied
  `workforce.0001_initial` and
  `workforce.0002_alter_department_created_at_and_more` to PostgreSQL
  `Agentix`; the latter preserves database-side `now()` defaults for
  workforce timestamps.
- An earlier `python manage.py test workforce companies accounts
  --verbosity 1` run passed all 40 tests against PostgreSQL's temporary
  `test_Agentix` database; Django removed the temporary test database.
- After adding another role-permission test, the subsequent 41-test run
  failed with five database connection errors when the PostgreSQL Windows
  service stopped.
- After PostgreSQL became available again, `python manage.py test workforce
  companies accounts --verbosity 2 --keepdb` passed all 41 tests against the
  existing PostgreSQL `test_Agentix` database. The database was preserved by
  `--keepdb`.
- `python manage.py check` and `python manage.py makemigrations --check
  --dry-run` both passed after the recovery.
- Resolved every workforce route and confirmed the active Django database
  configuration uses `django.db.backends.postgresql` with name `Agentix`.
- No documents, connections, AI agents, projects, recommendations, or other
  unapproved business models were added.

## 2026-10-19 — Documents app

### Changes

- Added only the approved `CompanyDocument` model, mapped to
  `company_documents` with the approved fields, relation, and timestamp
  defaults.
- Added authenticated list/create and detail/retrieve/update/delete routes
  under `/api/v1/documents/`.
- Scoped reads to company memberships and writes to owners, admins, and
  managers. Company IDs supplied on writes are restricted to companies where
  the requester has a writable membership; inaccessible document IDs return
  404.
- Implemented `file_path` as nullable metadata only; no file upload or
  storage behavior is claimed.
- Added documents API and permission tests and registered the app and routes.

### Verification

- `python manage.py check`: passed with no issues.
- `python manage.py makemigrations --check --dry-run`: passed with no
  ungenerated model changes.
- `python manage.py migrate --noinput`: applied
  `documents.0001_initial` to PostgreSQL `Agentix`.
- `python manage.py test documents companies accounts workforce --verbosity
  2 --keepdb`: all 51 tests passed against the existing PostgreSQL
  `test_Agentix` test database; it was preserved.
- Both document URL patterns resolved successfully in the automated tests.
- No integrations, agents, projects, recommendations, or other unapproved
  apps or business tables were added.

## 2026-10-19 — Integrations app

### Changes

- Added only the approved `Connection` model mapped to the `connections`
  table, including the company relation, provider metadata, `disconnected`
  status default, and nullable `connected_at`.
- Added authenticated connection list/create and detail/retrieve/update/delete
  routes under `/api/v1/integrations/`.
- Scoped reads to company members and writes to owners, admins, and managers.
  Company IDs supplied on create/update must belong to a company where the
  requester has a writable membership; inaccessible records return 404.
- Limited this app to connection metadata. It does not establish or verify
  external provider connections or store credentials, API keys, or tokens.
- Added the initial migration, API tests, and integrations module
  documentation.

### Verification

- `python manage.py check`: passed with no issues.
- `python manage.py makemigrations --check --dry-run`: passed with no
  ungenerated model changes.
- `python manage.py migrate --noinput`: applied
  `integrations.0001_initial` to PostgreSQL `Agentix`.
- `python manage.py test integrations companies accounts workforce documents
  --verbosity 2 --keepdb`: all 62 tests passed against the existing
  PostgreSQL `test_Agentix` test database; it was preserved.
- Both integration URL patterns resolved successfully.
- No agents, projects, recommendations, or other unapproved apps/tables were
  added.

## 2026-10-19 — Agents app

### Changes

- Added only the approved `AIAgent` model mapped to `ai_agents`, with the
  company relation, metadata fields, `active` status default, and
  current-timestamp defaults.
- Added authenticated agent list/create and detail/retrieve/update/delete
  routes under `/api/v1/agents/`.
- Scoped reads to company members and writes to owners, admins, and managers.
  Company IDs supplied on create/update must belong to a company where the
  requester has a writable membership; inaccessible records return 404.
- Limited the app to agent records and metadata. It does not execute
  autonomous tasks, call tools, run AI workflows, or handle credentials.
- Added the initial migration, API tests, and agents module documentation.

### Verification

- `python manage.py check`: passed with no issues.
- `python manage.py makemigrations --check --dry-run`: passed with no
  ungenerated model changes.
- `python manage.py migrate --noinput`: applied `agents.0001_initial` to
  PostgreSQL `Agentix`.
- `python manage.py test agents companies accounts workforce documents
  integrations --verbosity 2 --keepdb`: all 75 tests passed against the
  existing PostgreSQL `test_Agentix` test database; it was preserved.
- Both agent URL patterns resolved successfully.
- No projects, recommendations, or other unapproved apps/tables were added.

## 2026-10-19 — Projects app

### Changes

- Added only the approved `Project`, `ProjectRequirement`, and `ProjectMember`
  models mapped to their exact DBML table names and existing `Company`,
  `Employee`, and `AIAgent` model classes.
- Added authenticated project CRUD and nested project requirement and member
  CRUD routes under `/api/v1/projects/`.
- Scoped project and nested-resource queries to the user's company
  memberships. Owners, admins, and managers can write; members can read.
- Validated that a project member references exactly one employee or AI
  agent, that the candidate belongs to the project's company, and that
  company changes cannot invalidate existing project-member assignments.
- Added the initial migration and project API tests.

### Verification

- `python manage.py check`: passed with no issues.
- `python manage.py makemigrations --check --dry-run`: passed with no
  ungenerated model changes.
- `python manage.py migrate --noinput`: applied `projects.0001_initial` to
  PostgreSQL `Agentix`; the migration is recorded as applied.
- `python manage.py test projects agents workforce companies accounts
  documents integrations --verbosity 2 --keepdb`: all 91 tests passed
  against the existing PostgreSQL `test_Agentix` test database; it was
  preserved.
- Project, requirement, and member route patterns resolved in the tests.
- Confirmed the configured database remains PostgreSQL `Agentix`.

## 2026-10-19 — Recommendations app

### Changes

- Added only the approved `Recommendation` model and `recommendations` table,
  referencing the existing `Project`, `Employee`, and `AIAgent` models.
- Added database and serializer validation requiring exactly one employee
  or AI-agent target.
- Added authenticated list/create and detail/retrieve/update/delete routes,
  plus a project-scoped recommendation listing route.
- Scoped all record and project queries through company membership. Owners,
  admins, and managers can write; members can read. Candidate targets are
  checked against the project's company.
- The app stores recommendation records only; no recommendation-generation
  or AI-scoring algorithm was added.
- Added the initial migration, API tests, and module documentation.

### Verification

- `python manage.py check`: passed with no issues.
- `python manage.py makemigrations --check --dry-run`: passed with no
  ungenerated model changes.
- `python manage.py migrate --noinput`: applied
  `recommendations.0001_initial` to PostgreSQL `Agentix`.
- `python manage.py test recommendations projects agents workforce companies
  accounts documents integrations --verbosity 2 --keepdb`: all 108 tests
  passed against the existing PostgreSQL `test_Agentix` test database; it was
  preserved.
- Recommendation list, detail, and project-scoped list routes resolved in
  the tests.
- Confirmed the configured database is PostgreSQL `Agentix`.

## 2026-10-20 — Django Admin configuration

### Changes

- Registered the existing company, workforce, document, connection, AI agent,
  project, and recommendation models in their app admin modules. Accounts
  continues to use Django's standard registered User and Group administration;
  it defines no models.
- Added useful list columns, searches, filters, ordering, relationship
  selectors, read-only timestamps, and company/project/employee inlines.
- Added admin form validation for employee-skill company consistency and
  project-member/recommendation one-candidate and same-company rules. Existing
  database constraints and API behavior are unchanged.
- Confirmed the existing root URL configuration mounts Django Admin at
  `/admin/`.

### Verification

- `python manage.py check`: passed with no issues.
- Confirmed the Django Admin registry includes Django's built-in User and
  Group plus all 14 implemented business models.
- `python manage.py test accounts companies workforce documents integrations
  agents projects recommendations`: the initial run could not create its
  temporary test database because `test_Agentix` already existed and the
  non-interactive confirmation prompt could not be answered. No database was
  deleted.
- Reran the requested app suite with `--keepdb`: all 108 tests passed against
  the existing PostgreSQL `test_Agentix` test database, which was preserved.
- Five focused admin-form tests passed for employee-skill company matching,
  project-member/recommendation candidate and company validation, and
  department/employee/skill/project changes that could invalidate existing
  assignments.
- The final full app suite passed all 113 tests with `--keepdb`, preserving
  the existing PostgreSQL `test_Agentix` test database.
- `git diff --check`: passed.
- No migration was created; Django Admin configuration did not change models
  or the approved database schema.

## 2026-10-20 — Agentix Master Control Center (admin presentation)

### Changes

- Added presentation-only `admin_center` app with `AgentixAdminSite`,
  permission-aware dashboard metrics, branded templates, and CSS design
  tokens. No business models or migrations were added.
- Wired `AGENTIX_ADMIN_CUSTOMIZATION_ENABLED` in settings so disabling the
  flag (and restarting) restores stock Django Admin presentation while
  keeping all existing model registrations.
- Documented architecture, flag behavior, and rollback in
  `docs/ADMIN_CUSTOMIZATION.md`. Existing app-level `admin.py` files were
  left as the source of model administration.

### Verification

- `python manage.py check`: passed with no issues.
- `python manage.py makemigrations --check --dry-run`: passed; no model
  changes detected.
- `python manage.py test admin_center --keepdb`: all 9 tests passed against
  the existing PostgreSQL `test_Agentix` database.
- `python manage.py test admin_center recommendations projects agents
  workforce companies accounts documents integrations --keepdb`: all 122
  tests passed against the existing PostgreSQL `test_Agentix` database,
  which was preserved.
- Strengthened the feature-flag subprocess test to verify that disabled
  customization resolves Django's stock admin index template and preserves
  User, Group, and all 14 business-model registrations.
- Added enabled-mode coverage for the complete admin model registry.
- `git diff --check`: passed.
- Uncommitted prior README/status/log admin-registration notes were
  preserved and extended rather than reverted.
