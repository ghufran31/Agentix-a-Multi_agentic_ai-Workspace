# Workforce app

## Scope

The app implements only these approved tables: `departments`, `employees`,
`employee_ai_profiles`, `skills`, and `employee_skills`. It uses the existing
`companies.Company` model and configured Django user indirectly through
company membership. No other business models or tables are introduced.

The API enforces membership scoping at each queryset and relationship input.
Owners, admins, and managers can create, update, and delete workforce data.
Company members can read but not write. Writes involving an unauthorized
company/resource are rejected; inaccessible detail objects return 404.
Employee-skill assignments are accepted only when the employee's department
company matches the skill company. The database schema does not add a
cross-table check constraint beyond the approved DBML; this relationship
invariant is enforced by the API serializer. Updates to department, employee,
or skill company relationships are also rejected when they would invalidate
existing employee-skill assignments.

## Routes

Every route requires JWT authentication. `<id>` parameters are integer primary
keys.

| Method | Route | Behavior |
| --- | --- | --- |
| `GET`, `POST` | `/api/v1/workforce/departments/` | List accessible departments; create in an authorized company |
| `GET`, `PUT`, `PATCH`, `DELETE` | `/api/v1/workforce/departments/<id>/` | Retrieve, update, or delete an accessible department |
| `GET`, `POST` | `/api/v1/workforce/employees/` | List accessible employees; create in an authorized department |
| `GET`, `PUT`, `PATCH`, `DELETE` | `/api/v1/workforce/employees/<id>/` | Retrieve, update, or delete an accessible employee |
| `GET`, `POST`, `PUT`, `PATCH`, `DELETE` | `/api/v1/workforce/employees/<id>/profile/` | Retrieve, create, update, or delete the employee's AI profile |
| `GET`, `POST` | `/api/v1/workforce/skills/` | List accessible-company skills; create in an authorized company |
| `GET`, `PUT`, `PATCH`, `DELETE` | `/api/v1/workforce/skills/<id>/` | Retrieve, update, or delete a skill |
| `GET`, `POST` | `/api/v1/workforce/employee-skills/` | List accessible assignments; create a same-company assignment |
| `GET`, `PUT`, `PATCH`, `DELETE` | `/api/v1/workforce/employee-skills/<id>/` | Retrieve, update, or delete an accessible assignment |

Create operations return 201, reads and updates return 200, deletes return
204, and serializer validation failures return 400. Duplicate employee codes,
company skill names, profiles, or employee-skill assignments are prevented
by the database constraints; duplicate API submissions are validated or
reported as conflicts.

## Input and model constraints

- Department creation requires `company` and `name`.
- Employee creation requires `department`, `employee_code`, `first_name`, and
  `last_name`; `email` is nullable and validated as an email when supplied.
- Employee AI profiles are nested under an employee; `employee` cannot be
  reassigned through the profile API. Defaults and status choices follow the
  approved DBML.
- Skill creation requires `company` and `name`.
- Employee-skill assignment requires `employee` and `skill`; an optional
  `proficiency` and default-zero `years_experience` follow the schema.

The generated migrations are
`agentix_backend/workforce/migrations/0001_initial.py` and
`agentix_backend/workforce/migrations/0002_alter_department_created_at_and_more.py`.
The second migration records database-side current-timestamp defaults for the
three workforce `created_at` columns and the AI profile's `updated_at`.

## Tests

Run `python manage.py test workforce companies accounts` from
`agentix_backend`. The suite covers CRUD, defaults and validation, all
approved uniqueness constraints, profile uniqueness, company role
permissions, authentication, cross-company read/update/delete isolation,
cross-company foreign-key rejection, same-company employee-skill validation,
and route resolution.
