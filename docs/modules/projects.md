# Projects app

## Scope

The app implements only the approved `projects`, `project_requirements`, and
`project_members` tables. It uses the existing `companies.Company`,
`workforce.Employee`, and `agents.AIAgent` models. Recommendations are not
implemented.

All endpoints require JWT authentication. Projects and nested resources are
visible only to members of the project's company. Owners, admins, and
managers may create, update, or delete; company members have read-only access.
Inaccessible project or nested-resource IDs return 404.

## Routes

`<project_id>` and `<id>` are integer primary keys.

| Method | Route | Behavior |
| --- | --- | --- |
| `GET`, `POST` | `/api/v1/projects/` | List accessible projects; create in an authorized company |
| `GET`, `PUT`, `PATCH`, `DELETE` | `/api/v1/projects/<id>/` | Retrieve, replace, partially update, or delete an accessible project |
| `GET`, `POST` | `/api/v1/projects/<project_id>/requirements/` | List or create requirements for an accessible project |
| `GET`, `PUT`, `PATCH`, `DELETE` | `/api/v1/projects/<project_id>/requirements/<id>/` | Retrieve, replace, update, or delete a requirement under that project |
| `GET`, `POST` | `/api/v1/projects/<project_id>/members/` | List or assign members to an accessible project |
| `GET`, `PUT`, `PATCH`, `DELETE` | `/api/v1/projects/<project_id>/members/<id>/` | Retrieve, replace, update, or remove a project-member assignment |

Create operations return 201, reads and updates return 200, and deletes return
204. Invalid input returns 400, authenticated write attempts by read-only
members return 403, and inaccessible project/resource IDs return 404.

## Request and response fields

### Projects

Create requires:

- `company`: company ID where the requester has an owner, admin, or manager
  membership.
- `name`: required string, maximum 255 characters.

Optional writable fields are `description`, `status` (maximum 50; defaults to
`draft`), `priority` (maximum 50; defaults to `medium`), `start_date`, and
`deadline`. `id` and `created_at` are generated and read-only. The company
may be changed only to another writable company; a change is rejected if it
would make an existing employee or AI agent assignment inconsistent with the
project's company.

### Project requirements

Create requires `requirement` text. `required_skills`, `required_roles`,
`deadline`, and `priority` (maximum 50; defaults to `medium`) are optional.
The nested URL determines the project; `project`, `id`, and `created_at` are
read-only in responses.

### Project members

Create requires `member_type` (maximum 50) and exactly one of:

- `employee`: an employee whose department belongs to the project's company;
- `ai_agent`: an AI agent belonging to the project's company.

Providing neither or both returns 400 and is also rejected by the database
check constraint `project_member_exactly_one_candidate`. Optional `role`
(maximum 150) may be null, and `status` (maximum 50) defaults to `active`.
The nested URL determines the project; `project`, `id`, and `assigned_at` are
read-only in responses.

Project status, priority, requirement priority, member type, member role,
and member status are strings rather than enumerations in the approved DBML;
the API does not invent choices for them.

## Migration and tests

The initial migration is
`agentix_backend/projects/migrations/0001_initial.py`. Run the app and
regression tests from `agentix_backend`:

```powershell
python manage.py test projects agents workforce companies accounts documents integrations
```

Tests cover CRUD, field requirements and defaults, the database exactly-one
constraint, authentication, role permissions, company scoping, and rejecting
cross-company employee and AI-agent assignments.
