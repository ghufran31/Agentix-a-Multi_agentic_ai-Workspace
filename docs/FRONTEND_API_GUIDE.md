# Agentix Frontend API Guide

This guide documents the implemented Django REST Framework API as it exists
in this repository. The source of truth for paths and payloads is
`agentix_backend/config/urls.py` and each mounted app's URL configuration,
serializer, view, permission class, and tests. Examples use fake data and
placeholders only.

## Contents

1. [Base URL and HTTP conventions](#base-url-and-http-conventions)
2. [Endpoint index](#endpoint-index)
3. [Authentication and JWT](#authentication-and-jwt)
4. [Company membership and permissions](#company-membership-and-permissions)
5. [Accounts API](#accounts-api)
6. [Companies API](#companies-api)
7. [Workforce API](#workforce-api)
8. [Documents API](#documents-api)
9. [Integrations API](#integrations-api)
10. [Agents API](#agents-api)
11. [Projects API](#projects-api)
12. [Recommendations API](#recommendations-api)
13. [Errors and validation](#errors-and-validation)
14. [Relationships and frontend data flow](#relationships-and-frontend-data-flow)
15. [Postman setup and request examples](#postman-setup-and-request-examples)
16. [Verification checklist and unresolved items](#verification-checklist-and-unresolved-items)

## Base URL and HTTP conventions

The backend origin is environment-specific. For local development, the
README's Django development-server setup uses `http://127.0.0.1:8000`.
Configure the origin once in the frontend rather than hardcoding it:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
```

That variable name is an example for Vite; use the environment-variable
convention of the actual frontend framework. It is the **server origin only**.
The API paths below already include `/api/v1/`; do not append that prefix a
second time.

For JSON requests, send:

```http
Content-Type: application/json
Accept: application/json
Authorization: Bearer {{access_token}}
```

The `Authorization` header is required for all API paths except registration,
login, refresh, and logout. Logout uses the refresh token in its body and is
implemented as a public Simple JWT blacklist view; a bearer access token is
not required by that view. All data is JSON; no multipart file upload route
is implemented.

### Serialization and collection behavior

- Primary keys and foreign keys are JSON integers. Related objects are
  represented by IDs, not nested objects, except the company-member response's
  `user` object.
- Dates use `YYYY-MM-DD`. Date-times use ISO 8601 timestamps with timezone
  information; examples use UTC `Z`.
- DRF `DecimalField` responses are strings (for example `"0.00"`). Send
  decimal values as JSON strings to avoid client-side floating-point loss.
- List endpoints return a plain JSON array. No pagination, filtering,
  search, or ordering backend is configured. No endpoint defines query
  parameters. Extra query parameters are not documented as supported.
- Successful deletes return HTTP 204 with an empty body.
- On update, `PATCH` only changes supplied writable fields. `PUT` is a
  non-partial serializer update: required fields must be supplied, but
  omitted optional fields are not a guarantee of database-row replacement.
  Prefer `PATCH` for targeted changes.
- Writable fields not shown in a request table are either read-only, derived
  from the URL/authenticated user, or not accepted by that serializer.

## Endpoint index

The root Django admin is mounted at `/admin/`; it is not a versioned REST API.
The 32 REST URL patterns below are mounted by the project's actual root URL
configuration. The methods shown are the methods implemented by the
corresponding DRF views.

### Accounts

| Method | Endpoint | Authentication | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/accounts/register/` | Public | Register a Django user |
| POST | `/api/v1/accounts/login/` | Public | Obtain JWT access and refresh tokens |
| POST | `/api/v1/accounts/token/refresh/` | Public | Rotate refresh token and issue access token |
| POST | `/api/v1/accounts/logout/` | Public | Blacklist submitted refresh token |
| GET | `/api/v1/accounts/me/` | Bearer access token | Read safe current-user profile |

### Companies

| Method | Endpoint | Authentication | Purpose |
| --- | --- | --- | --- |
| GET, POST | `/api/v1/companies/` | Bearer access token | List memberships' companies or create one |
| GET, PATCH | `/api/v1/companies/<pk>/` | Bearer access token | Read or owner-update a company |
| GET | `/api/v1/companies/<pk>/members/` | Bearer access token | List company memberships and safe user details |

### Workforce

| Method | Endpoint | Authentication | Purpose |
| --- | --- | --- | --- |
| GET, POST | `/api/v1/workforce/departments/` | Bearer access token | List or create departments |
| GET, PUT, PATCH, DELETE | `/api/v1/workforce/departments/<pk>/` | Bearer access token | Read/update/delete department |
| GET, POST | `/api/v1/workforce/employees/` | Bearer access token | List or create employees |
| GET, PUT, PATCH, DELETE | `/api/v1/workforce/employees/<pk>/` | Bearer access token | Read/update/delete employee |
| GET, POST, PUT, PATCH, DELETE | `/api/v1/workforce/employees/<employee_id>/profile/` | Bearer access token | Read/create/update/delete employee AI profile |
| GET, POST | `/api/v1/workforce/skills/` | Bearer access token | List or create company skills |
| GET, PUT, PATCH, DELETE | `/api/v1/workforce/skills/<pk>/` | Bearer access token | Read/update/delete skill |
| GET, POST | `/api/v1/workforce/employee-skills/` | Bearer access token | List or create employee-skill assignment |
| GET, PUT, PATCH, DELETE | `/api/v1/workforce/employee-skills/<pk>/` | Bearer access token | Read/update/delete assignment |

### Documents, integrations, and agents

| Method | Endpoint | Authentication | Purpose |
| --- | --- | --- | --- |
| GET, POST | `/api/v1/documents/` | Bearer access token | List or create document metadata |
| GET, PUT, PATCH, DELETE | `/api/v1/documents/<pk>/` | Bearer access token | Read/update/delete document metadata |
| GET, POST | `/api/v1/integrations/` | Bearer access token | List or create connection metadata |
| GET, PUT, PATCH, DELETE | `/api/v1/integrations/<pk>/` | Bearer access token | Read/update/delete connection metadata |
| GET, POST | `/api/v1/agents/` | Bearer access token | List or create agent metadata |
| GET, PUT, PATCH, DELETE | `/api/v1/agents/<pk>/` | Bearer access token | Read/update/delete agent metadata |

### Projects

| Method | Endpoint | Authentication | Purpose |
| --- | --- | --- | --- |
| GET, POST | `/api/v1/projects/` | Bearer access token | List or create projects |
| GET, PUT, PATCH, DELETE | `/api/v1/projects/<pk>/` | Bearer access token | Read/update/delete project |
| GET, POST | `/api/v1/projects/<project_id>/requirements/` | Bearer access token | List or create requirements |
| GET, PUT, PATCH, DELETE | `/api/v1/projects/<project_id>/requirements/<pk>/` | Bearer access token | Read/update/delete nested requirement |
| GET, POST | `/api/v1/projects/<project_id>/members/` | Bearer access token | List or assign project members |
| GET, PUT, PATCH, DELETE | `/api/v1/projects/<project_id>/members/<pk>/` | Bearer access token | Read/update/delete project-member assignment |

### Recommendations

| Method | Endpoint | Authentication | Purpose |
| --- | --- | --- | --- |
| GET, POST | `/api/v1/recommendations/` | Bearer access token | List or store recommendation records |
| GET, PUT, PATCH, DELETE | `/api/v1/recommendations/<pk>/` | Bearer access token | Read/update/delete recommendation record |
| GET | `/api/v1/recommendations/projects/<project_id>/` | Bearer access token | List records for one accessible project |

## Authentication and JWT

Authentication is Django's configured user model and Simple JWT. Access
tokens last 15 minutes; refresh tokens last 7 days. Refresh rotation and
blacklisting of rotated refresh tokens are enabled. Registration creates a
user only: it does not issue tokens or create a company.

### Register

`POST /api/v1/accounts/register/` is public and returns HTTP 201 with the
safe profile (not tokens).

| Field | Data type | Required? | Default | Validation | Example |
| --- | --- | --- | --- | --- | --- |
| `username` | string | Yes | None | Django username field; unique; maximum 150 characters | `"morgan"` |
| `email` | string/email | Yes | None | Valid email syntax; email is not declared unique by the user model | `"morgan@example.test"` |
| `first_name` | string | No | `""` | Django user field; maximum 150 characters | `"Morgan"` |
| `last_name` | string | No | `""` | Django user field; maximum 150 characters | `"Lee"` |
| `password` | string | Yes | None | Django configured password validators; write-only and hashed on save | `"Use-a-unique-demo-password-937!"` |
| `password_confirmation` | string | Yes | None | Must exactly match `password`; write-only | `"Use-a-unique-demo-password-937!"` |

Example:

```http
POST {{base_url}}/api/v1/accounts/register/
Content-Type: application/json
```

```json
{
  "username": "morgan",
  "email": "morgan@example.test",
  "first_name": "Morgan",
  "last_name": "Lee",
  "password": "Use-a-unique-demo-password-937!",
  "password_confirmation": "Use-a-unique-demo-password-937!"
}
```

Response `201 Created`:

```json
{
  "id": 42,
  "username": "morgan",
  "email": "morgan@example.test",
  "first_name": "Morgan",
  "last_name": "Lee",
  "date_joined": "2026-10-19T14:00:00Z"
}
```

The response never includes either password field or a password hash.
Validation errors return 400 with field keys; duplicate username is rejected.

### Login

`POST /api/v1/accounts/login/` is public. It uses Simple JWT's token-obtain
serializer, accepts username/password and returns HTTP 200. Inactive users
and invalid credentials are rejected with HTTP 401.

| Field | Data type | Required? | Default | Validation | Example |
| --- | --- | --- | --- | --- | --- |
| `username` | string | Yes | None | Must identify an active account | `"morgan"` |
| `password` | string | Yes | None | Must match stored Django password hash | `"Use-a-unique-demo-password-937!"` |

Request:

```json
{"username": "morgan", "password": "Use-a-unique-demo-password-937!"}
```

Response `200 OK` (token values shown as placeholders, never reuse these):

```json
{"refresh": "<refresh-jwt>", "access": "<access-jwt>"}
```

### Refresh token

`POST /api/v1/accounts/token/refresh/` is public to the JWT authentication
class and requires a valid refresh token in the JSON body. It returns 200 and,
with rotation enabled, a new access token and a new refresh token; the prior
refresh token is blacklisted.

| Field | Data type | Required? | Default | Validation | Example |
| --- | --- | --- | --- | --- | --- |
| `refresh` | string/JWT | Yes | None | Valid, unexpired, not-blacklisted refresh token | `"{{refresh_token}}"` |

Request: `{"refresh": "{{refresh_token}}"}`.

Response `200 OK`:

```json
{"access": "<new-access-jwt>", "refresh": "<new-refresh-jwt>"}
```

The frontend must replace both stored token values after refresh. Reuse of
the rotated token, expiration, or an invalid token returns 401.

### Logout

`POST /api/v1/accounts/logout/` submits the refresh token for blacklisting.
It is a public Simple JWT blacklist endpoint (no bearer token required) and
returns HTTP 200 on success. The body is `{"refresh":"{{refresh_token}}"}`.
The successful response is an empty JSON object (`{}`). A bad/expired token
is rejected by Simple JWT.

### Current profile

`GET /api/v1/accounts/me/` requires a bearer access token and returns 200:

```json
{
  "id": 42,
  "username": "morgan",
  "email": "morgan@example.test",
  "first_name": "Morgan",
  "last_name": "Lee",
  "date_joined": "2026-10-19T14:00:00Z"
}
```

All six fields are read-only. The endpoint returns the authenticated user
only; it never returns the password or password hash. Missing, invalid,
expired, or inactive-user authentication returns 401.

## Company membership and permissions

Company creation is separate from account registration. A successful
`POST /api/v1/companies/` creates the company and an `owner` membership for
the authenticated creator in one transaction. The creator may create only
one company. There is no invitation, join, or membership-role-management
endpoint in the registered API; a frontend must not imply that users can
self-join another company.

`GET /api/v1/companies/` lists companies whose membership belongs to the
authenticated user. Its `id` is the company ID supplied to company-scoped
workforce, document, integration, and agent create requests. Project
creation also requires a company ID. Existing resources are filtered through
membership querysets; browser-supplied IDs do not authorize access.

| App area | Read access | Write access |
| --- | --- | --- |
| Companies | Any member of the company | Company owner only for company-detail `PATCH`; company create is the authenticated new creator |
| Workforce | Company members | Owners, admins, managers |
| Documents | Company members | Owners, admins, managers |
| Integrations | Company members | Owners, admins, managers |
| Agents | Company members | Owners, admins, managers |
| Projects and nested requirements/members | Company members | Owners, admins, managers |
| Recommendations | Company members through their project | Owners, admins, managers |

The company detail and member querysets, and all business resource querysets,
are membership-scoped. For these detail endpoints, a record outside the
requester's memberships is generally hidden with 404. A member who can read
the company but lacks a writer role receives 403 for a write. Invalid or
unauthorized foreign-key IDs in serializers generally return 400. The
companies owner-only patch checks membership role and returns 403 to a
non-owner who can access that company.

## Companies API

The company serializer returns:

```json
{
  "id": 7,
  "created_by_user": 42,
  "name": "Northwind Studio",
  "industry": "Software",
  "description": "Product engineering team",
  "email": "contact@example.test",
  "phone": "+1-555-0100",
  "address": "100 Demo Avenue",
  "created_at": "2026-10-19T14:10:00Z"
}
```

### `GET` and `POST /api/v1/companies/`

Both require authentication. `GET` returns a plain array of the company
objects above for the user's memberships (200). It has no query parameters.
`POST` returns 201 and accepts:

| Field | Data type | Required? | Default | Validation | Example |
| --- | --- | --- | --- | --- | --- |
| `name` | string | Yes on create | None | Maximum 255 characters | `"Northwind Studio"` |
| `industry` | string or null | No | null | Maximum 150 characters | `"Software"` |
| `description` | string or null | No | null | Text | `"Product engineering team"` |
| `email` | string/email or null | No | null | Email syntax, maximum 255 characters | `"contact@example.test"` |
| `phone` | string or null | No | null | Maximum 50 characters | `"+1-555-0100"` |
| `address` | string or null | No | null | Text | `"100 Demo Avenue"` |

Do not send `id`, `created_by_user`, `created_at`, user, or role. The user and
owner membership are assigned by the backend.

POST body:

```json
{
  "name": "Northwind Studio",
  "industry": "Software",
  "description": "Product engineering team",
  "email": "contact@example.test",
  "phone": "+1-555-0100",
  "address": "100 Demo Avenue"
}
```

The returned object has the company response shape above. Missing `name` or
invalid email returns 400. A second company by the same creator returns
409 with `{"detail":"This user already created a company."}`. If transactional
creation conflicts, 409 reports a safe conflict detail.

### `GET` and `PATCH /api/v1/companies/<pk>/`

`<pk>` is an integer company ID. GET returns the same company object (200).
PATCH is the only update method registered and is owner-only; it accepts any
subset of the create detail fields above. Omitted fields remain unchanged;
nullable fields can be explicitly set to null. PATCH returns the updated
company object (200). A member with a non-owner role receives 403; a
nonmember receives 404. PUT and DELETE are not implemented (405).

Example:

```http
PATCH {{base_url}}/api/v1/companies/{{company_id}}/
Authorization: Bearer {{access_token}}
Content-Type: application/json
```

```json
{"description": "Updated team description"}
```

Response: the company object shown above with the changed description.

### `GET /api/v1/companies/<pk>/members/`

Requires membership in the path company. Returns a plain JSON array (200):

```json
[
  {
    "id": 13,
    "user": {
      "id": 42,
      "username": "morgan",
      "email": "morgan@example.test",
      "first_name": "Morgan",
      "last_name": "Lee"
    },
    "role": "owner",
    "created_at": "2026-10-19T14:10:00Z"
  }
]
```

The `user` is safe profile data; it contains no password. All fields are
read-only. Nonmembers receive 404. No role update or invite method is
implemented.

## Workforce API

All workforce routes require authentication. Members can read their
companies' resources; owners, admins, and managers can write. The serializer
restricts supplied company, department, employee, and skill IDs to writable
companies. Employee rows reference a department, and the department supplies
the company. A skill references a company directly. Employee-skill
assignments are accepted only if employee department and skill share a
company. An employee AI profile belongs to the employee in the URL; the
profile response does not include an employee field.

### Departments: `/api/v1/workforce/departments/` and `/<pk>/`

GET collection returns a plain array. POST returns 201. Detail GET/PUT/PATCH
returns 200; DELETE returns 204. Detail IDs outside the user's memberships
return 404. Members are read-only (403 for writes).

| Field | Data type | Required? | Default | Validation | Example |
| --- | --- | --- | --- | --- | --- |
| `company` | integer ID | Yes on create | None | Existing company where requester is owner/admin/manager | `7` |
| `name` | string | Yes on create/PUT | None | Maximum 150 characters | `"Engineering"` |
| `description` | string or null | No | null | Text | `"Platform team"` |
| `id` | integer | Response only | Database-generated | Read-only | `31` |
| `created_at` | datetime | Response only | Current time | Read-only | `"2026-10-19T14:00:00Z"` |

Example POST body: `{"company":7,"name":"Engineering","description":"Platform team"}`.
Response:

```json
{
  "id": 31,
  "company": 7,
  "name": "Engineering",
  "description": "Platform team",
  "created_at": "2026-10-19T14:00:00Z"
}
```

For detail PUT, provide the required `company` and `name`; PATCH can contain
only fields to change. On an update the `company` is still validated against
the caller's writable companies. Supplying an inaccessible company ID returns
400; inaccessible detail ID returns 404.

### Employees: `/api/v1/workforce/employees/` and `/<pk>/`

GET collection returns a plain array. POST returns 201. Detail GET/PUT/PATCH
returns 200; DELETE returns 204. Employee is scoped by
`department.company`.

| Field | Data type | Required? | Default | Validation | Example |
| --- | --- | --- | --- | --- | --- |
| `department` | integer ID | Yes on create/PUT | None | Existing department in a writable company | `31` |
| `employee_code` | string | Yes on create/PUT | None | Maximum 50; unique within department | `"ENG-004"` |
| `first_name` | string | Yes on create/PUT | None | Maximum 100 | `"Morgan"` |
| `last_name` | string | Yes on create/PUT | None | Maximum 100 | `"Lee"` |
| `email` | string/email or null | No | null | Email validation, maximum 255 | `"morgan@example.test"` |
| `phone` | string or null | No | null | Maximum 50 | `"+1-555-0144"` |
| `address` | string or null | No | null | Text | `"100 Demo Avenue"` |
| `date_of_birth` | date string or null | No | null | `YYYY-MM-DD` | `"1994-04-12"` |
| `id`, `created_at` | integer, datetime | Response only | Generated | Read-only | `58`, `"2026-10-19T14:00:00Z"` |

POST body:

```json
{
  "department": 31,
  "employee_code": "ENG-004",
  "first_name": "Morgan",
  "last_name": "Lee",
  "email": "morgan@example.test",
  "phone": "+1-555-0144",
  "address": "100 Demo Avenue",
  "date_of_birth": "1994-04-12"
}
```

Response uses those values plus generated `id` and `created_at`. A duplicate
`(department, employee_code)` returns 400. PATCH omitted fields are unchanged.
Changing a department to another writable company is rejected with 400 if
existing employee-skill links would become cross-company.

### Employee AI profile: `/api/v1/workforce/employees/<employee_id>/profile/`

`employee_id` is an existing employee ID in a member company. GET returns
200; POST creates and returns 201; PUT/PATCH updates and returns 200; DELETE
returns 204. GET/update/delete when no profile exists returns 404. A second
POST returns 409. Members may read but not modify; writes require a writer
role in that employee's company.

| Field | Data type | Required? | Default | Validation | Example |
| --- | --- | --- | --- | --- | --- |
| `job_title` | string or null | No | null | Maximum 150 | `"Senior engineer"` |
| `education` | string or null | No | null | Maximum 255 | `"BSc Computer Science"` |
| `experience_years` | decimal string/number | No | `0.00` | At most 5 digits, 2 decimal places | `"6.50"` |
| `performance_score` | decimal string/number or null | No | null | At most 5 digits, 2 decimal places | `"92.50"` |
| `availability_status` | string | No | `"available"` | `available`, `partially_available`, `unavailable` | `"available"` |
| `current_workload` | decimal string/number | No | `0.00` | At most 5 digits, 2 decimal places | `"20.00"` |
| `previous_project_score` | decimal string/number or null | No | null | At most 5 digits, 2 decimal places | `null` |
| `completed_projects` | integer | No | `0` | Integer | `4` |
| `employment_status` | string | No | `"active"` | `active`, `inactive`, `on_leave` | `"active"` |
| `id`, `updated_at` | integer, datetime | Response only | Generated/current time | Read-only | `10`, `"2026-10-19T14:00:00Z"` |

The URL supplies the employee; do not send `employee`. Example POST:

```json
{
  "job_title": "Senior engineer",
  "education": "BSc Computer Science",
  "experience_years": "6.50",
  "performance_score": "92.50",
  "availability_status": "available",
  "current_workload": "20.00",
  "previous_project_score": null,
  "completed_projects": 4,
  "employment_status": "active"
}
```

Response:

```json
{
  "id": 10,
  "job_title": "Senior engineer",
  "education": "BSc Computer Science",
  "experience_years": "6.50",
  "performance_score": "92.50",
  "availability_status": "available",
  "current_workload": "20.00",
  "previous_project_score": null,
  "completed_projects": 4,
  "employment_status": "active",
  "updated_at": "2026-10-19T14:00:00Z"
}
```

Omitted values on create use defaults/null; on PATCH omitted values stay
unchanged. PUT is non-partial; fields with model defaults/nullable settings
are not all required by the serializer.

### Skills: `/api/v1/workforce/skills/` and `/<pk>/`

GET collection returns a plain array. POST returns 201. Detail GET/PUT/PATCH
returns 200; DELETE returns 204.

| Field | Data type | Required? | Default | Validation | Example |
| --- | --- | --- | --- | --- | --- |
| `company` | integer ID | Yes on create/PUT | None | Existing writable company | `7` |
| `name` | string | Yes on create/PUT | None | Maximum 150; unique per company | `"Python"` |
| `category` | string or null | No | null | Maximum 100 | `"Backend"` |
| `description` | string or null | No | null | Text | `"Python application development"` |
| `id`, `created_at` | integer, datetime | Response only | Generated | Read-only | `72`, `"2026-10-19T14:00:00Z"` |

POST body: `{"company":7,"name":"Python","category":"Backend","description":"Python application development"}`.
Response has those values plus generated `id` and `created_at`. Duplicate
company/name returns 400. Moving a skill to another company is rejected if
it would invalidate employee-skill assignments.

### Employee skills: `/api/v1/workforce/employee-skills/` and `/<pk>/`

GET returns a plain array of assignment objects; POST returns 201; detail GET,
PUT, PATCH return 200; DELETE returns 204.

| Field | Data type | Required? | Default | Validation | Example |
| --- | --- | --- | --- | --- | --- |
| `employee` | integer ID | Yes | None | Employee in a writable company | `58` |
| `skill` | integer ID | Yes | None | Skill in a writable company and same company as employee | `72` |
| `proficiency` | decimal string/number or null | No | null | At most 5 digits, 2 decimal places | `"88.50"` |
| `years_experience` | decimal string/number | No | `0.00` | At most 5 digits, 2 decimal places | `"3.25"` |
| `id` | integer | Response only | Generated | Read-only | `5` |

POST example: `{"employee":58,"skill":72,"proficiency":"88.50","years_experience":"3.25"}`.
The response returns the same field set with `id`. Employee and skill IDs must
belong to the same company. Duplicate `(employee, skill)` returns 400.

## Documents API

Documents represent metadata and a nullable text `file_path`; the API does
not accept binary file uploads or store a file. Company members can read;
owners, admins, and managers can write. Company is a writable company ID on
create/update.

### `GET`, `POST /api/v1/documents/`

GET returns a plain array (200); POST returns one document (201).

| Field | Data type | Required? | Default | Validation | Example |
| --- | --- | --- | --- | --- | --- |
| `company` | integer ID | Yes on create | None | Existing writable company | `7` |
| `title` | string | Yes on create/PUT | None | Maximum 255 characters | `"Employee handbook"` |
| `document_type` | string or null | No | null | Maximum 100 characters | `"policy"` |
| `description` | string or null | No | null | Text | `"Current handbook metadata"` |
| `file_path` | string or null | No | null | Text metadata only; no upload semantics | `"private/handbook.pdf"` |
| `id`, `uploaded_at` | integer, datetime | Response only | Generated/current time | Read-only | `12`, `"2026-10-19T14:00:00Z"` |

Example body:

```json
{
  "company": 7,
  "title": "Employee handbook",
  "document_type": "policy",
  "description": "Current handbook metadata",
  "file_path": "private/handbook.pdf"
}
```

Example response:

```json
{
  "id": 12,
  "company": 7,
  "title": "Employee handbook",
  "document_type": "policy",
  "description": "Current handbook metadata",
  "file_path": "private/handbook.pdf",
  "uploaded_at": "2026-10-19T14:00:00Z"
}
```

Missing title or invalid/inaccessible company ID returns 400.

### `GET`, `PUT`, `PATCH`, `DELETE /api/v1/documents/<pk>/`

`pk` is a document ID. GET returns the document object (200); PUT/PATCH use
the writable fields in the table above and return the updated object (200);
DELETE returns 204 with no body. PATCH may omit unchanged fields. An
inaccessible ID returns 404; a read-only company member receives 403 for
write operations. This endpoint can update `company` only to a writable
company.

Example PATCH body: `{"title":"Employee handbook v2"}`.

## Integrations API

This app stores connection metadata only. It neither authenticates against
third-party services nor verifies that a status value means a real connection.
It exposes no credential or token fields. Company members can read; owners,
admins, and managers can write.

### `GET`, `POST /api/v1/integrations/`

GET returns a plain array (200); POST returns 201.

| Field | Data type | Required? | Default | Validation | Example |
| --- | --- | --- | --- | --- | --- |
| `company` | integer ID | Yes on create | None | Existing writable company | `7` |
| `provider` | string | Yes on create | None | Maximum 100 characters | `"GitHub"` |
| `connection_type` | string or null | No | null | Maximum 100 characters | `"repository"` |
| `account_name` | string or null | No | null | Maximum 255 characters | `"Agentix"` |
| `status` | string | No | `"disconnected"` | Maximum 50; not an enumerated state machine | `"disconnected"` |
| `connected_at` | ISO datetime or null | No | null | Nullable timestamp; does not prove connectivity | `null` |
| `id` | integer | Response only | Generated | Read-only | `3` |

Example POST body: `{"company":7,"provider":"GitHub","connection_type":"repository","account_name":"Agentix"}`.
Example response:

```json
{
  "id": 3,
  "company": 7,
  "provider": "GitHub",
  "connection_type": "repository",
  "account_name": "Agentix",
  "status": "disconnected",
  "connected_at": null
}
```

Provider is required; omitted optional fields use the defaults/nulls above.

### `GET`, `PUT`, `PATCH`, `DELETE /api/v1/integrations/<pk>/`

GET returns the connection object (200); PUT/PATCH accept the writable
metadata fields above and return the updated object (200); DELETE returns 204
with an empty body. Inaccessible IDs return 404, and members without a
writer role get 403 for writes. Unauthorized company IDs on a write return
400. Example PATCH body:
`{"status":"connected","connected_at":"2026-10-19T14:30:00Z"}`. This changes
metadata only; it does not establish or verify a provider connection.

## Agents API

The AI agent resource is metadata only. It does not execute tasks, call
tools, or run workflows. Company members can read; owners, admins, and
managers can write.

### `GET`, `POST /api/v1/agents/`

GET returns a plain array (200); POST returns 201.

| Field | Data type | Required? | Default | Validation | Example |
| --- | --- | --- | --- | --- | --- |
| `company` | integer ID | Yes on create | None | Existing writable company | `7` |
| `name` | string | Yes on create/PUT | None | Maximum 150 characters | `"Planning assistant"` |
| `agent_type` | string or null | No | null | Maximum 100 characters | `"planner"` |
| `description` | string or null | No | null | Text | `"Metadata record"` |
| `capabilities` | string or null | No | null | Text metadata only | `"Summarization"` |
| `status` | string | No | `"active"` | Maximum 50; not an enum | `"active"` |
| `id`, `created_at` | integer, datetime | Response only | Generated/current time | Read-only | `18`, `"2026-10-19T14:00:00Z"` |

POST body:

```json
{
  "company": 7,
  "name": "Planning assistant",
  "agent_type": "planner",
  "description": "Metadata record",
  "capabilities": "Summarization",
  "status": "active"
}
```

Response:

```json
{
  "id": 18,
  "company": 7,
  "name": "Planning assistant",
  "agent_type": "planner",
  "description": "Metadata record",
  "capabilities": "Summarization",
  "status": "active",
  "created_at": "2026-10-19T14:00:00Z"
}
```

### `GET`, `PUT`, `PATCH`, `DELETE /api/v1/agents/<pk>/`

GET returns the agent object (200); PUT/PATCH accept the writable fields
above and return the updated object (200); DELETE returns 204. Inaccessible
IDs return 404; a read-only member gets 403 on write. Example PATCH body:
`{"name":"Planning assistant v2","status":"paused"}`.

## Projects API

All project endpoints require authentication. Company members can read;
owners, admins, and managers can write. Requirements and members use the
project ID from their parent path; `project` is read-only in their
serializers. A project-member assignment must have exactly one employee or
agent. Both the serializer and database check constraint enforce this.
Candidate company must match the project company.

### Projects: `/api/v1/projects/` and `/<pk>/`

Collection GET returns an array (200); POST returns 201. Detail GET/PUT/PATCH
returns an object (200); DELETE returns 204. Company is validated against the
requester's writable memberships. Moving a project with an existing
cross-company member assignment is rejected.

| Field | Data type | Required? | Default | Validation | Example |
| --- | --- | --- | --- | --- | --- |
| `company` | integer ID | Yes on create/PUT | None | Existing writable company | `7` |
| `name` | string | Yes on create/PUT | None | Maximum 255 characters | `"Website refresh"` |
| `description` | string or null | No | null | Text | `"Customer portal"` |
| `status` | string | No | `"draft"` | Maximum 50; not an enum | `"draft"` |
| `priority` | string | No | `"medium"` | Maximum 50; not an enum | `"high"` |
| `start_date` | date string or null | No | null | `YYYY-MM-DD` | `"2026-10-20"` |
| `deadline` | date string or null | No | null | `YYYY-MM-DD` | `"2027-01-31"` |
| `id`, `created_at` | integer, datetime | Response only | Generated/current time | Read-only | `22`, `"2026-10-19T14:00:00Z"` |

POST body: `{"company":7,"name":"Website refresh","description":"Customer portal","priority":"high","start_date":"2026-10-20","deadline":"2027-01-31"}`.
Response adds `id`, defaults `status` to `draft`, and includes timestamp:

```json
{
  "id": 22,
  "company": 7,
  "name": "Website refresh",
  "description": "Customer portal",
  "status": "draft",
  "priority": "high",
  "start_date": "2026-10-20",
  "deadline": "2027-01-31",
  "created_at": "2026-10-19T14:00:00Z"
}
```

For PATCH, only the provided fields change. PUT is non-partial and requires
company/name. Detail inaccessible to a nonmember is 404.

### Requirements: `/api/v1/projects/<project_id>/requirements/` and `/<pk>/`

The collection GET returns an array (200); POST returns 201. Nested detail
GET/PUT/PATCH returns one object (200); DELETE returns 204. The path project
must be accessible to the user. The request cannot choose or change `project`.

| Field | Data type | Required? | Default | Validation | Example |
| --- | --- | --- | --- | --- | --- |
| `requirement` | string | Yes on create/PUT | None | Text | `"Support single sign-on"` |
| `required_skills` | string or null | No | null | Text | `"Python, OAuth"` |
| `required_roles` | string or null | No | null | Text | `"Backend engineer"` |
| `priority` | string | No | `"medium"` | Maximum 50; not an enum | `"high"` |
| `deadline` | date string or null | No | null | `YYYY-MM-DD` | `"2026-12-15"` |
| `id`, `project`, `created_at` | integer, integer, datetime | Response only | Generated | Read-only / URL-supplied project | `4`, `22`, `"2026-10-19T14:00:00Z"` |

POST body: `{"requirement":"Support single sign-on","required_skills":"Python, OAuth","required_roles":"Backend engineer","priority":"high","deadline":"2026-12-15"}`.
Response:

```json
{
  "id": 4,
  "project": 22,
  "requirement": "Support single sign-on",
  "required_skills": "Python, OAuth",
  "required_roles": "Backend engineer",
  "priority": "high",
  "deadline": "2026-12-15",
  "created_at": "2026-10-19T14:00:00Z"
}
```

PATCH changes supplied fields; PUT requires `requirement`. If `project` is
included in a body it is read-only and the nested URL remains authoritative.

### Project members: `/api/v1/projects/<project_id>/members/` and `/<pk>/`

Collection GET returns an array (200); POST returns 201. Detail GET/PUT/PATCH
returns an object (200); DELETE returns 204. Accessible project path required.

| Field | Data type | Required? | Default | Validation | Example |
| --- | --- | --- | --- | --- | --- |
| `employee` | integer ID or null | Conditionally required | null | Must be in project company | `58` |
| `ai_agent` | integer ID or null | Conditionally required | null | Must be in project company | `18` |
| `role` | string or null | No | null | Maximum 150 characters | `"Developer"` |
| `member_type` | string | Yes on create/PUT | None | Maximum 50; no enum choices imposed | `"employee"` |
| `status` | string | No | `"active"` | Maximum 50; no enum choices imposed | `"active"` |
| `id`, `project`, `assigned_at` | integer, integer, datetime | Response only | Generated/URL supplied | Read-only | `9`, `22`, `"2026-10-19T14:00:00Z"` |

Exactly one of `employee` and `ai_agent` must resolve to a non-null ID.
Create example for an employee:

```json
{
  "employee": 58,
  "ai_agent": null,
  "role": "Developer",
  "member_type": "employee",
  "status": "active"
}
```

Response:

```json
{
  "id": 9,
  "project": 22,
  "employee": 58,
  "ai_agent": null,
  "role": "Developer",
  "member_type": "employee",
  "status": "active",
  "assigned_at": "2026-10-19T14:00:00Z"
}
```

For an agent assignment, use `employee: null` and a valid `ai_agent` ID.
Neither/both targets returns 400. PATCH retains omitted target values; to
switch an assignment, explicitly null the old target and provide the new
target in the same request. The database constraint protects direct database
writes too.

## Recommendations API

This app stores records; it does not generate recommendations or compute
scores. Recommendations are scoped through their project's company. Members
can read; owners, admins, and managers can create/update/delete.

### `GET`, `POST /api/v1/recommendations/`

GET returns a plain array (200). POST returns 201.

| Field | Data type | Required? | Default | Validation | Example |
| --- | --- | --- | --- | --- | --- |
| `project` | integer ID | Yes | None | Existing project in a writable company | `22` |
| `employee` | integer ID or null | Conditionally required | null | Same company as project | `58` |
| `ai_agent` | integer ID or null | Conditionally required | null | Same company as project | `18` |
| `recommended_role` | string or null | No | null | Maximum 150 characters | `"Backend engineer"` |
| `score` | decimal string/number | Yes | None | Maximum 8 total digits, 5 decimal places | `"0.92345"` |
| `rank` | integer | Yes | None | Integer | `1` |
| `reason` | string or null | No | null | Text | `"Relevant experience"` |
| `status` | string | No | `"pending"` | Maximum 50; not an enum | `"pending"` |
| `id`, `created_at` | integer, datetime | Response only | Generated/current time | Read-only | `11`, `"2026-10-19T14:00:00Z"` |

Exactly one candidate target must be non-null. Body example:

```json
{
  "project": 22,
  "employee": 58,
  "ai_agent": null,
  "recommended_role": "Backend engineer",
  "score": "0.92345",
  "rank": 1,
  "reason": "Relevant experience",
  "status": "pending"
}
```

Response:

```json
{
  "id": 11,
  "project": 22,
  "employee": 58,
  "ai_agent": null,
  "recommended_role": "Backend engineer",
  "score": "0.92345",
  "rank": 1,
  "reason": "Relevant experience",
  "status": "pending",
  "created_at": "2026-10-19T14:00:00Z"
}
```

### `GET`, `PUT`, `PATCH`, `DELETE /api/v1/recommendations/<pk>/`

GET returns one recommendation object (200); PUT/PATCH accept the writable
fields above and return the updated object (200); DELETE returns 204. A
nonmember sees 404; a read-only member gets 403 on writes. PUT requires
project, score, rank, and exactly one candidate. PATCH omitted fields remain
unchanged. When PATCH supplies a non-null employee without `ai_agent`, or a
non-null AI agent without `employee`, the serializer clears the opposing
target. Supplying both non-null targets or leaving neither target returns
400. Project, employee, and agent IDs must be writable/valid for the caller
and company-consistent.

### `GET /api/v1/recommendations/projects/<project_id>/`

The path project ID is required and must belong to a company the caller
belongs to. It returns a plain array of the recommendation response shape
above (200). The endpoint is read-only, accepts no body, and returns 404 for
an inaccessible/nonexistent project.

## Errors and validation

There is no project-wide custom exception handler. DRF serializers normally
return a field-keyed 400 response; exact messages vary by validator and
submitted value. For example:

```json
{
  "name": ["This field is required."],
  "company": ["Invalid pk \"999999\" - object does not exist."]
}
```

Some object-level validation uses a non-field error:

```json
{"non_field_errors":["Exactly one of employee or ai_agent must be provided."]}
```

Common status behavior observed in the app implementations and tests:

| Status | Meaning |
| --- | --- |
| 201 | Created (registration/resource create) |
| 200 | Successful read/update, login, token refresh, logout |
| 204 | Successful delete; empty response body |
| 400 | Serializer validation, missing/invalid fields, invalid or unauthorized related ID |
| 401 | Missing/invalid/expired bearer authentication; invalid credentials; invalid/expired token |
| 403 | Authenticated user can address the company/object but lacks its required write role |
| 404 | Object or parent project outside the user's visible company scope, or not found |
| 409 | Duplicate company creation, conflicting company create, or duplicate employee AI profile |
| 405 | HTTP method is not implemented for that URL |

Typical examples:

```json
{"detail":"Authentication credentials were not provided."}
```

```json
{"detail":"Only the company owner may update company details."}
```

```json
{"detail":"This employee already has an AI profile."}
```

An invalid JWT may include a `detail`, `code`, and `messages` structure from
Simple JWT. Do not depend on a single exact string for all authentication
failures. When receiving 401 on a protected request, try one refresh using a
valid refresh token; replace both tokens when rotation returns a new pair.
If refresh fails, clear the frontend's authentication state and require login.
Do not retry 403 or 404 by changing IDs; show an access/not-found state.

Database constraints exist for the approved unique constraints and
exactly-one candidate checks. The tests verify duplicate workforce API
submissions are rejected as 400; direct database writes that violate a
constraint raise a database integrity error rather than returning an API
response. Projects and recommendations reject exclusive-target violations
through serializers and database check constraints.

## Relationships and frontend data flow

One practical workflow, with IDs retained from preceding responses:

1. Register or log in. Registration returns a user profile but no token;
   login returns `access` and `refresh`.
2. Send the access token as `Authorization: Bearer ...`; call `/accounts/me/`
   to load the current profile.
3. Call `GET /companies/`. If no company exists, create one with
   `POST /companies/`. The response's `id` is `company_id`; the caller is
   automatically its owner. There is no join/invite endpoint.
4. Create departments with `company_id`; save each returned department `id`.
5. Create skills with `company_id`; save each skill `id`.
6. Create employees with a `department` ID. Create a profile at the nested
   profile path using the returned employee ID, if needed.
7. Create AI agent metadata with the same `company_id`.
8. Create projects with `company_id`; save the returned project ID.
9. Create requirements at the project-specific nested route; the parent
   project ID comes from its URL, not the JSON body.
10. Assign an employee or AI agent at the nested members route. Use an
    employee ID from employees or an agent ID from agents; the project
    serializer enforces same-company assignment and exactly one target.
11. List or manage recommendation records using the project, employee, and
    agent IDs. The endpoint stores records and does not generate them.
12. Create/list documents and connection metadata for the company. A
    document `file_path` is text only; connection status is metadata only.

The ID values are database-generated and are not predictable. Fetch/list
resources or retain IDs from create responses. An ID supplied by the browser
never replaces backend company-membership authorization.

## Postman setup and request examples

Set these optional Postman environment variables:

| Variable | Example value |
| --- | --- |
| `base_url` | `http://127.0.0.1:8000` |
| `access_token` | Set from login/refresh response |
| `refresh_token` | Set from login/refresh response |
| `company_id` | Set from company create/list response |
| `department_id` | Set from department response |
| `employee_id` | Set from employee response |
| `skill_id` | Set from skill response |
| `assignment_id` | Set from employee-skill response |
| `ai_agent_id` | Set from agent response |
| `document_id` | Set from document response |
| `connection_id` | Set from integration response |
| `project_id` | Set from project response |
| `requirement_id` | Set from project-requirement response |
| `member_id` | Set from project-member response |
| `recommendation_id` | Set from recommendation response |

For authenticated calls, use the Postman Bearer Token authorization type with
`{{access_token}}`. Use `Content-Type: application/json` for JSON bodies.
The endpoint index plus each app's field and response examples above are the
request/response reference for every route. Method-specific request examples:

| API path | Method | Example body / behavior | Success |
| --- | --- | --- | --- |
| `/api/v1/accounts/register/` | POST | Registration JSON above | 201 profile |
| `/api/v1/accounts/login/` | POST | `{"username":"morgan","password":"Use-a-unique-demo-password-937!"}` | 200 token pair |
| `/api/v1/accounts/token/refresh/` | POST | `{"refresh":"{{refresh_token}}"}` | 200 rotated token pair |
| `/api/v1/accounts/logout/` | POST | `{"refresh":"{{refresh_token}}"}` | 200 `{}` |
| `/api/v1/accounts/me/` | GET | No body | 200 profile |
| `/api/v1/companies/` | GET | No body | 200 company array |
| `/api/v1/companies/` | POST | Company JSON above | 201 company |
| `/api/v1/companies/{{company_id}}/` | GET | No body | 200 company |
| `/api/v1/companies/{{company_id}}/` | PATCH | `{"description":"Updated team description"}` | 200 company |
| `/api/v1/companies/{{company_id}}/members/` | GET | No body | 200 membership array |
| `/api/v1/workforce/departments/` | GET | No body | 200 array |
| `/api/v1/workforce/departments/` | POST | `{"company":{{company_id}},"name":"Engineering"}` | 201 department |
| `/api/v1/workforce/departments/{{department_id}}/` | GET | No body | 200 department |
| `/api/v1/workforce/departments/{{department_id}}/` | PUT | `{"company":{{company_id}},"name":"Engineering","description":"Platform team"}` | 200 department |
| `/api/v1/workforce/departments/{{department_id}}/` | PATCH | `{"description":"Platform team"}` | 200 department |
| `/api/v1/workforce/departments/{{department_id}}/` | DELETE | No body | 204 empty |
| `/api/v1/workforce/employees/` | GET | No body | 200 array |
| `/api/v1/workforce/employees/` | POST | Employee JSON above | 201 employee |
| `/api/v1/workforce/employees/{{employee_id}}/` | GET | No body | 200 employee |
| `/api/v1/workforce/employees/{{employee_id}}/` | PUT | `{"department":{{department_id}},"employee_code":"ENG-004","first_name":"Morgan","last_name":"Lee","email":"morgan@example.test","phone":"+1-555-0144","address":"100 Demo Avenue","date_of_birth":"1994-04-12"}` | 200 employee |
| `/api/v1/workforce/employees/{{employee_id}}/` | PATCH | `{"phone":"+1-555-0144"}` | 200 employee |
| `/api/v1/workforce/employees/{{employee_id}}/` | DELETE | No body | 204 empty |
| `/api/v1/workforce/employees/{{employee_id}}/profile/` | GET | No body | 200 profile (404 if absent) |
| `/api/v1/workforce/employees/{{employee_id}}/profile/` | POST | Profile JSON above | 201 profile |
| `/api/v1/workforce/employees/{{employee_id}}/profile/` | PUT | Use the complete profile JSON example above; employee comes from URL | 200 profile |
| `/api/v1/workforce/employees/{{employee_id}}/profile/` | PATCH | `{"availability_status":"partially_available"}` | 200 profile |
| `/api/v1/workforce/employees/{{employee_id}}/profile/` | DELETE | No body | 204 empty |
| `/api/v1/workforce/skills/` | GET | No body | 200 array |
| `/api/v1/workforce/skills/` | POST | `{"company":{{company_id}},"name":"Python","category":"Backend"}` | 201 skill |
| `/api/v1/workforce/skills/{{skill_id}}/` | GET | No body | 200 skill |
| `/api/v1/workforce/skills/{{skill_id}}/` | PUT | `{"company":{{company_id}},"name":"Python","category":"Backend","description":"Python application development"}` | 200 skill |
| `/api/v1/workforce/skills/{{skill_id}}/` | PATCH | `{"category":"Backend"}` | 200 skill |
| `/api/v1/workforce/skills/{{skill_id}}/` | DELETE | No body | 204 empty |
| `/api/v1/workforce/employee-skills/` | GET | No body | 200 array |
| `/api/v1/workforce/employee-skills/` | POST | `{"employee":{{employee_id}},"skill":{{skill_id}},"proficiency":"88.50"}` | 201 assignment |
| `/api/v1/workforce/employee-skills/{{assignment_id}}/` | GET | No body | 200 assignment |
| `/api/v1/workforce/employee-skills/{{assignment_id}}/` | PUT | `{"employee":{{employee_id}},"skill":{{skill_id}},"proficiency":"88.50","years_experience":"3.25"}` | 200 assignment |
| `/api/v1/workforce/employee-skills/{{assignment_id}}/` | PATCH | `{"proficiency":"90.00"}` | 200 assignment |
| `/api/v1/workforce/employee-skills/{{assignment_id}}/` | DELETE | No body | 204 empty |
| `/api/v1/documents/` | GET | No body | 200 array |
| `/api/v1/documents/` | POST | Document JSON above | 201 document |
| `/api/v1/documents/{{document_id}}/` | GET | No body | 200 document |
| `/api/v1/documents/{{document_id}}/` | PUT | `{"company":{{company_id}},"title":"Employee handbook","document_type":"policy","description":"Current handbook metadata","file_path":"private/handbook.pdf"}` | 200 document |
| `/api/v1/documents/{{document_id}}/` | PATCH | `{"title":"Employee handbook v2"}` | 200 document |
| `/api/v1/documents/{{document_id}}/` | DELETE | No body | 204 empty |
| `/api/v1/integrations/` | GET | No body | 200 array |
| `/api/v1/integrations/` | POST | `{"company":{{company_id}},"provider":"GitHub","account_name":"Agentix"}` | 201 connection |
| `/api/v1/integrations/{{connection_id}}/` | GET | No body | 200 connection |
| `/api/v1/integrations/{{connection_id}}/` | PUT | `{"company":{{company_id}},"provider":"GitHub","connection_type":"repository","account_name":"Agentix","status":"disconnected","connected_at":null}` | 200 connection |
| `/api/v1/integrations/{{connection_id}}/` | PATCH | `{"status":"connected"}` (metadata only) | 200 connection |
| `/api/v1/integrations/{{connection_id}}/` | DELETE | No body | 204 empty |
| `/api/v1/agents/` | GET | No body | 200 array |
| `/api/v1/agents/` | POST | Agent JSON above | 201 agent |
| `/api/v1/agents/{{ai_agent_id}}/` | GET | No body | 200 agent |
| `/api/v1/agents/{{ai_agent_id}}/` | PUT | `{"company":{{company_id}},"name":"Planning assistant","agent_type":"planner","description":"Metadata record","capabilities":"Summarization","status":"active"}` | 200 agent |
| `/api/v1/agents/{{ai_agent_id}}/` | PATCH | `{"status":"paused"}` | 200 agent |
| `/api/v1/agents/{{ai_agent_id}}/` | DELETE | No body | 204 empty |
| `/api/v1/projects/` | GET | No body | 200 array |
| `/api/v1/projects/` | POST | Project JSON above | 201 project |
| `/api/v1/projects/{{project_id}}/` | GET | No body | 200 project |
| `/api/v1/projects/{{project_id}}/` | PUT | `{"company":{{company_id}},"name":"Website refresh","description":"Customer portal","status":"draft","priority":"high","start_date":"2026-10-20","deadline":"2027-01-31"}` | 200 project |
| `/api/v1/projects/{{project_id}}/` | PATCH | `{"status":"active"}` | 200 project |
| `/api/v1/projects/{{project_id}}/` | DELETE | No body | 204 empty |
| `/api/v1/projects/{{project_id}}/requirements/` | GET | No body | 200 array |
| `/api/v1/projects/{{project_id}}/requirements/` | POST | `{"requirement":"Support SSO","priority":"high"}` | 201 requirement |
| `/api/v1/projects/{{project_id}}/requirements/{{requirement_id}}/` | GET | No body | 200 requirement |
| `/api/v1/projects/{{project_id}}/requirements/{{requirement_id}}/` | PUT | `{"requirement":"Support single sign-on","required_skills":"Python, OAuth","required_roles":"Backend engineer","priority":"high","deadline":"2026-12-15"}`; project from URL | 200 requirement |
| `/api/v1/projects/{{project_id}}/requirements/{{requirement_id}}/` | PATCH | `{"priority":"medium"}` | 200 requirement |
| `/api/v1/projects/{{project_id}}/requirements/{{requirement_id}}/` | DELETE | No body | 204 empty |
| `/api/v1/projects/{{project_id}}/members/` | GET | No body | 200 array |
| `/api/v1/projects/{{project_id}}/members/` | POST | `{"employee":{{employee_id}},"ai_agent":null,"member_type":"employee"}` | 201 member |
| `/api/v1/projects/{{project_id}}/members/{{member_id}}/` | GET | No body | 200 member |
| `/api/v1/projects/{{project_id}}/members/{{member_id}}/` | PUT | `{"employee":{{employee_id}},"ai_agent":null,"role":"Developer","member_type":"employee","status":"active"}`; project from URL | 200 member |
| `/api/v1/projects/{{project_id}}/members/{{member_id}}/` | PATCH | `{"status":"inactive"}` | 200 member |
| `/api/v1/projects/{{project_id}}/members/{{member_id}}/` | DELETE | No body | 204 empty |
| `/api/v1/recommendations/` | GET | No body | 200 array |
| `/api/v1/recommendations/` | POST | Recommendation JSON above | 201 recommendation |
| `/api/v1/recommendations/{{recommendation_id}}/` | GET | No body | 200 recommendation |
| `/api/v1/recommendations/{{recommendation_id}}/` | PUT | `{"project":{{project_id}},"employee":{{employee_id}},"ai_agent":null,"recommended_role":"Backend engineer","score":"0.92345","rank":1,"reason":"Relevant experience","status":"pending"}` | 200 recommendation |
| `/api/v1/recommendations/{{recommendation_id}}/` | PATCH | `{"status":"accepted"}` | 200 recommendation |
| `/api/v1/recommendations/{{recommendation_id}}/` | DELETE | No body | 204 empty |
| `/api/v1/recommendations/projects/{{project_id}}/` | GET | No body | 200 array |

## Verification checklist and unresolved items

- [x] Read the project instructions, README, architecture, approved DBML,
  current status, settings, and root URL configuration.
- [x] Inspected models, serializers, views, URL patterns, permission classes,
  and relevant tests for all eight mounted apps.
- [x] Endpoint index reflects all 32 API URL patterns and implemented methods
  in `config.urls` and the app URL modules.
- [x] Request/response fields and company permission rules are documented
  from source rather than inferred only from database models.
- [x] Distinguishes metadata/record management from binary file storage,
  external connection verification, autonomous agents, and recommendation
  generation, none of which is implemented by these APIs.
- [ ] Routes for deleting/changing company memberships, invitations, file
  uploads, provider credential exchange, autonomous agent execution, and
  recommendation generation are not implemented.
- [ ] Request `PUT` semantics are ordinary DRF serializer updates; clients
  should prefer `PATCH` when they intend to change only selected fields.
- [ ] No custom API schema, OpenAPI document, global error handler, pagination,
  filters, search, or ordering configuration was found. Query parameters and
  response-envelope behavior beyond the plain list/object shapes described
  here are not supported or verified.

No frontend code, application code, models, serializers, views, routes,
migrations, settings, or approved DBML was changed to create this guide.
