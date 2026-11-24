# Supervisor Phase 07

Phase 07 verifies the real read-only Supervisor path in stages. Live
OpenRouter structured decisions succeeded. Live multi-task execution and
live Project Agent specification generation still need verification.

## Start the real developer console

From `agentix_backend` with the project environment active, provision console
storage if it has not already been set up. Keep credentials in the project
environment. The configuration used for verification was:

```powershell
python manage.py setup_supervisor_console
$env:AGENTIX_SUPERVISOR_CONSOLE_ENABLED = 'true'
$env:AGENTIX_SUPERVISOR_CONSOLE_MODE = 'real'
$env:SUPERVISOR_LLM_PROVIDER = 'openrouter'
$env:SUPERVISOR_LLM_MODEL = 'openrouter/free'
$env:SPECIALIST_LLM_PROVIDER = 'groq'
$env:SPECIALIST_LLM_MODEL = 'openai/gpt-oss-120b'
python manage.py runserver 127.0.0.1:8000
```

Open [the Supervisor console](http://127.0.0.1:8000/dev/supervisor/) as an
active staff member with a company membership. Confirm the header says
**Real mode**. Select or create a real-mode conversation. For saved project
lookup or matching, enter a project ID from the active company.

The server selects the provider, capabilities, and permissions. The console
uses session authentication, CSRF checks, and company and conversation
ownership. Real task dispatch uses the existing allowlisted read-only
adapters. PostgreSQL stores operational checkpoints and events. See the
[Phase 06 guide](SUPERVISOR_PHASE_06.md) for endpoint and storage details.

## Manual workflow checklist

| Scenario | What to verify |
| --- | --- |
| A. Ask “Hello Agentix. What can you do?” | A direct response appears in history and no specialist runs. The live planner passed this probe. |
| B. Ask for details of an existing project | The database task returns only scoped project fields. With no project ID, expect clarification. |
| C. Ask for the best employees for an existing project | Matching returns actual XGBoost scores and eligible candidates. Use an authorized project ID. |
| D. Ask for Python's latest features and verified sources | Follow the Research Agent citations to the sources. Verify findings are grounded. |
| E. Request a detailed e-commerce specification without saving | The Project task shows a validated specification or a safe error. Verify no business project is created. |
| F. Request Flutter architecture research and an e-commerce specification without saving | Expect both capabilities, with independent tasks eligible to overlap. The live planner returned clarification before any dispatch on this prompt. |
| G. Request a Flutter e-commerce specification, then research suitable backend options | Verify the follow-up retains the Flutter context and checkpoints remain readable after refresh. |

Prior controlled runs verified Database, Matching, and Research. Phase 07
reused the database and ranking regression fixtures. It made no live
Research Agent or Tavily calls.

## Live requests and observed usage

| Probe | Requested model | Routed model | HTTP | Input / output tokens | Result |
| --- | --- | --- | --- | --- | --- |
| OpenRouter direct request | `openrouter/free` | `nvidia/nemotron-3.5-lightning:free` | 200 | 1,536 / 285 | Pydantic direct response |
| OpenRouter Flutter request | `openrouter/free` | `nvidia/nemotron-3-ultra-550b-a55b:free` | 200 | 1,548 / 614 | Pydantic clarification, no plan or dispatch |
| Groq Project tool planning, request 1 | `openai/gpt-oss-120b` | same | 200 | 1,362 / 115 | Tool planning response |
| Groq Project tool planning, request 2 | `openai/gpt-oss-120b` | same | 200 | 2,940 / 1,148 | Draft response |
| Groq Project structured synthesis | `openai/gpt-oss-120b` | unavailable | 429 | unavailable | `rate_limit_exceeded` |

The live runs made two OpenRouter requests (3,084 input, 899 output tokens)
and one Project Agent invocation (three Groq HTTP requests, 4,302
input and 1,263 output tokens reported across two successful responses).
The rejected request reported no usage. Tavily used zero credits. No live
request was repeated. The live planner probes used the shared factory in
planning-only mode. The Project probe used the real adapter and an injected
validated Supervisor decision with membership lookup mocked. Browser
integration was tested separately with real-mode routing and mocked providers.

## Stabilization and limits

Project synthesis now receives the bounded tool-phase draft and concise
output instructions. Strict Pydantic validation still rejects incomplete
specifications. Project errors preserve the safe failure stage, HTTP status,
and an allowlisted provider code. HTTP 429 maps to `rate_limited`, and SSE
terminal events include a safe error code. Provider response bodies and
credentials stay outside the console.

The earlier Project run lacked sufficient diagnostics to identify its
failure stage. The latest run reached structured synthesis and was stopped
by Groq rate limiting. That run did not exercise successful provider-native
Project specification validation. The Supervisor prompt now scopes the
saved-project ID requirement to lookup and matching. The update has offline
coverage and has not been tested with another live request.

## Automated verification

The focused PostgreSQL run passed 72 tests, including mock planner and
specialist routes, real-mode console checkpoints, and authorization checks.
The full regression run discovered 134 tests and passed 127. Seven console
database cases were skipped there because they require the Phase 06 test
database prefix. All seven ran and passed in the focused run, for 134
distinct passing tests across both runs. The 13 planner tests passed again
after the prompt edit. Django system checks, migration dry run,
`pip check`, and `git diff --check` passed.

## Plan validation diagnostics and project matching chain

The previous live `invalid_plan` response was caught by static plan
validation, but its generated plan was not retained; the exact failed rule
cannot be recovered. The validator now logs a bounded rule/error code, task
and capability identifiers, dependency/reference endpoints, and Pydantic
locations/types where applicable. Input values and internal details remain
out of user-facing errors.

Offline validation covers the authorized chain
`project.plan → database.create_project → matching.rank`: the create task
references `project.plan.structured_output`, matching references
`database.create_project.project_id`, and the server-bound deadline remains
`2027-03-30`. The existing approval and permission gates remain required.
