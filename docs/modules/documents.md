# Documents app

## Scope

The app implements only the approved `company_documents` database table
through `CompanyDocument`. It manages document metadata and the nullable text
`file_path` value only. It does not upload, validate, copy, or store a file at
that path.

## Routes

All routes require JWT authentication. Document detail IDs are integer
primary keys.

| Method | Route | Behavior |
| --- | --- | --- |
| `GET` | `/api/v1/documents/` | List documents for companies where the requester is a member |
| `POST` | `/api/v1/documents/` | Create document metadata for a company where requester may write |
| `GET` | `/api/v1/documents/<id>/` | Retrieve an accessible document |
| `PUT`, `PATCH` | `/api/v1/documents/<id>/` | Replace or partially update document metadata |
| `DELETE` | `/api/v1/documents/<id>/` | Delete an accessible document record |

Creation returns 201, retrieval and updates return 200, deletion returns 204,
and invalid fields or unauthorized company IDs return 400. An inaccessible
document detail ID returns 404.

## Authorization

All company members may list and retrieve records belonging to their
companies. Only `owner`, `admin`, or `manager` memberships may create,
update, or delete documents. The company foreign key on create or update is
limited to companies where the requester has one of those writer roles.
Document querysets are membership-scoped, so another company's records are
not exposed through list, retrieval, update, or deletion.

## Fields

- `company`: required company relation (`company_id` in PostgreSQL)
- `title`: required text, maximum 255 characters
- `document_type`: optional text, maximum 100 characters
- `description`: optional text
- `file_path`: optional text metadata; not a file upload
- `uploaded_at`: automatically defaulted current timestamp and read-only in
  the API

The model maps explicitly to `company_documents`. Its migration is
`agentix_backend/documents/migrations/0001_initial.py`.

## Tests

Run `python manage.py test documents companies accounts workforce` from
`agentix_backend`. Tests cover create/list/retrieve/update/delete, required
and optional values, authentication, member/write permissions, company
scoping, inaccessible IDs, company-ID validation, and route resolution.
