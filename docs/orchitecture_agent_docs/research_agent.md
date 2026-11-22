# Agent 05 — Web Research

Searches public sources with Tavily Basic, reads bounded webpage excerpts,
and validates a structured summary against evidence from the current turn.

## Source

- [Entry point](../../agentix_backend/orchestrator/agents/research/agent.py)
- [Registered tools and source helpers](../../agentix_backend/orchestrator/tools/research/)
- [Schemas](../../agentix_backend/orchestrator/agents/research/schemas.py)
- [System prompt](../../agentix_backend/orchestrator/agents/research/prompts/system.md)

## Tools and inputs

| Registered name | Input and responsibility |
| --- | --- |
| `search_web` | `SearchInput`: `query: str`, `max_results: int` (3–5, default 4), `include_domains: list[str]`, and optional `time_range` (`day`, `week`, `month`, `year`). Returns normalized titles, URLs, and snippets. |
| `read_webpage` | `PageInput` accepts `url: str` up to 2,048 characters and extracts bounded HTML or text evidence. |

Call `execute_research(question, conversation=(), *, model_name=None,
agent=None)`. `ResearchRequest` validates a nonempty `question: str` up to
4,000 characters. Pass optional history as a sequence of `(role, content)`
pairs. No company context is required.

## Results

- `ResearchResult` has `question: str` and `status` (`ok`, `partial`, or
  `error`), `summary: Summary | None`, `sources: list[Source]`,
  `errors: list[str]`, `tool_calls: list[dict]`, `tool_results: list[dict]`,
  integer `model_responses` and `tokens`, and nullable `provider_status: int`,
  `provider_code: str`, and `provider_message: str`.
- `Summary` contains `answer: str`, `findings: list[Finding]`, and
  `comparisons` / `limitations` as lists of strings. Each `Finding` has
  `claim: str` and `urls: list[str]`. Each `Source` contains
  `url: HttpUrl` and `title`, `excerpt`, `provider` strings.
- `ok` has a validated summary and cited sources without recorded tool
  errors. `partial` has a grounded summary plus errors. `error` can omit the
  summary or include a local explanation with empty findings after failed
  search. Examples include `missing_tavily_key`, `search_quota`, `no_results`,
  and `invalid_or_ungrounded_summary`. There is no clarification payload.
- Tool results may report search request counts, credits, and HTTP status.
  Citation validation checks URL membership in retrieved evidence, not whether
  the source logically supports each claim.

## Security, integration, and testing

Uses LangChain, Groq, Tavily, and HTTPX. Django loads the environment, but
research requires no business database access. Page retrieval checks public
addresses, pins the checked IP, and checks redirect destinations. Treat page
content as untrusted. A future Supervisor should preserve citation provenance
and route on `status` before forwarding findings.

Run `python manage.py test orchestrator.agents.research.tests` or the
`test_research_agent` console. Ten focused tests passed after Tavily was
added. The direct Tavily test returned four URLs for “Python official
documentation,” using one request and one credit. The combined Groq + Tavily
scenario remains unverified. See the [Research Agent guide](../orchestrator/RESEARCH_AGENT.md).
