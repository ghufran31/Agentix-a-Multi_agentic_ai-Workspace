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

The specification includes an optional ISO date (`YYYY-MM-DD`) deadline.
The Project Agent preserves a user-supplied date exactly and leaves the field
null otherwise; it never infers a deadline from milestone durations.

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

## Flutter console failure diagnosis

The saved execution for the unsaved Flutter e-commerce specification reached
`output_validation` and returned `project_planning_failed`. Its checkpoint
recorded three Project model invocations and three responses, with no saved
provider HTTP status or provider error code. Supervisor planning used Groq
`openai/gpt-oss-120b`; the configured Project specialist used the same
provider and model. The failure was returned by the Project Agent before the
adapter could publish a specification.

The older checkpoint did not retain the parser category, finish reason or
raw response. It cannot distinguish a missing or invalid field from invalid
JSON or truncation. The current Groq model supports tool use and native JSON
Schema in separate requests, so this evidence does not establish a transport
incompatibility. The existing two-pass transport was retained.

The synthesis prompt now explicitly identifies the required specification
sections. Both mappings and already-typed outputs are revalidated. New
failures store bounded Pydantic error categories and allowlisted finish
reasons, without raw provider replies or payload values. The console shows
the Project failure stage alongside the error code.

### Repeated Flutter request

The later `task1` run saved `output_validation`, Pydantic `model_type`,
and finish reason `stop` after three model responses. Those saved fields
confirm the updated diagnostic code was active on the Project Agent path.
Pydantic expected a model-shaped object at some point in the output. The
checkpoint omitted the rejected field path and input, so it cannot identify
the exact field. The finish reason did not report a token-limit truncation.

The adapter and checkpoint preserved the diagnostics. The original event
journal entry only saved the error code, and the execution response omitted
validation categories and finish reason. Both paths now use the same
allowlisted projection. The execution response can display the saved details
for this older run. Existing journal entries remain as originally written.
No live requests were made during the diagnosis.

### Structured-output field diagnostics

New Pydantic failures record bounded `validation_issues` entries with a
schema-checked `loc`, category `type`, `expected_type`, and
`received_type`. The model's safe finish reason is preserved separately.
Unknown response keys are represented as `<unknown>`. A missing value
has received type `missing`. No input values, arbitrary keys, provider
response bodies, or validator messages are included. The console displays
these details in task state and newly emitted failure events.

Synthesis distinguishes LangChain's `raw` / `parsed` / `parsing_error`
envelope from a bare structured dictionary or a typed Pydantic response.
The synthesis prompt describes the nested shapes and how to use tool
evidence. Project models enforce strict scalar types from the first Pydantic
parse. The old `model_type` checkpoint still has no field location.

### Parallel Flutter request

The successful single Project execution recorded three provider requests and
three responses. The parallel Project execution received two responses,
then the synthesis request was rejected with HTTP 413 and provider code
`rate_limit_exceeded`. No synthesis response reached Pydantic, so there
was no parser category, finish reason, or validation field path. The
installed Groq SDK maps HTTP 413 to `APIStatusError`.

The Project task brief was 352 characters in the parallel run and 116 in
the single run. The saved checkpoint contains neither the complete provider
request size nor quota headers, so the longer brief and concurrent requests
cannot establish which provider threshold was exceeded. Both workers started
before either completed. The Research result and its citations remained
separate from Project's failed result.

The Project adapter now reports the specific 413 plus
`rate_limit_exceeded` combination as `rate_limited`, retaining the HTTP
status and provider code in console state and new failure events. Parallel
scheduling and validation are unchanged. If future controlled observations
tie failures to concurrent provider use, start with one in-flight request
per Groq quota scope and a bounded queue. A per-request size limit instead
calls for reducing synthesis input or output budget.
