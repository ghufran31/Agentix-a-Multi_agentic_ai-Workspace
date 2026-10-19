# Approved database schema

This is the authoritative, approved DBML supplied by the project owner. Keep
the DBML below unchanged. Framework-managed Django authentication and JWT
blacklist tables are outside this business schema.

```dbml
Project Agentix {
  database_type: 'PostgreSQL'
  Note: 'Django-managed authentication; one company per user; company-specific skills; employees and AI agents; project assignment history.'
}

Enum company_user_role {
  owner
  admin
  manager
  member
}

Enum employment_status {
  active
  inactive
  on_leave
}

Enum availability_status {
  available
  partially_available
  unavailable
}

Table companies {
  id bigint [pk, increment]
  created_by_user_id bigint [not null, unique, note: 'References Django-managed auth user; one company per user']
  name varchar(255) [not null]
  industry varchar(150)
  description text
  email varchar(255)
  phone varchar(50)
  address text
  created_at timestamp [default: `now()`]
}

Table company_users {
  id bigint [pk, increment]
  company_id bigint [not null, ref: > companies.id]
  user_id bigint [not null, note: 'References Django-managed auth user']
  role company_user_role [not null, default: 'member']
  created_at timestamp [default: `now()`]

  indexes {
    (company_id, user_id) [unique]
  }
}

Table departments {
  id bigint [pk, increment]
  company_id bigint [not null, ref: > companies.id]
  name varchar(150) [not null]
  description text
  created_at timestamp [default: `now()`]
}

Table employees {
  id bigint [pk, increment]
  department_id bigint [not null, ref: > departments.id]
  employee_code varchar(50) [not null]
  first_name varchar(100) [not null]
  last_name varchar(100) [not null]
  email varchar(255)
  phone varchar(50)
  address text
  date_of_birth date
  created_at timestamp [default: `now()`]

  indexes {
    (department_id, employee_code) [unique]
  }
}

Table employee_ai_profiles {
  id bigint [pk, increment]
  employee_id bigint [not null, unique, ref: - employees.id]
  job_title varchar(150)
  education varchar(255)
  experience_years decimal(5,2) [default: 0]
  performance_score decimal(5,2)
  availability_status availability_status [not null, default: 'available']
  current_workload decimal(5,2) [default: 0]
  previous_project_score decimal(5,2)
  completed_projects int [default: 0]
  employment_status employment_status [not null, default: 'active']
  updated_at timestamp [default: `now()`]
}

Table skills {
  id bigint [pk, increment]
  company_id bigint [not null, ref: > companies.id]
  name varchar(150) [not null]
  category varchar(100)
  description text
  created_at timestamp [default: `now()`]

  indexes {
    (company_id, name) [unique]
  }
}

Table employee_skills {
  id bigint [pk, increment]
  employee_id bigint [not null, ref: > employees.id]
  skill_id bigint [not null, ref: > skills.id]
  proficiency decimal(5,2)
  years_experience decimal(5,2) [default: 0]

  indexes {
    (employee_id, skill_id) [unique]
  }
}

Table company_documents {
  id bigint [pk, increment]
  company_id bigint [not null, ref: > companies.id]
  title varchar(255) [not null]
  document_type varchar(100)
  description text
  file_path text
  uploaded_at timestamp [default: `now()`]
}

Table connections {
  id bigint [pk, increment]
  company_id bigint [not null, ref: > companies.id]
  provider varchar(100) [not null]
  connection_type varchar(100)
  account_name varchar(255)
  status varchar(50) [default: 'disconnected']
  connected_at timestamp
}

Table ai_agents {
  id bigint [pk, increment]
  company_id bigint [not null, ref: > companies.id]
  name varchar(150) [not null]
  agent_type varchar(100)
  description text
  capabilities text
  status varchar(50) [default: 'active']
  created_at timestamp [default: `now()`]
}

Table projects {
  id bigint [pk, increment]
  company_id bigint [not null, ref: > companies.id]
  name varchar(255) [not null]
  description text
  status varchar(50) [default: 'draft']
  priority varchar(50) [default: 'medium']
  start_date date
  deadline date
  created_at timestamp [default: `now()`]
}

Table project_requirements {
  id bigint [pk, increment]
  project_id bigint [not null, ref: > projects.id]
  requirement text [not null]
  required_skills text
  required_roles text
  priority varchar(50) [default: 'medium']
  deadline date
  created_at timestamp [default: `now()`]
}

Table recommendations {
  id bigint [pk, increment]
  project_id bigint [not null, ref: > projects.id]
  employee_id bigint [ref: > employees.id]
  ai_agent_id bigint [ref: > ai_agents.id]
  recommended_role varchar(150)
  score decimal(8,5) [not null]
  rank int [not null]
  reason text
  status varchar(50) [default: 'pending']
  created_at timestamp [default: `now()`]

  checks {
    `num_nonnulls(employee_id, ai_agent_id) = 1` [name: 'recommendation_exactly_one_candidate']
  }
}

Table project_members {
  id bigint [pk, increment]
  project_id bigint [not null, ref: > projects.id]
  employee_id bigint [ref: > employees.id]
  ai_agent_id bigint [ref: > ai_agents.id]
  role varchar(150)
  member_type varchar(50) [not null]
  status varchar(50) [default: 'active']
  assigned_at timestamp [default: `now()`]

  checks {
    `num_nonnulls(employee_id, ai_agent_id) = 1` [name: 'project_member_exactly_one_candidate']
  }
}
```

## Implemented schema status

The `companies` app implements only the `companies` and `company_users`
tables from the approved DBML above. Migration
`agentix_backend/companies/migrations/0001_initial.py` uses those exact table
names, maps `created_by_user`, `company`, and `user` to the corresponding
`*_id` columns, enforces one company per creator, and enforces uniqueness of
each `(company_id, user_id)` membership.

The `workforce` app implements only the `departments`, `employees`,
`employee_ai_profiles`, `skills`, and `employee_skills` tables. Its initial
migration uses those exact table names and column relationships and enforces
the approved unique constraints on department/employee code, company/skill
name, one profile per employee, and employee/skill assignment. The follow-up
migration preserves database-side `now()` defaults for workforce timestamp
columns.

The `documents` app implements only the approved `company_documents` table
using the exact DBML fields and relationships. `file_path` is stored as
nullable text metadata only; the app does not upload or store files. Its
`uploaded_at` field has both an application-side and database-side current
timestamp default.

The `integrations` app implements only the approved `connections` table with
the DBML fields and relation. Its `status` defaults to `disconnected`, and
`connected_at` is nullable. Provider status is metadata and does not prove
that an external service connection was authenticated or verified. This app
does not store credentials. No other business tables were added by the
integrations app.

The `agents` app implements only the approved `ai_agents` table and fields.
Its `created_at` has application-side and database-side current timestamp
defaults. Agent records are metadata only and do not imply autonomous
execution, tool use, or AI workflow processing. Django auth and Simple JWT
tables remain framework-managed and are outside this business schema.
