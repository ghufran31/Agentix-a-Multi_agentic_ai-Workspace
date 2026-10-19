# Agents app

## Scope

The app implements only the approved `ai_agents` table through the
`AIAgent` model. It stores company, name, type, description, capabilities,
status, and creation-time metadata. Agent records do not execute autonomous
tasks, call tools, or run AI workflows.

## Routes

All endpoints require JWT authentication.

| Method | Route | Behavior |
| --- | --- | --- |
| `GET` | `/api/v1/agents/` | List agents for companies where the requester is a member |
| `POST` | `/api/v1/agents/` | Create an agent record for a company where requester may write |
| `GET` | `/api/v1/agents/<id>/` | Retrieve an accessible agent |
| `PUT`, `PATCH` | `/api/v1/agents/<id>/` | Replace or partially update agent metadata |
| `DELETE` | `/api/v1/agents/<id>/` | Delete an accessible agent record |

Creation returns 201, retrieval and updates return 200, deletion returns 204,
invalid fields or unauthorized company IDs return 400, and detail requests
for inaccessible IDs return 404.

## Request and response fields

- `company`: required company primary key; must be a company where the
  requester has a writer membership.
- `name`: required string, maximum 150 characters.
- `agent_type`: optional nullable string, maximum 100 characters.
- `description`: optional nullable text.
- `capabilities`: optional nullable text metadata; this does not enable the
  described capabilities.
- `status`: optional string, maximum 50 characters; defaults to `active`.
- `id`: generated primary key, returned read-only.
- `created_at`: generated current timestamp, returned read-only.

Responses contain only these schema fields. There are no credential fields.

The model maps to `ai_agents`; migration:
`agentix_backend/agents/migrations/0001_initial.py`.

## Authorization

Company members may list and retrieve agents in their companies. Only
`owner`, `admin`, or `manager` memberships may create, update, or delete. The
company foreign key on create and update is restricted to companies where the
requester has one of these writer roles. Agent querysets are scoped to the
requester's memberships, so foreign-company IDs return 404 for detail,
update, and delete.

## Tests

Run `python manage.py test agents companies accounts workforce documents
integrations` from `agentix_backend`. Tests cover CRUD, defaults and field
validation, authentication, company roles, company scoping, unauthorized
company IDs, inaccessible records, response field safety, and route
resolution.
