# Recommendations app

## Scope

The app implements only the approved `recommendations` table, using the
existing `projects.Project`, `workforce.Employee`, and `agents.AIAgent`
models. It stores recommendation records. It does not generate
recommendations, run an AI scoring algorithm, or call an external AI service.

All endpoints require JWT authentication. Users can read recommendations for
projects belonging to their member companies. Only company owners, admins,
and managers can create, update, or delete recommendation records. Inaccessible
recommendation IDs and project IDs in the nested listing return 404.

## Routes

`<id>` and `<project_id>` are integer primary keys.

| Method | Route | Behavior |
| --- | --- | --- |
| `GET`, `POST` | `/api/v1/recommendations/` | List accessible records or create one for a writable project |
| `GET`, `PUT`, `PATCH`, `DELETE` | `/api/v1/recommendations/<id>/` | Retrieve, replace, update, or delete an accessible record |
| `GET` | `/api/v1/recommendations/projects/<project_id>/` | List records for one accessible project |

Create returns 201, retrieval and updates return 200, deletes return 204,
invalid data returns 400, writes by read-only members return 403, and
inaccessible IDs return 404.

## Request and response fields

Create requires:

- `project`: project ID belonging to a company where the requester has an
  owner, admin, or manager membership.
- Exactly one of `employee` or `ai_agent`:
  - `employee`: existing employee ID; the employee's department company must
    match the project company.
  - `ai_agent`: existing AI agent ID; the agent company must match the
    project company.
- `score`: required decimal, up to 8 total digits and 5 decimal places.
- `rank`: required integer.

Optional fields:

- `recommended_role`: nullable string, maximum 150 characters.
- `reason`: nullable text.
- `status`: string, maximum 50 characters; defaults to `pending`.

`id` and `created_at` are generated and read-only. The nested project-list
route accepts no request body; its project is selected by the URL.

The exactly-one-target invariant is validated by the serializer and enforced
by the database constraint `recommendation_exactly_one_candidate`. During a
partial update, setting one non-null target automatically clears the other.
Setting both targets to null or supplying both non-null targets is rejected.

Responses contain only the fields above; no generation or scoring behavior is
implied by the stored `score` value.

The model maps to `recommendations`; migration:
`agentix_backend/recommendations/migrations/0001_initial.py`.

## Tests

From `agentix_backend`, run:

```powershell
python manage.py test recommendations projects agents workforce companies accounts documents integrations
```

Tests cover model defaults, decimal and required-field validation, CRUD,
project-scoped listing, authentication, role permissions, database target
exclusivity, and company-isolation checks for projects, employees, and agents.
