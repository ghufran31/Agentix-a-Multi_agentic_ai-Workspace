# Agentix specialist agents

Four standalone LangChain specialists are implemented under
`agentix_backend/orchestrator/`. They use the shared Groq model factory,
agent-specific prompts and tools, and Pydantic result models. Implementation
and live verification are tracked separately.

| Agent | Responsibility | Verification status |
| --- | --- | --- |
| [01 Database](database_agent.md) | Authorized Django ORM operations | Live Groq and isolated PostgreSQL verified |
| [02 Project](project_agent.md) | Project planning and clarification | Automated tests passed, live matrix incomplete |
| [03 Matching](matching_agent.md) | Rank eligible employees for a saved project | PostgreSQL and XGBoost verified, final follow-up correction tested locally |
| [05 Research](research_agent.md) | Search, fetch, and cite public sources | Automated tests and direct Tavily verified, combined Groq + Tavily run pending |

## Future Supervisor integration

The Supervisor is planned. The entry points in these pages are standalone
Python functions. A future Supervisor can wrap each in a node, resolve
authenticated context server-side, and pass validated payloads using
`model_dump(mode='json')`. Inspect status, outcome, and errors before routing
to the next node. Keep conversation state, authorization, and approval
decisions outside model-generated text.

A Project Agent specification is a proposal. Persist it through an authorized
workflow before passing a real project ID to Matching. Research findings can
inform planning while retaining their evidence URLs and limitations.

See the [development log](../DEVELOPMENT_LOG.md) for verification history.
