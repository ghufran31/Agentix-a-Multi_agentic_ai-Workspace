# Agent 01 — Database

Runs company-scoped business operations via the Django ORM. It can read
and mutate supported records, summarize relationships, and prepare certain
destructive actions for approval.

## Source

- [Entry point](../../agentix_backend/orchestrator/agents/database/agent.py)
- [Registered tools](../../agentix_backend/orchestrator/tools/database/)
- [Schemas](../../agentix_backend/orchestrator/agents/database/schemas.py)
- [System prompt](../../agentix_backend/orchestrator/agents/database/prompts/system.md)

## Tools

| Area | Registered names and responsibilities |
| --- | --- |
| Company | `get_company`, `update_company`, `list_company_members` |
| Departments | `create_department`, `get_department`, `list_departments`, `update_department`, `delete_department` (prepare), `summarize_department_employees` |
| Employees | `create_employee`, `get_employee`, `list_employees`, `update_employee`, `delete_employee` (prepare), `get_employee_profile`, `update_employee_profile` |
| Employee skills | `manage_employee_skills` (add/update), `unlink_employee_skill` (prepare), `resolve_delete_approval` (resolve a pending operation) |
| Skills | `create_skill`, `get_skill`, `list_skills`, `update_skill`, `delete_skill` (prepare) |
| Projects | `create_project`, `get_project`, `list_projects`, `update_project`, `delete_project` (prepare), `create_project_requirement`, `assign_project_member`, `summarize_project_members` |
| Recommendations | `create_recommendation`, `list_recommendations`, `get_recommendation` (stored records) |
| Duplicates | `detect_duplicates` (bounded employee/project checks) |

## Calling and results

Call `execute_database_task(context, task, conversation=None, model_name=None,
prior_task_data=None, read_only=False)`. Supply natural-language `task` and a
trusted `DatabaseExecutionContext` from `database_context(user, company_id)`.
List tools use bounded pagination. Tool arguments are validated with their
individual input schemas.

- `DatabaseAgentResult` contains `answer: str`, `success: bool`,
  `tool_names: list[str]`, `execution_results: list[ToolExecutionResult]`,
  and `pending_approval: dict | None`.
- Each `ToolExecutionResult` has `success: bool`, `operation: str`,
  `message: str`, `data: dict`, `errors: list[str]`, and
  `pending_approval: dict | None`. Optional collections default to empty.
- Top-level success means no recorded tool execution failed. It can be true
  for a clarification, an empty execution list, or a pending approval.
  Missing information is conversational or in the tool's error details.
  Handle raised exceptions separately.

## Security and future integration

Uses LangChain, Groq, Django ORM, and PostgreSQL. The caller supplies
authenticated company context. Writes generally require owner, admin, or
manager, and company updates require owner. Read-only mode blocks writes.
The approval registry is process-local and binds approvals to user and company.
The resolver accepts an explicit approval argument. A future Supervisor must
gate it with a trusted decision and verify the execution result before
reporting a mutation as complete.

## Testing

From `agentix_backend`, run `python manage.py test orchestrator.tests`.
The `test_database_agent` console requires a test database and defaults to
read-only. See the [console instructions](../../README.md#database-agent)
and the [recorded live Groq and PostgreSQL checks](../DEVELOPMENT_LOG.md#2026-11-22--real-groq-verification).
