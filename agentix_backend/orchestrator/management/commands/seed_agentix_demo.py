from datetime import timedelta
from random import Random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from companies.models import Company, CompanyUser
from orchestrator.ml_engine.loader import load_model
from projects.models import Project, ProjectRequirement
from workforce.models import Department, Employee, EmployeeAIProfile, EmployeeSkill, Skill


DEMO_NAME = 'Agentix Demo Company'
DEMO_EMAIL = 'company@agentix-demo.example.invalid'
TEAMS = (
    ('Mobile Engineering', ('Flutter', 'Dart', 'REST APIs'), 'Mobile Developer',
     ('Retail Order Tracker', 'Field Service Mobile App'), 'Implement authenticated offline workflows and data sync.'),
    ('Backend Engineering', ('Python', 'Django', 'PostgreSQL'), 'API Engineer',
     ('Customer Billing API', 'Partner Onboarding Service'), 'Implement tenant-scoped APIs with audit records and integration tests.'),
    ('Web Engineering', ('React', 'TypeScript', 'Accessibility'), 'Frontend Developer',
     ('Supplier Portal', 'Customer Self-Service Dashboard'), 'Build accessible forms and verify responsive behavior.'),
    ('Data Engineering', ('SQL', 'Python', 'dbt'), 'Data Engineer',
     ('Sales Data Warehouse', 'Inventory Reconciliation Pipeline'), 'Build incremental pipelines with data quality and freshness checks.'),
    ('Applied AI', ('Python', 'XGBoost', 'Model Evaluation'), 'ML Engineer',
     ('Demand Forecasting Pilot', 'Support Ticket Triage'), 'Evaluate a baseline model with held-out data and publish error metrics.'),
    ('Platform Engineering', ('Docker', 'Terraform', 'Linux'), 'DevOps Engineer',
     ('Container Delivery Platform', 'Disaster Recovery Automation'), 'Automate deployment and verify recovery in a staging environment.'),
    ('Quality Engineering', ('Playwright', 'Python', 'Test Automation'), 'QA Engineer',
     ('Checkout Regression Suite', 'Release Readiness Automation'), 'Automate critical flows and add reproducible failure reporting.'),
    ('Security Engineering', ('Threat Modeling', 'OAuth', 'Linux'), 'Security Engineer',
     ('Identity Access Review', 'API Security Hardening'), 'Document trust boundaries and verify scoped access controls.'),
    ('Product Design', ('Figma', 'User Research', 'Accessibility'), 'UX Designer',
     ('Merchant Onboarding Redesign', 'Accessible Account Settings'), 'Prototype key journeys and validate them with usability sessions.'),
    ('Analytics', ('SQL', 'Power BI', 'Data Visualization'), 'Data Analyst',
     ('Fulfillment KPI Dashboard', 'Customer Retention Analysis'), 'Define metric ownership and reconcile reporting with source records.'),
)
FIRST_NAMES = ('Amira', 'Yusuf', 'Maya', 'Daniel', 'Noura', 'Mateo', 'Leila', 'Hana', 'Omar', 'Sofia')
LAST_NAMES = ('Haddad', 'Reyes', 'Saleh', 'Chen', 'Nasser', 'Patel', 'Ito', 'Santos', 'Khan', 'Silva')


class Command(BaseCommand):
    help = 'Create one isolated synthetic Agentix company for an existing user.'

    def add_arguments(self, parser):
        parser.add_argument('--owner', required=True, help='Username of an active user without an owned company.')
        parser.add_argument('--confirm-demo-seed', action='store_true')
        parser.add_argument('--departments', type=int, default=10)
        parser.add_argument('--employees', type=int, default=1000)
        parser.add_argument('--projects', type=int, default=20)
        parser.add_argument('--seed', type=int, default=42)

    def handle(self, *args, **options):
        if not options['confirm_demo_seed']:
            raise CommandError('Pass --confirm-demo-seed to authorize creating synthetic data.')
        departments, employees, projects = (options[key] for key in ('departments', 'employees', 'projects'))
        if not 1 <= departments <= len(TEAMS) or not departments <= employees <= 10000 or not 1 <= projects <= 1000:
            raise CommandError('Use 1–10 departments, at least one employee per department (max 10000), and 1–1000 projects.')

        with transaction.atomic():
            users = get_user_model()
            owner = users.objects.select_for_update().filter(
                **{users.USERNAME_FIELD: options['owner'], 'is_active': True},
            ).first()
            if owner is None:
                raise CommandError('The owner must be an existing active user.')
            existing = Company.objects.filter(created_by_user=owner).first()
            if existing:
                if existing.name != DEMO_NAME or existing.email != DEMO_EMAIL:
                    raise CommandError('This user already owns another company. Choose a dedicated demo account.')
                self.stdout.write(f'Demo company {existing.pk} already exists. No records changed.')
                return

            _, metadata = load_model()
            categories = metadata['categories']
            roles = categories['job_title']
            priorities = [value for value in ('low', 'medium', 'high') if value in categories['project_priority']]
            if not priorities or not roles or 'active' not in categories['employment_status'] or (
                'available' not in categories['availability_status']
            ):
                raise CommandError('The model categories cannot represent the demo profiles.')
            random = Random(options['seed'])
            company = Company.objects.create(
                created_by_user=owner, name=DEMO_NAME, email=DEMO_EMAIL,
                industry='Software and IT Services', description='Synthetic data for Agentix demonstrations.',
            )
            CompanyUser.objects.create(company=company, user=owner, role=CompanyUser.Role.OWNER)
            self.seed_company(company, TEAMS[:departments], employees, projects, random, categories, priorities)
        self.stdout.write(self.style.SUCCESS(
            f'Created demo company {company.pk} with {departments} departments, {employees} employees and {projects} projects.'
        ))

    def seed_company(self, company, teams, count, project_count, random, categories, priorities):
        departments = Department.objects.bulk_create([
            Department(company=company, name=team[0]) for team in teams
        ])
        skills = Skill.objects.bulk_create([
            Skill(company=company, name=name)
            for name in sorted({name for team in teams for name in team[1]})
        ])
        skill_ids = {skill.name: skill.pk for skill in skills}
        titles = categories['job_title']
        team_roles = [team[2] if team[2] in titles else titles[index % len(titles)]
                      for index, team in enumerate(teams)]
        staff = Employee.objects.bulk_create([
            Employee(
                department=departments[index % len(teams)],
                employee_code=f'DEMO-{company.pk}-{index + 1:05d}',
                first_name=random.choice(FIRST_NAMES), last_name=random.choice(LAST_NAMES),
                email=f'employee-{company.pk}-{index + 1:05d}@agentix-demo.example.invalid',
            )
            for index in range(count)
        ], batch_size=500)

        profiles, assignments = [], []
        for index, employee in enumerate(staff):
            team_index = index % len(teams)
            experience = random.randint(1, 18)
            availability = 'available'
            if index >= len(teams):
                availability = random.choice([
                    value for value in ('available', 'available', 'partially_available', 'unavailable')
                    if value in categories['availability_status']
                ])
            profiles.append(EmployeeAIProfile(
                employee=employee, job_title=team_roles[team_index], experience_years=experience,
                availability_status=availability, employment_status='active',
                performance_score=random.randint(60, 99), previous_project_score=random.randint(55, 98),
                current_workload=random.randint(10, 45) if availability == 'available' else random.randint(55, 95),
                completed_projects=random.randint(0, experience * 3),
                education=random.choice(('BSc Computer Science', 'BEng Software Engineering', 'Professional Diploma')),
            ))
            for name in teams[team_index][1]:
                assignments.append(EmployeeSkill(
                    employee=employee, skill_id=skill_ids[name], proficiency=random.randint(2, 5),
                    years_experience=random.randint(1, experience),
                ))
        EmployeeAIProfile.objects.bulk_create(profiles, batch_size=500)
        EmployeeSkill.objects.bulk_create(assignments, batch_size=500)

        today = timezone.localdate()
        projects, requirements = [], []
        for index in range(project_count):
            team_index = index % len(teams)
            _, required_skills, _, names, deliverable = teams[team_index]
            cycle = index // len(teams)
            name = names[cycle % len(names)]
            if cycle >= len(names):
                name = f'{name} — Release {cycle // len(names) + 1}'
            start = today + timedelta(days=index % 14)
            deadline = start + timedelta(days=random.randint(30, 150))
            priority = random.choice(priorities)
            projects.append(Project(company=company, name=name, description=deliverable,
                                    start_date=start, deadline=deadline, priority=priority))
            requirements.append((required_skills, team_roles[team_index], deliverable))
        saved = Project.objects.bulk_create(projects, batch_size=500)
        ProjectRequirement.objects.bulk_create([
            ProjectRequirement(
                project=project, requirement=text, required_skills=', '.join(required_skills),
                required_roles=role, priority=project.priority, deadline=project.deadline,
            )
            for project, (required_skills, role, deliverable) in zip(saved, requirements, strict=True)
            for text in (deliverable, f'Validate {project.name} in staging and document acceptance criteria.')
        ], batch_size=500)
