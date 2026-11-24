# Supervisor Phase 06

The authenticated developer console is at `/dev/supervisor/`. It is disabled
by default. Mock mode uses an offline planner and simulated tasks. Real mode
uses only Phase 04 read-only adapters and can consume provider credits.

## Local startup

From `agentix_backend`, with PostgreSQL and the project environment configured:

```powershell
python manage.py setup_supervisor_console
$env:AGENTIX_SUPERVISOR_CONSOLE_ENABLED = 'true'
python manage.py runserver 127.0.0.1:8000
```

Open http://127.0.0.1:8000/dev/supervisor/ and sign in using a Django staff
account that belongs to a company. Create a conversation and send `demo` to
see parallel tasks, `demo failure` to see partial completion, or
`demo approval` to pause and approve or reject the operation. Approval
decisions require an owner, admin, or manager role. Refresh while paused to
check recovery, then reopen the conversation from the selector.

The setup command provisions the Phase 05 saver and the console thread index
and event journal in `agentix_checkpoints`. These tables are operational
storage. The command does not change Django business schemas or migrations.
A separate checkpoint database can be configured via `AGENTIX_CHECKPOINT_DSN`.
The runtime database role needs access to the console tables and sequences
as well as the checkpoint tables. Keep storage credentials out of logs.

## Version 1 endpoints

All paths are relative to `/dev/supervisor/api/v1/conversations/`.
POSTs require JSON and a valid Django CSRF token tied to the session.

| Method | Suffix | Request and response |
| --- | --- | --- |
| GET | empty | `{conversations: [{thread, created_at}], mode}` for the latest 100 conversations |
| POST | empty | `{}` creates a conversation and returns `{thread, mode}` with HTTP 201 |
| GET | `<thread>/messages/` | `{messages: [{role, content}]}` from the checkpoint |
| POST | `<thread>/messages/` | `{message, request_id, project_id?}` returns `{execution_id}` |
| GET | `<thread>/execution/` | `{mode, execution_id, status, decision, plan, errors, pending_approvals, approval_records}` |
| GET | `<thread>/events/` | SSE from `Last-Event-ID`, or `?after=<id>` for a new client |
| POST | `<thread>/approval/` | `{approval_id, execution_id, approved}` resumes and returns `{execution_id}` |

`request_id` is a client-generated UUID, returned as a canonical hexadecimal
`execution_id`. Retries must reuse the UUID for the same operation. The
service records the submission under the Phase 05 thread lock. A repeated
submission returns the existing ID. Execution state represents the latest
checkpoint in a conversation. The plan is nullable and contains a goal plus
task entries with ID, capability, agent, dependencies, status, output and
error fields. Application errors use `{error: {code}}`. Session, CSRF and
allowed-method errors may use Django's standard responses.

## Streaming and recovery

The graph publishes actual events through LangGraph `updates` and `custom`
streams. Each SSE record has a numeric cursor and a JSON body with `type`,
`execution_id`, nullable `task_id`, UTC `timestamp`, `status` and `data`.
Data is limited to identifiers, counts, status and error codes.

- Planning emits `conversation_started`, `planner_decision` and
  `plan_validated` when execution validation succeeds.
- Execution emits `task_scheduled`, `agent_started`, `agent_completed`,
  `agent_failed` and `task_blocked`. Parallel workers can interleave.
- Approval emits `approval_requested` and `approval_resolved`. Terminal
  events are `execution_completed` and `execution_failed`; partial
  completion carries status `partial`.

The SSE endpoint is read-only and works with ASGI and local WSGI. It polls
the journal independently of the submitting request and periodically closes
so EventSource can reconnect with its cursor. A fresh page reads messages and
execution from checkpoints and can replay the journal. Refresh or SSE
disconnect does not start a graph. Approval and message POSTs remain
synchronous until completion or pause, with separate PostgreSQL connections
for checkpoint and journal writes.

## Security and limits

- Requests require Django session authentication, staff status, and active
  company membership. The active company comes from the server session, or
  the user's first membership by company ID. Signed threads and ownership
  checks apply to every conversation endpoint. SSE also rechecks current
  membership and staff status while streaming.
- Browser JSON cannot set identity, permissions, mode or specialist registry.
  Real mode requires the server to set `AGENTIX_SUPERVISOR_CONSOLE_MODE=real`.
  Optional project IDs are checked against the authenticated company.
- Browser views project structured results and citation links from validated
  tasks. Raw tool inputs, transport errors and provider metadata stay on the
  server. Mock approval inputs are explicitly allowlisted. The console
  renders content as text and limits citation links to HTTP(S).
- The journal does not prune old events or checkpoint data automatically.
  Configure retention separately. A process crash can leave a submitted
  operation incomplete. The receipt prevents replay and the checkpoint
  remains available for inspection. There is no automatic recovery outside
  a saved approval pause. The event journal and checkpoints commit separately.

## Verification

All nine Phase 06 tests passed on a disposable PostgreSQL database with
`DB_NAME=agentix_phase06_a7f137`. A second disposable database with
`DB_NAME=agentix_phase05_a7f137` passed 125 tests (the 122 prior tests and
three Phase 06 graph tests). Its six console database tests were skipped
because they require the Phase 06 database prefix. Django removed both
test databases. No live provider requests were made.

The focused suite covers staff and company authorization, CSRF, request
deduplication, state recovery, structured output projection, parallel task
events, errors, approvals, blocking, ASGI SSE, and cursor replay. Django
system checks, migration dry run, dependency checks, JavaScript syntax,
and Git diff checks passed.

Run the focused suite from `agentix_backend` using a fresh disposable
`DB_NAME` beginning with `agentix_phase06_`:

```powershell
python manage.py test orchestrator.test_supervisor_console --noinput
```

## Disposable browser test for project creation

The console exposes `database.create_project` only in real mode with
`AGENTIX_SUPERVISOR_CONSOLE_TEST_WRITES=true`. Before serving the workflow,
Django, the checkpoint saver and the event journal each query PostgreSQL
for the actual database name. Any name other than `test_Agentix` is rejected.
The console also requires an active staff session, company membership, CSRF,
thread ownership and the existing writer role and approval checks.

Run from `agentix_backend` in PowerShell 7.5 or later:

```powershell
$env:DB_NAME = 'test_Agentix'
$env:AGENTIX_CHECKPOINT_DSN = ''
$env:AGENTIX_SUPERVISOR_CONSOLE_ENABLED = 'true'
$env:AGENTIX_SUPERVISOR_CONSOLE_MODE = 'real'
$env:AGENTIX_SUPERVISOR_CONSOLE_TEST_WRITES = 'true'
..\.venv-ml\Scripts\python.exe manage.py prepare_supervisor_ui_test
..\.venv-ml\Scripts\python.exe manage.py changepassword agentix-ui-owner
..\.venv-ml\Scripts\python.exe manage.py runserver 127.0.0.1:8001
```

The empty checkpoint DSN makes the saver use the Django database settings
for this process. The preparation command refuses other databases and
provisions the existing checkpoint and journal tables. It creates an
active staff account with the owner role in a dedicated synthetic company
and five active, available employees skilled in Flutter and Dart. A newly
created account has an unusable password until you set it interactively.
Run `changepassword` only when setting or changing that account's password.

Sign in at [the local test login](http://127.0.0.1:8001/admin/login/?next=/dev/supervisor/)
and open [the console](http://127.0.0.1:8001/dev/supervisor/). Confirm the
header identifies test database writes with approval. In a new conversation,
ask for a Flutter e-commerce specification, project creation after approval,
and five employee recommendations. Include a future deadline in ISO
`YYYY-MM-DD` form and request Flutter and Dart skills. Inspect the draft
specification and proposed saved fields before approving. After approval,
the plan shows the saved project ID, deadline and requirement count, followed
by XGBoost recommendations. Leave the optional existing Project ID field
blank for a new project. Sending this request in real mode can use API quota.

The Django tests use mocked provider responses. The browser API workflow
test exercises PostgreSQL writes, the receipt and real XGBoost on isolated
synthetic fixtures. It removes only its own temporary records. Use the
focused fixture test procedure for the persistent `test_Agentix` database,
never a Django runner invocation that would drop or flush it.

Verification passed ten workflow and transaction tests on `test_Agentix`
and twelve console/API regressions in a separate disposable runner database,
including rejection of that database in write mode. Both live connections
reported `test_Agentix` for the prepared fixtures. An unsaved Flutter/Dart
project fixture ranked all five synthetic employees with real XGBoost.
No live provider calls were made.

## Multi-turn deadlines and write approval

The real Supervisor now retains the original request and authoritative
deadline in the conversation checkpoint while clarification is pending.
It accepts an ISO date-only reply in that context and binds the validated
date to the Project and Database tasks. A new explicit create-and-match
brief replaces the pending request. `Cancel` or `start over` clears it.
The date comes from the user's request or clarification reply, never
from the planner's task data.

For the authorized create-and-match workflow, a missing date is handled
before the planner call. If the planner still asks for ordinary chat
approval or repeats the deadline question when the date is already known,
the server builds the standard validated Project → Database → Matching
chain. Database creation still pauses at the authenticated LangGraph
approval interrupt. Typing `yes` cannot resume that interrupt.

The historical Flutter thread showed a chat approval question, followed by
two deadline questions and `invalid_plan`. Its checkpoints did not retain
the rejected rule, dependency or Pydantic error path. New planner
validation diagnostics retain safe codes and rule details in the
checkpoint and logs. For the manual retest, start a fresh conversation or
resend the complete project brief with its ISO date.
