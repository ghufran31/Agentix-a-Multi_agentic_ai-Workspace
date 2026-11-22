# Orchestrator progress

## Current specialist-agent track · 2026-11-22

- Completed before this phase: 1/10 — Database Agent.
- Currently building: 2/10 — Project Planning Agent.
- Agent 02 implementation and 33 combined automated tests pass, but the full
  mandatory live Groq A–I matrix is not complete because the configured Groq
  organization reached its 200,000-token daily limit during Test C.
- Remaining to complete while Agent 02 awaits live verification: 9.
- Agent 03 is implemented and partially live-verified. The PostgreSQL ranking
  path passed, while conversational follow-up and invalid-project messaging
  need work. The LangGraph Supervisor has not started.

Do not mark Agent 02 as 2/10 complete until all required live scenarios pass
on the final implementation.

> Historical record only: the prototype described below was removed on
> 2026-11-22. The current app is a minimal Django shell with its original
> `ml_engine` files, artifacts, and migrations preserved. No phase below is
> currently implemented in the app.

## 2026-11-22 · Phase 01 complete

Added the in-process registry, Pydantic task and plan validation, and a
LangGraph graph that initializes and preserves typed state. The foundation
can discover mock agents by capability and has no handler dispatch.

Python 3.13.17 resolved the following additions. All five were previously
absent. No installed package needed a version change.

| Installed package | Version | Purpose |
| --- | --- | --- |
| langgraph | 1.2.24 | StateGraph and message reducer |
| langgraph-checkpoint | 4.3.2 | Required by LangGraph |
| langgraph-prebuilt | 1.1.3 | Required by LangGraph |
| langgraph-sdk | 0.4.14 | Required by LangGraph |
| ormsgpack | 1.13.1 | Required by the checkpoint package |

PyPI showed [LangGraph 1.2.24](https://pypi.org/project/langgraph/1.2.24/),
[LangChain Core 1.8.4](https://pypi.org/project/langchain-core/1.8.4/),
[LangChain Groq 1.2.1](https://pypi.org/project/langchain-groq/1.2.1/), and
[LangGraph Checkpoint 4.3.2](https://pypi.org/project/langgraph-checkpoint/4.3.2/).
Core and Groq already matched their installed pins. The full
[LangChain 1.5.2](https://pypi.org/project/langchain/1.5.2/) package and the
[PostgreSQL checkpointer 3.2.1](https://pypi.org/project/langgraph-checkpoint-postgres/3.2.1/)
were researched and deferred. Groq SDK 1.7.0 and Pydantic 2.14.4 stayed pinned.

Installation from the root requirements succeeded. `pip check` and
`manage.py check` passed. `manage.py test orchestrator` passed all 26 tests,
including seven new foundation tests and the existing ML and mocked LLM
factory tests. No live Groq call was made.

## 2026-11-22 · Phase 02

Added structured Groq planning, an enabled capability catalog scoped by a
trusted per-call allowlist, and deterministic input, approval, dependency,
and size checks. The graph stores a separate planning outcome and preserves
existing state. No dependency upgrades were required.

Verification on Python 3.13: all 12 focused planner tests and all 38
orchestrator tests passed. Django system checks, `pip check`, and
`git diff --check` passed. The installed Groq structured-output parser was
tested with mocked generation. Live provider behavior was not tested.

## 2026-11-22 · Phase 03

The Supervisor now runs validated plans in dependency waves. Mock async
handlers receive typed inputs and isolated prerequisite results. The worker
rechecks authorization, validates outputs, bounds cooperative execution time,
and blocks approval-required tasks. Caller-supplied run history is preserved.

All 47 orchestrator tests passed, including nine execution tests. An
async barrier proved overlap for two and three independent workers.
Django checks, `pip check`, and `git diff --check` passed. On this Windows
host the async tests needed local loopback socket access. Groq was mocked.

## 2026-11-22 · Phase 04

Added an ownership-gated conversation service with in-memory checkpoints,
isolated threads, and a configuration path for the optional PostgreSQL saver.
New turns restore history and keep prior run results. Interrupted work returns
`recovery_required` without replay. PostgreSQL provisioning and integration
with authenticated conversation ownership await approval and implementation.

All 54 orchestrator tests passed, including seven new checkpoint tests and
the Phase 03 concurrency test. Django checks, `pip check`, and
`git diff --check` passed. PostgreSQL configuration was mocked. No checkpoint
tables were created and no live Groq request was sent. LangGraph emits a
warning for the explicit durability mode on the unsaved worker graph. This
mode prevents the worker from inheriting synchronous checkpoint writes.

## 2026-11-22 · Phase 05

Added structured failures, bounded opt-in retries, and run-level limits on
concurrent workers and scheduling rounds. In-memory checkpointed runs can
pause for approval and resume the matching task after ownership, approval
authority, and execution permissions are checked. A stale decision cannot
consume a later interrupt, and completed tasks remain in the same run.

All seven focused recovery tests and all 61 orchestrator tests passed.
Django checks, `pip check`, and `git diff --check` passed. The existing
LangGraph durability warning remains. Tests used mocked Groq and handlers.
PostgreSQL provisioning, cross-process coordination, and authenticated
application wiring remain pending.

## 2026-11-22 · Phase 06

Verified single, sequential, parallel, and mixed workflows with fixture
directory, matching, research, and report handlers. The tests use the real
Groq structured-output parser with mocked generation and in-memory state.
They cover direct dependency handoff, new turns, authorization, approval,
rejection, limits, and recovery without replay.

The durability warning came from an explicit durability mode on an unsaved
worker graph. Removing that option alone would inherit the parent graph's
synchronous mode. The worker now runs in a fresh context while parent
checkpoint writes remain synchronous. A regression test treats the warning
as an error. Scalar output from a root schema is rejected before it reaches
the object-shaped result state.

All 10 focused integration tests and all 71 orchestrator tests passed.
Django checks, `pip check`, and `git diff --check` passed. Tests used no live
Groq calls or business database writes. PostgreSQL checkpoints remain optional
and unprovisioned. Runtime identity wiring and coordinated cross-process
writes remain separate production work.

## 2026-11-22 · Phase 07

Added authenticated caller resolution with active company membership,
verified conversation scope, and five read-only Database Agent capabilities.
Fixed ORM queries return paged employee and project data and bounded nested
skills and requirements. Membership is rechecked at dispatch and enforced
in every business query. Matching context returns stored source fields for
Phase 08 without running the model.

PostgreSQL fixtures cover company isolation, revoked membership, projected
fields, pagination, scoped dependency results, and bounded related queries.
The tests use Django's isolated test database and mock Groq. The server must
still supply a trusted ownership callback when wiring an application entry
point. PostgreSQL checkpoint provisioning and cross-process coordination
remain separate work.

All 172 tests in the combined orchestrator and related Django suite passed.
After moving the live membership check inside the conversation lock, all 80
orchestrator tests passed again, including nine Database Agent tests.
Django system checks, `pip check`, and `git diff --check` passed.

## 2026-11-22 · Phase 08

The Matching Agent now consumes one direct, verified Database Agent
prerequisite. It revalidates source, shape, project, and live company scope
before adapting records to the existing engine. It refuses partial pages and
truncated requirements or skills. Missing employee features can produce a
clearly labeled evaluable subset. Output scores retain their synthetic-label
limitations.

Eight focused tests passed. A PostgreSQL fixture reproduced the saved
reference score of 0.9938564 with real artifacts. Separate integration
tests mocked inference and Groq. No artifact was modified.
All 137 tests in the combined orchestrator, workforce, projects, and
companies suite passed. Django system checks, `pip check`, and
`git diff --check` also passed.

## 2026-11-22 · Phase 09

Implemented the opt-in developer chat at `/agentix/test/`. It binds one
active conversation to the authenticated staff member's session and
selected company. It renders Supervisor messages, run diagnostics,
validated database and ranking outputs, and pending approval actions.

Seven focused HTTP and presentation tests passed with an isolated in-memory
SQLite test database. A separate run of 71 related Django app and
orchestrator unit tests passed under that test-only database override.
PostgreSQL-backed execution tests and the full orchestrator
suite remain unverified on this host. Automatic approval review timed out
for the requested test command, and the sandbox denied the PostgreSQL
loopback connection before test setup. Django system checks, `pip check`,
and `git diff --check` passed. Django found both static assets.

Django detected a configured Groq key and the legacy Llama 3.3 model ID.
Live provider smoke testing was deferred until the automated execution
tests can pass. Live database and matching checks also need an explicitly
allowlisted staff user and an authorized company. See the architecture
guide for startup and access configuration.

No subsequent phase has started.
