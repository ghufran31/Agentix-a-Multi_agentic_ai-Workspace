# Agent 02 — Project Planning

Converts project ideas into validated proposals covering requirements,
technology, staffing, risks, and milestones. It can request clarification and
uses an optional company skill taxonomy. Planning does not persist records.

## Source

- [Entry point](../../agentix_backend/orchestrator/agents/project/agent.py)
- [Registered tools](../../agentix_backend/orchestrator/tools/project/)
- [Schemas](../../agentix_backend/orchestrator/agents/project/schemas.py)
- [System prompt](../../agentix_backend/orchestrator/agents/project/prompts/system.md)

## Tools

| Registered name | Responsibility |
| --- | --- |
| `analyze_project_description` | Extract requirements and essential gaps |
| `prepare_project_specification` | Normalize proposal inputs |
| `recommend_technology_stack` | Propose a stack while respecting required choices |
| `compare_frameworks` | Compare known tradeoffs |
| `identify_project_roles_and_skills` | Identify staffing and map company skills when available |
| `generate_project_roadmap` | Outline dependencies, phases, milestones, and risks |
| `create_complete_planning_evidence` | Combine planning tool outputs |

## Calling and results

Call `execute_project_task(context, task, conversation=None, model_name=None,
agent=None, structured_model=None)`. Supply natural-language `task` and pass
`context=None` for general planning or a trusted company context for taxonomy
lookups. Prior turns may be role/content dictionaries or LangChain messages.

- `ProjectAgentResult` has `answer: str`, `success: bool`,
  `structured_output: ProjectAgentOutput | None`, `tool_names: list[str]`,
  `tool_executions: list[PlanningToolExecution]`, `validation_errors: list[str]`,
  and integer `model_calls` / `model_requests`. Tool executions contain
  `name: str`, `input: dict`, and `output: dict`.
- `ProjectAgentOutput` has `outcome` (`specification`, `clarification`, or
  `unsupported`), `response: str`, nullable `specification` and `clarification`,
  and `persistence_performed: bool` constrained to false.
- `specification` requires `ProjectSpecification` with name, description,
  project type, typed features, functional requirements, technology stack,
  roles, skills, and milestones. Additional fields capture nonfunctional
  requirements, constraints, assumptions, risks, limitations, and missing data.
- `clarification` requires `ClarificationOutcome` with `understood_request: str`,
  `questions: list[MissingInformation]`, and `retained_requirements: list[str]`.
  `MissingInformation` carries `field`, `question`, and `impact` strings plus
  an `essential: bool` flag. Nonblocking gaps can remain in
  `ProjectSpecification.missing_information`.
- `unsupported` carries neither nested payload. Success means a validated
  outcome, including a clarification or unsupported request. Provider or
  validation failure can leave `structured_output=None` with diagnostics in
  `validation_errors`; `answer` may contain an unvalidated fallback.

## Security, integration, and testing

Uses LangChain and Groq, with a separate tool-free structured-output pass.
Optional taxonomy reads use PostgreSQL and the supplied company context.
A future Supervisor should branch on `outcome` and treat all specifications
as proposals. The agent has no persistence or live research tool.

Run `python manage.py test orchestrator.agents.project.tests` or the
`test_project_agent` console. Automated tests passed. The live matrix
remains incomplete after the reported quota limit.
See the [Project Agent guide](../orchestrator/PROJECT_AGENT.md).
