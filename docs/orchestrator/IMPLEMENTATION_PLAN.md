# Orchestrator implementation plan

The prior orchestration prototype was removed. Its phase-completion notes are
historical and must not be treated as implemented functionality. Rebuild only
after project-owner approval, reusing the preserved `ml_engine` without
changing its files or artifacts.

| Phase | Goal | Acceptance criteria |
| --- | --- | --- |
| 0 · Clean baseline | Preserve the minimal Django app, existing migrations, and `ml_engine`. | Django checks pass; model artifacts load; no orchestration code or routes remain. |
| 1 · Architecture approval | Agree on boundaries, permissions, and state lifecycle before implementation. | Approved design explicitly preserves the database schema and ML contract. |
| 2 · Conversational Supervisor | Add user-facing conversation behavior using the approved orchestration design. | Focused tests cover replies, failures, context, and limits. |
| 3 · Structured requirements and planning | Interpret project goals and validate bounded plans. | Schemas and assumptions are documented and tested. |
| 4 · Authorized execution | Add approved task execution and safe output handoff. | Permissions, approval, retries, and recovery are tested before business writes. |
| 5 · Project and matching workflows | Integrate approved project operations and existing matching. | Company scope, data completeness, and non-assignment behavior are verified. |

Do not begin phases 1–5 without project-owner approval.
