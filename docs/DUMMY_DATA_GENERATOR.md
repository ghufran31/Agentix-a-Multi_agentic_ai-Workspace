# Agentix dummy data generator

Use `seed_agentix_demo` to populate a dedicated synthetic company for demos,
UI walkthroughs, or employee matching. The generator uses the bundled XGBoost
model's supported categories for job titles, availability, employment status,
and project priority. Seeding is an explicit post-deployment operation.

## Default dataset

| Record | Count |
| --- | ---: |
| Demo company | 1 |
| Departments | 10 |
| Unique employees | 1,000 |
| Employee AI profiles | 1,000 |
| Projects | 20 |
| Project requirements | 40 |
| Employee skill assignments | 3,000 |

Each project has a start date, a deadline, and two requirements with skills
and roles. Skills are shared within the company, with three skill assignments
per employee. Synthetic employee email addresses use the reserved `.invalid`
domain.

## Generate the data in Dokploy

1. Confirm the Agentix deployment is healthy, migrations have run, and the
   web image contains the seeding command and bundled model artifacts.
2. Register a dedicated user with username `demo-owner` through the Agentix
   signup flow, or create a regular user in Django Admin. Keep the account
   active and leave it without an owned company. The command assigns the
   company owner role during seeding. Django staff or superuser status is
   unnecessary for this account.
3. In Dokploy, open the Agentix Compose service and select the terminal for
   the **web** container. Run the command from the directory containing
   `manage.py`. The deployment image uses `/app`.
4. Run the following command and note the company ID printed on success.

   ```sh
   python manage.py seed_agentix_demo --owner demo-owner --confirm-demo-seed
   ```

## Configuration

| Option | Default | Behavior |
| --- | --- | --- |
| `--owner USERNAME` | Required | Selects an existing active user who will own the demo company. |
| `--confirm-demo-seed` | Required | Explicitly authorizes the seed operation. |
| `--departments N` | 10 | Selects 1–10 departments. |
| `--employees N` | 1,000 | Creates up to 10,000 employees, with at least one per department. |
| `--projects N` | 20 | Creates 1–1,000 projects. |
| `--seed N` | 42 | Sets the random seed for generated values. Deadlines are relative to the execution date. |

For a smaller dataset, run this as the first seed for a dedicated account:

```sh
python manage.py seed_agentix_demo --owner demo-owner --confirm-demo-seed --departments 4 --employees 100 --projects 8 --seed 17
```

View the command's built-in help:

```sh
python manage.py seed_agentix_demo --help
```

## Duplicate prevention and transaction safety

Employee codes and emails incorporate the company ID and employee sequence
number. The command locks the owner record to serialize concurrent runs for
that owner and creates all records in one database transaction. A failure
rolls back the company and its generated records together.

A repeat run for the same owner reports that the demo company already exists
and leaves existing rows intact. Counts and seed values apply only on initial
creation. If the owner already owns another company, the command exits before
writing anything.

## Verify the data

Sign in as `demo-owner` and open **Agentix Demo Company**. Check the workforce
and project lists. For exact counts, open a read-only verification session
in the web container:

```sh
python manage.py shell
```

Run the following queries in that shell:

```python
from companies.models import Company
from projects.models import ProjectRequirement
from workforce.models import Employee, EmployeeAIProfile, EmployeeSkill

company = Company.objects.get(
    created_by_user__username="demo-owner",
    email="company@agentix-demo.example.invalid",
)
employees = Employee.objects.filter(department__company=company)
print("Departments:", company.departments.count())
print("Employees:", employees.count())
print("Unique employee codes:", employees.values("employee_code").distinct().count())
print("Unique employee emails:", employees.values("email").distinct().count())
print("AI profiles:", EmployeeAIProfile.objects.filter(employee__in=employees).count())
print("Projects:", company.projects.count())
print("Requirements:", ProjectRequirement.objects.filter(project__company=company).count())
print("Skill assignments:", EmployeeSkill.objects.filter(employee__in=employees, skill__company=company).count())
```

Compare the results with the default dataset table or your first-run options.
Both unique employee counts should equal the employee count. For deployment
details, see the [Dokploy guide](deployment/DOKPLOY.md).
