# Companies app

## Scope and schema

The app implements only the approved `companies` and `company_users` tables.
It uses Django's configured user model and defines no custom user table.
Explicit database table names preserve the DBML names:

- `Company` maps to `companies`; its unique `created_by_user` one-to-one
  relation maps to `created_by_user_id`.
- `CompanyUser` maps to `company_users`; its `company` and `user` relations
  map to `company_id` and `user_id`. The `(company, user)` pair has a database
  unique constraint.

Company registration through the separate accounts API does not provision a
company. Company creation here records the authenticated creator as
`created_by_user` and, in the same transaction, adds their `owner`
membership.

## Endpoints

All endpoints require JWT authentication and are mounted under
`/api/v1/companies/`.

| Method and path | Behavior |
| --- | --- |
| `POST /` | Create a company; the authenticated user becomes creator and owner. Returns 201. |
| `GET /` | List only companies where the authenticated user has a membership. |
| `GET /<id>/` | Retrieve a company only when the user is a member. |
| `PATCH /<id>/` | Update name, industry, description, email, phone, or address. |
| `GET /<id>/members/` | List safe user profile fields and roles for company members. |

Creation requires a non-empty `name`; optional email is validated as an email
address. A user who already created a company receives HTTP 409. Failed
company or owner-membership inserts are transactionally rolled back. The
database unique constraint also prevents duplicate company memberships.

## Authorization

All company querysets are filtered by the requesting user's membership.
Requests for a company outside that scope return 404, including detail,
members, and patch requests, so the API does not disclose the existence of
another tenant's company.

All members may view accessible company details and membership. **Only the
`owner` role may patch company details.** Admin, manager, and member roles
receive HTTP 403 on an update. This is the least-privilege update policy for
the current scope. Invitations, role changes, and deletion are not
implemented.

The company and member response serializers exclude passwords, password
hashes, token secrets, and internal settings. Membership user data is limited
to `id`, `username`, `email`, `first_name`, and `last_name`.

## Migration and tests

`companies/migrations/0001_initial.py` creates the two approved tables.
Apply it with `python manage.py migrate`. Run the focused suite, including
accounts regression tests, with `python manage.py test companies accounts`.
