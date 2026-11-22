# Agent 03 — Employee Matching

Ranks eligible company employees against a saved project's requirements.
The preserved feature pipeline and XGBoost classifier calculate scores.
Groq routes tool calls. A ranking follow-up can explain a saved result
using observed features without attributing causes to individual scores.

## Source

- [Entry point](../../agentix_backend/orchestrator/agents/matching/agent.py)
- [Registered tools](../../agentix_backend/orchestrator/tools/matching/context_tools.py)
- [Schemas](../../agentix_backend/orchestrator/agents/matching/schemas.py)
- [System prompt](../../agentix_backend/orchestrator/agents/matching/prompts/system.md)
- [ML engine](../../agentix_backend/orchestrator/ml_engine/)

## Tools and inputs

| Registered name | Input and responsibility |
| --- | --- |
| `get_project_matching_context` | Positive integer `project_id`. Fetches company-scoped project requirements. |
| `rank_project_employees` | `MatchingRequest`: positive `project_id: int`, `top_n: int` (1–25, default 5), `available_only: bool`, optional `role_filter: str`, and `skill_filter: list[str]`. Scans candidates in batches, filters and scores them, and returns a bounded ranking. |

Call `execute_matching_task(context, task, conversation=None, model_name=None,
agent=None, *, last_matching=None)` with trusted company context, a task string,
and optional role/content history. A future Supervisor can retain the last
successful `MatchingResponse` per authorized session and pass it as
`last_matching` for ranking explanations.

## Results

- `MatchingAgentResult` contains `success: bool`, `answer: str`,
  `structured_output: MatchingResponse | None`, `tool_names: list[str]`,
  `validation_errors: list[str]`, integer `model_requests` and
  `model_responses`, and `token_usage: dict[str, int]`.
- `MatchingResponse` has `success: bool`, `answer: str`,
  `candidates: list[RankedCandidate]`, `exclusions: list[dict]`,
  `metadata: MatchingExecutionMetadata | None`, and `error: str | None`.
- `RankedCandidate` has integer `employee_id` and `rank`, float
  `model_score` in [0, 1], string `employee_name` (display label),
  `availability_status` and `explanation`, plus string lists
  `matched_skills` and `missing_skills`.
- Metadata includes integer project ID and candidate, eligible, and ranked
  counts, `complete: bool`, string artifact and score descriptions, and
  `warnings: list[str]`. Validation enforces counts, unique IDs, consecutive
  ranks, and descending score with employee ID as tie-breaker.
- A missing or inaccessible project yields `error="not_found"`. Failure
  responses require an error, empty candidates, and null metadata. Missing
  project requirements use descriptive errors. Missing employee features
  appear in bounded exclusion diagnostics. Zero scorable candidates can
  be a successful empty ranking. A provider error may omit structured output.

## Security, dependencies, and testing

Uses PostgreSQL, LangChain, Groq, and the preserved XGBoost artifacts.
The tools recheck active company membership and read scoped records only.
Scores are exploratory classifier outputs from synthetic labels and are
uncalibrated. The agent does not assign employees.

Run `python manage.py test orchestrator.agents.matching.test_matching` or
`test_matching_agent` against an isolated test database. PostgreSQL and
independent XGBoost predictions were verified. The final live invalid-project
turn passed, and the final follow-up correction passed locally.
See the [conversation verification log](../DEVELOPMENT_LOG.md#2026-11-22--agent-03-conversation-fixes).
