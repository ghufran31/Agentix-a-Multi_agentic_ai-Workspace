# Project Planning Agent

## Scope

The independent Project Agent is implemented under
`agentix_backend/orchestrator/agents/project/`. It analyzes software project
ideas and returns either a strongly typed project specification, targeted
clarification questions, or an unsupported-operation result. It does not save
projects, call the Database Agent, perform employee matching, invoke
`ml_engine`, or coordinate other agents.

The future Supervisor can serialize `ProjectAgentOutput` without losing
features, functional and nonfunctional requirements, technology decisions,
roles, skills, milestones, constraints, assumptions, missing information, or
limitations.

## Runtime design

`build_project_agent()` uses LangChain's supported `create_agent` API and the
shared cached Groq factory. Planning tools perform deterministic extraction,
technology comparison, company skill-taxonomy lookup, and roadmap generation.
They never write business data.

Groq does not allow native JSON response mode and tool calling in the same
request. Execution therefore has two explicit stages using the same configured
model:

1. the LangChain agent handles conversation and calls planning tools;
2. a tool-free Groq native JSON-schema pass validates `ProjectAgentOutput`.

The testing console reports both successful model responses and attempted API
requests so provider errors are not hidden. `GROQ_MAX_TOKENS` defaults to
16,384 and can be configured through the environment.

## Planning tools

- `analyze_project_description` extracts explicit statements, named features,
  technology constraints, deadlines, and essential gaps.
- `prepare_project_specification` normalizes a proposal without persistence.
- `recommend_technology_stack` preserves user overrides and explains choices.
- `compare_frameworks` describes known tradeoffs without claiming live research.
- `identify_project_roles_and_skills` maps roles and skills and, with an
  authenticated company context, distinguishes existing skill IDs from
  proposed taxonomy entries.
- `generate_project_roadmap` creates ordered phases, milestones, dependencies,
  risks, and assumptions.
- `create_complete_planning_evidence` composes the same deterministic helpers
  for broad plan requests, reducing repeated model/tool round trips.

## Console

From `agentix_backend`:

```powershell
..\.venv-ml\Scripts\python.exe manage.py test_project_agent
..\.venv-ml\Scripts\python.exe manage.py test_project_agent --scenario all --summary --model openai/gpt-oss-120b
```

Add `--report-file ..\docs\orchestrator\PROJECT_AGENT_LIVE_RESULTS.json` to
write a sanitized in-repository record containing exact turns, tool diagnostics,
structured output, validation, and API request/response counts. The command
refuses report paths outside the repository.

Interactive commands are `:reset`, `:structured`, `:tools`, `:scenarios`,
`:scenario NAME`, and `:quit`. Optional `--user-id` and `--company-id` arguments
enable read-only mapping against the authenticated company's skill taxonomy.
The two arguments must be supplied together.

## Boundaries and limitations

- Conversation continuity is supplied through prior user and assistant turns;
  the standalone command keeps it in process and `:reset` clears it.
- No project ID can be returned because this agent has no persistence tool.
- Technology recommendations use supplied requirements and known tradeoffs;
  no live research capability is registered.
- Delivery estimates are planning assumptions, not commitments.
- Provider quotas and availability can prevent live requests even when local
  validation and mocked tests pass.
