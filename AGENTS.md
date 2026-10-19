# Instructions for AI agents

Before changing the project, read `README.md` and all relevant documents under
`docs/`, especially `docs/ARCHITECTURE.md`,
`docs/DATABASE_SCHEMA.md`, `docs/CURRENT_STATUS.md`, and
`docs/DEVELOPMENT_LOG.md`.

## Required workflow

1. Implement one app at a time, and only the app currently approved by the
   project owner.
2. Preserve the approved schema in `docs/DATABASE_SCHEMA.md` exactly. Do not
   invent or alter business tables, fields, types, constraints, or relations.
3. Reuse the existing Django project and settings. Do not overwrite unrelated
   work or delete development data.
4. Keep credentials and secret keys out of source code, logs, and committed
   files. Use environment variables for local configuration.
5. Write and run focused tests for each change. Report actual results and
   disclose failures; never claim an unrun test passed.
6. Update the relevant documentation and development log with implemented
   behavior, verification results, and known issues.
7. Review the final Git diff and leave unrelated changes untouched.
8. After completing the currently approved app, stop and wait for the
   project owner's approval before starting another app.

## Current scope

The Django `accounts` app implements registration, JWT login and refresh,
refresh-token blacklisting on logout, and an authenticated safe profile
endpoint. The `companies` app implements only the approved `companies` and
`company_users` tables and their requested APIs. The `workforce` app implements
only departments, employees, employee AI profiles, skills, and employee
skills. The `documents` app implements only company document metadata and
the approved `company_documents` table; it does not upload or store files.
The `integrations` app implements only connection records and status
metadata in the approved `connections` table; it does not authenticate with
external providers or store their credentials. Account registration must not
create a company. The `agents` app implements only company-scoped agent
records and metadata in the approved `ai_agents` table; agent records do not
execute autonomous tasks, call tools, or run AI workflows. The `projects`
app implements only projects, requirements, and project-member assignments
from the approved schema. The `recommendations` app stores company-scoped
recommendation records only; it does not generate recommendations or run an
AI scoring algorithm. After the approved recommendations work is complete,
wait for the project owner's approval before starting another app.
