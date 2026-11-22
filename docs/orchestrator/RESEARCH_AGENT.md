# Agent 05 Research Agent

Set `TAVILY_API_KEY` in the repository-root `.env` loaded by Django.
Keep credentials in that ignored file or in the process environment. Groq uses
the existing `GROQ_API_KEY` and `GROQ_MODEL_NAME` configuration.

`search_web` requests 3–5 results through Tavily Basic, with optional domain
and freshness filters. Search diagnostics show requests and credits when
reported. Missing credentials, exhausted quota, and unavailable search produce
structured errors. `read_webpage` checks public addresses and redirects and
returns bounded HTML or text excerpts. Each finding must reference a URL
observed in tool output during the current turn. A cited search snippet and
a fetched page are identified separately.

From `agentix_backend`:

```powershell
..\.venv-ml\Scripts\python.exe manage.py test_research_agent
..\.venv-ml\Scripts\python.exe manage.py test orchestrator.agents.research.tests
```

Use `:reset` to clear console history or `:quit` to exit. Use
`--question` for a scripted turn. The console uses no business database data.
