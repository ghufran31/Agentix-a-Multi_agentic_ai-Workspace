# Integrations app

## Scope

The app implements only the approved `connections` table through the
`Connection` model. It stores provider name, optional connection type and
account label, status, and an optional timestamp. These are metadata fields:
the app does not authenticate with or verify external providers, and it does
not store credentials, API keys, tokens, or secrets.

## Routes

All endpoints require JWT authentication.

| Method | Route | Behavior |
| --- | --- | --- |
| `GET` | `/api/v1/integrations/` | List connection records for companies where the requester is a member |
| `POST` | `/api/v1/integrations/` | Create a connection metadata record for a company where requester may write |
| `GET` | `/api/v1/integrations/<id>/` | Retrieve an accessible connection |
| `PUT`, `PATCH` | `/api/v1/integrations/<id>/` | Replace or partially update connection metadata |
| `DELETE` | `/api/v1/integrations/<id>/` | Delete an accessible connection record |

Creation returns 201, retrieval and updates return 200, deletion returns 204,
invalid fields or unauthorized company IDs return 400, and detail requests
for inaccessible IDs return 404.

## Request and response fields

- `company`: required company primary key; it must be a company where the
  requester has a writer membership.
- `provider`: required string, maximum 100 characters.
- `connection_type`: optional nullable string, maximum 100 characters.
- `account_name`: optional nullable string, maximum 255 characters.
- `status`: optional string, maximum 50 characters; defaults to
  `disconnected`.
- `connected_at`: optional nullable timestamp.
- `id`: generated primary key, returned read-only.

Responses contain only those schema fields. There are no credential fields.
A caller may set the status value as metadata; a value such as `connected`
does not mean an external connection was authenticated or verified.

The model maps to `connections`; migration:
`agentix_backend/integrations/migrations/0001_initial.py`.

## Authorization

Company members may list and retrieve connection records in their companies.
Only `owner`, `admin`, or `manager` memberships may create, update, or delete.
The company foreign key on create and update is restricted to companies where
the requester has one of these writer roles. Connection querysets are scoped
to the requester's memberships, so foreign-company IDs return 404 for
retrieve, update, and delete.

## Tests

Run `python manage.py test integrations companies accounts workforce
documents` from `agentix_backend`. Tests cover CRUD, defaults and nullable
fields, authentication, writer permissions, company scoping, unauthorized
company IDs, inaccessible records, response field safety, and route
resolution.
