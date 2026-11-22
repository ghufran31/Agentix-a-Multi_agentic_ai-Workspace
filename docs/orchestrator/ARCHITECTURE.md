# Orchestrator architecture

> Historical design notes for the removed prototype. They do not describe the
> current app. The current baseline is a minimal Django shell with the
> preserved `ml_engine` directory.

The Supervisor graph initializes missing fields, optionally plans one new
request, and executes ready plans. Supply an explicit `user_request` in state and pass a
server-created `PlanningContext` through `invoke(..., context=...)`.
The graph consumes the request and stores its proposal in `planning_outcome`.
Existing messages, plan, task results, and execution status remain available.
Without a checkpointer, pass prior state explicitly. For checkpointed threads,
use `ConversationService` with a trusted ownership callback. The service checks
the authenticated user, company, and conversation UUID before reading or writing
state. Register conversation ownership server-side before the first turn.
Thread IDs are namespaced by user and company. One process serializes turns
per thread. Multi-process deployment requires coordinated single-writer access.

The in-process registry lists trusted handlers by name and capability. To add
an agent, register an `AgentSpec` with its name, description, capabilities,
handler, and required permissions. Add a `CapabilitySpec` with a description,
Pydantic input schema, restrictions, and approval requirement for each capability
the planner may use. The server must preauthorize exact agent/capability pairs
for the caller and company. The planner intersects that allowlist with enabled
registrations. Omitted context grants access to zero capabilities.

The planner uses the shared Groq factory and Pydantic structured output with
`function_calling`. For a compatible JSON-only model, select
`build_graph(registry, method="json_mode")`. Both methods validate against
the same schema and server allowlist. An unsupported method or provider error
produces a safe planning failure. Groq free and developer tiers require a
supported `GROQ_MODEL_NAME` such as `openai/gpt-oss-120b` if the installation
still uses the retired Llama 3.3 default.

Ready plans require known capabilities, strict input validation, matching
approval requirements, unique task IDs, and existing acyclic dependencies.
Plans are limited to 12 tasks and five tasks per dependency chain. Dependencies
express ordering and identify the direct prerequisite results passed to handlers.
Messages merge by ID using LangGraph's message reducer. Results merge by task
ID, accept identical retries, and reject conflicting writes. The plan and
execution status are reserved for a single writer per graph step.

The scheduler revalidates the plan, then uses LangGraph `Send` to dispatch
ready tasks in parallel. Each wave merges records by task ID before the next
wave starts. Failed prerequisites block downstream tasks. Independent successes
are retained. Completed tasks are skipped within the run, and non-ready
planning outcomes end without dispatch.

Execution requires an async registered handler and a Pydantic output schema.
The handler receives an `ExecutionInput` with its task ID, capability,
validated input model, and copies of direct prerequisite results keyed by task
ID. Workers check the server allowlist again before invocation. They validate
outputs and apply a 30-second cooperative timeout. Handlers must yield to the
event loop and use bounded I/O. Task records contain an attempt count and
stable failure codes with safe messages. Only a handler's explicit
`TemporaryExecutionError` on a registered `retry_safe` capability permits a
retry. Mark a capability retry-safe only after verifying its idempotency.
Timed-out and approval-gated work gets no automatic retry.

`ExecutionLimits` defaults to one retry, 12 scheduling rounds, and four
concurrent workers per run. Limits can be lowered or raised within hard bounds
of three retries and 12 workers. Each wave consumes a round. A round limit or
an unsatisfied dependency leaves tasks blocked and preserves completed results.

Read the latest execution at `execution_runs[execution_id]`. Its task records
carry a terminal status and either a validated result or a safe error. Run IDs
keep reused task IDs separate and retain prior runs in caller-supplied state.
Checkpointed turns restore messages, the current plan, and run history.
The planner sees recent conversation messages. Historical task data is sent to
the provider only through an optional server-supplied summary that applies
current permissions and removes sensitive fields. Restoring state never runs
workers. New turns submit only new text and generate separate execution IDs.

The service saves checkpoints synchronously at graph boundaries. When ready
work needs approval, it saves prior results and pauses in a side-effect-free
LangGraph interrupt node. The pending request names the run, task, capability,
and trusted action description. A capability may explicitly list input fields
safe for review. Register only fields safe for the intended reviewer.

Call `ConversationService.decide_approval` with the trusted owner, conversation
UUID, exact run and task IDs, a boolean decision, and fresh server-authorized
capabilities. The service checks ownership and the `can_approve` callback,
matches the checkpoint's pending interrupt, and resumes that interrupt only.
Approval without a policy fails closed. Decisions are recorded in the run.
Rejection blocks dependents, and completed records are carried forward without
dispatch. The dispatcher still checks capability access and validates inputs
before executing. A graph without a checkpointer blocks approval-required work.

A terminal blocked run can be read and followed by a new turn. Other pending
nodes or failed in-flight checkpoints return `recovery_required`. Worker waves
are not checkpointed during execution. A crash can leave partial progress
unavailable, and an external effect may precede its saved result. The service
does not guarantee exactly-once external execution or coordinate across processes.

Each worker graph starts with a fresh execution context and explicit inputs
and authorization. This keeps the parent checkpoint namespace and
synchronous durability setting out of the worker graph. Parent checkpoints
are still written synchronously. Ambient tracing and request context are
also isolated. Workers receive caller scope explicitly from runtime context.

For database capabilities, the server calls `database_context(request.user,
selected_company_id)` after Django authenticates the request. This verifies
active company membership and supplies only the registered database read
pairs. Use `register_database_agent(registry)` to register those capabilities.
Pass the derived context to conversation turns and restores, with a trusted
conversation ownership callback. The service verifies matching owner scope
and current membership before accessing a separate verified checkpoint
namespace. Caller identity stays out of task inputs, model prompts, and
checkpoint state. Registration alone grants no access.

Database operations are limited to `list_employees`, `get_employee`,
`list_projects`, `get_project`, and `matching_context`. Fixed ORM queries
scope employees through departments and projects through their company.
Nested skill and requirement queries are scoped independently. The database
worker rechecks active membership with thread-sensitive `sync_to_async`.
Foreign and missing IDs share one `not_found` outcome. Employee names and
contact fields are excluded. Numeric precision fields serialize as decimal
strings and deadlines as ISO dates.

List inputs use an ascending primary-key cursor and a limit of 1–25 (10
by default). Nested collections are capped at 25 per parent and requirement
text at 1,000 characters per field, with explicit truncation flags. Matching
context returns stored project requirements and one employee page with
profiles and skills. Consumers must page or detect truncation before scoring
and handle missing profiles and values. Requirement skills and roles are
stored text and are returned as such. The payload is a data projection, not
a model feature vector or a point-in-time snapshot of the entire company.

Register `register_matching_agent(registry)` alongside the Database Agent
and use `matching_context_for_user` to derive the company-member allowlist.
`employee_matching.rank_candidates` accepts a project ID and `top_k` (1–25).
It requires one direct `database.matching_context` prerequisite for that
project, starting at the first page with limit 25. The scheduler supplies
the producer identity separately from result JSON. The handler revalidates
the envelope, live membership, and current company ownership of the
project and employee IDs before scoring. Task inputs cannot provide people
or model features.

Pages with a leading or trailing cursor, truncated requirements, or truncated
skills return `truncated` with no scores. There is no multi-page ranking yet.
Missing or invalid project requirements return `incomplete_data`. Missing
employee data can leave an explicitly labeled evaluable subset. The existing
engine applies eligibility, extracts all 16 features, and uses its cached
preprocessor and XGBoost artifacts off the event loop. The cooperative
timeout cannot forcibly stop native inference. The existing workload
behavior applies. Results contain eligible employee IDs, rank, skill
metrics, and a model score derived from synthetic labels. The score is exploratory
decision support. It has no established real-world calibration.

`open_checkpointer()` defaults to memory. For an approved deployment, install
the optional `langgraph-checkpoint-postgres==3.2.1`, set
`AGENTIX_CHECKPOINT_BACKEND=postgres` and provide a private
`AGENTIX_CHECKPOINT_DSN` pointing to a dedicated checkpoint database or schema.
After approval, use a provisioning role to call the official saver's
`setup()` once for that database or schema. This creates and migrates
`checkpoint_migrations`, `checkpoints`, `checkpoint_blobs`, and
`checkpoint_writes` and their indexes. Use a scoped runtime role afterward
and keep the service inside the checkpointer context. Application startup and
ordinary use do not call setup. PostgreSQL persistence has not been exercised
against a live database in this phase.

Reference: [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api).
See [ChatGroq structured output](https://reference.langchain.com/python/langchain-groq/chat_models/ChatGroq/with_structured_output)
and [Groq deprecations](https://console.groq.com/docs/deprecations).
See [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
and the [PostgreSQL saver setup requirements](https://pypi.org/project/langgraph-checkpoint-postgres/3.2.1/).
See [LangGraph subgraphs](https://docs.langchain.com/oss/python/langgraph/use-subgraphs)
for checkpoint inheritance.
See [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
for the checkpoint and resume contract.

## Developer chat

The developer tester runs at `/agentix/test/`. It requires an active
Django staff session, an explicit user-ID allowlist, and current company
membership. The server binds the selected company and generated thread UUID
to the Django session. The conversation service checks ownership and
membership again before access. For local development, run these commands
from the repository root with PostgreSQL running:

```powershell
$env:AGENTIX_TEST_UI_ENABLED = 'true'
$env:AGENTIX_TEST_UI_USER_IDS = 'YOUR_DJANGO_USER_ID'
$env:GROQ_MODEL_NAME = 'openai/gpt-oss-120b'
Set-Location agentix_backend
..\.venv-ml\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Use the existing local environment for `GROQ_API_KEY`. The model in the
example supports tool calling. Sign in at `http://127.0.0.1:8000/admin/`, then open
`http://127.0.0.1:8000/agentix/test/`. Select a company and click **New
conversation**. Try listing employees or asking for matches for a known
project ID. The Execution panel shows plans, prerequisites, safe failures,
and task outputs. Remote access requires HTTPS, deployment settings with
`DEBUG=False`, appropriate allowed hosts and CSRF origins, and secure cookies.
The feature is off unless explicitly enabled.

The tester uses process-local checkpoints. Restarts clear history, and
multiple processes do not share it. Each session has one active thread.
Approval controls use the existing service and appear only for a pending
approval. The registered read capabilities do not normally request approval.
The tester sends chat text to the planner. It does not feed historical task
results to Groq. Execution details show a bounded preview and recent runs.
