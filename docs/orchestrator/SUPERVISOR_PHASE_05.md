# Supervisor Phase 05

Use `SupervisorConversations` in `orchestrator/graph/conversations.py` as the
server-side boundary for persistent Supervisor sessions. The Phase 01–04
builders keep their existing interfaces. Persistent mode defaults to `mock`
with an injected planner and mock executors. Set `mode='planning'` for
validated proposals or `mode='real'` for the Phase 04 read-only adapters.

## Storage and configuration

- Install the pinned dependencies from `requirements.txt`. The official
  `langgraph-checkpoint-postgres` saver stores state, task results and interrupts
  in the dedicated `agentix_checkpoints` PostgreSQL schema.
- `open_postgres_checkpoints()` uses Django's default PostgreSQL connection
  settings. Set the optional `AGENTIX_CHECKPOINT_DSN` in the environment for a
  separate checkpoint database. Keep the DSN private.
- Provision once with `with open_postgres_checkpoints(setup=True): pass`
  from a Django shell using a role allowed to create the schema and saver
  tables. Use `setup=False` (the default) at runtime. Grant the runtime role
  schema usage and read/write access to the checkpoint tables only as needed.
  The context manager closes its dedicated connection. No Django migration
  creates checkpoint tables.
- Use `memory_checkpoints()` for isolated tests. PostgreSQL uses per-thread
  advisory locks across database sessions and synchronous checkpoint writes.
  Keep the Django signing key and the checkpoint database stable across
  restarts. A signed thread ID identifies its mode, company, owner and UUID.

## Conversation and approval contract

1. Construct the service with a registry, checkpoint store and trusted
   `grants(scope)` callback returning allowed capabilities and permissions.
   Call `create_thread(user, company_id)` with the server-authenticated user.
2. Call `turn(thread, user, company_id, request)`. Server-owned
   `project_id` and `project_requirements` may establish context. The service
   verifies saved and new project IDs against the company. Each turn retains
   up to 24 messages and up to 20 previous task results. The planner receives
   up to 12 truncated history messages, bounded requirements, and recent
   result IDs, capability names and statuses. Task references resolve only
   within the current plan.
3. Call `inspect(thread, user, company_id)` to read restored state. For
   approval-gated mock capabilities, independent ready tasks finish first.
   LangGraph then interrupts at one proposed operation at a time.
   `pending_approvals` holds the `ApprovalRequest` with string IDs for the
   approval, thread, execution, task and capability, a summary,
   validated JSON inputs, integer user and company IDs, an operation key,
   an expiration timestamp in Unix seconds, and status `pending`.
4. Call `resume(thread, user, company_id, approval_id=..., execution_id=...,
   approved=True|False)` from a trusted human-facing boundary. Each call
   checks the active Django user, membership, ownership, mode, current role,
   `approvals.decide` grant and capability permissions. Decisions must match
   the outstanding checkpoint interrupt. Replays and forged IDs are refused.
5. Terminal `approval_records` use `approved`, `rejected`, `expired` or
   `invalid`. Expiration is evaluated on resume. Negative decisions block
   the task and its dependents. Completed and unrelated results survive
   resume. A new turn is refused while an execution is paused.

## Limits and security

Real mutation adapters are disabled. The `operation_key()` contract hashes
the thread, execution, task, capability and canonical validated inputs.
Before a write adapter can use it, implement a durable uniqueness and receipt
record atomically with the mutation and verify replay behavior for that
operation. Checkpoints alone cannot guarantee exactly-once side effects.

Treat the checkpoint store as sensitive application data. Protect it from
direct user access and configure retention and backups separately. The bounded
planner context does not prune older stored checkpoints. Recovery is supported
for saved conversation turns and approval interrupts. An unexpected crash
outside an approval pause may leave a pending execution for operator review.
The service does not automatically replay that execution. A single store
serializes conversation calls on its connection. Concurrent task scheduling
inside a run still uses LangGraph worker dispatch.

## Verification

Run `python manage.py test orchestrator.test_persistent_supervisor` from
`agentix_backend`. To enable the PostgreSQL case, set `DB_NAME` to a fresh
disposable name beginning with `agentix_phase05_`, then run the tests without
`--keepdb`. Django creates and removes a database with the `test_` prefix.
The PostgreSQL test uses mock planner and specialist results and tests real
Django membership and role changes on synthetic records.

The full isolated PostgreSQL run passed all 122 orchestrator tests, including
10 Phase 05 tests. The database was removed by Django after the run. The
PostgreSQL case verified interrupt recovery on a reopened connection, lock
contention across two sessions, role revalidation and inactive-user denial.
Django system checks, the migration dry run, dependency checks and Git diff
checks passed. No live LLM or Tavily calls were made.
