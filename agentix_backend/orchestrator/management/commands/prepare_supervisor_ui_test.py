from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from companies.models import Company, CompanyUser
from orchestrator.graph.checkpoints import open_postgres_checkpoints
from orchestrator.graph.console_isolation import (
    ConsoleIsolationError, require_test_checkpoint, require_test_orm,
)
from orchestrator.graph.console_journal import setup_console_tables
from orchestrator.ml_engine.loader import load_model
from workforce.models import Department, Employee, EmployeeAIProfile, EmployeeSkill, Skill


USERNAME = 'agentix-ui-owner'
EMAIL = 'agentix-ui-owner@example.invalid'
COMPANY = 'Agentix Disposable UI Fixtures'


class Command(BaseCommand):
    help = 'Prepare console storage and synthetic UI fixtures only in PostgreSQL test_Agentix.'

    def handle(self, *args, **kwargs):
        try:
            require_test_orm()
            with open_postgres_checkpoints() as store:
                require_test_checkpoint(store.connection)
            with open_postgres_checkpoints(setup=True) as store:
                require_test_checkpoint(store.connection)
                setup_console_tables(store.connection)
        except ConsoleIsolationError as exc:
            raise CommandError(str(exc)) from None

        _, metadata = load_model()
        job_title = metadata['categories']['job_title'][0]
        with transaction.atomic():
            user, created = get_user_model().objects.get_or_create(
                username=USERNAME, defaults={'email': EMAIL, 'is_staff': True},
            )
            if user.email != EMAIL or not user.is_staff or not user.is_active or user.is_superuser:
                raise CommandError('The fixture username belongs to an unexpected account.')
            if created:
                user.set_unusable_password()
                user.save(update_fields=['password'])
            company, _ = Company.objects.get_or_create(created_by_user=user, defaults={'name': COMPANY})
            if company.name != COMPANY:
                raise CommandError('The fixture user already owns an unexpected company.')
            membership, _ = CompanyUser.objects.get_or_create(
                company=company, user=user, defaults={'role': CompanyUser.Role.OWNER},
            )
            if membership.role != CompanyUser.Role.OWNER or CompanyUser.objects.filter(
                user=user,
            ).exclude(company=company).exists():
                raise CommandError('The fixture user has unexpected company memberships.')
            department, _ = Department.objects.get_or_create(company=company, name='UI Engineering')
            skills = [Skill.objects.get_or_create(company=company, name=name)[0]
                      for name in ('Flutter', 'Dart', 'Python', 'Django', 'PostgreSQL')]
            for index in range(1, 6):
                employee, _ = Employee.objects.get_or_create(
                    department=department, employee_code=f'ui-eligible-{index}',
                    defaults={'first_name': 'Test Employee', 'last_name': str(index)},
                )
                EmployeeAIProfile.objects.get_or_create(employee=employee, defaults={
                    'job_title': job_title, 'experience_years': 2 + index,
                    'performance_score': 70 + index, 'previous_project_score': 70 + index,
                    'current_workload': 15 + index, 'completed_projects': index,
                    'availability_status': EmployeeAIProfile.AvailabilityStatus.AVAILABLE,
                    'employment_status': EmployeeAIProfile.EmploymentStatus.ACTIVE,
                })
                for skill in skills:
                    EmployeeSkill.objects.get_or_create(employee=employee, skill=skill, defaults={
                        'proficiency': 4, 'years_experience': 2,
                    })
        self.stdout.write(self.style.SUCCESS(
            f'ORM and checkpoint database: test_Agentix. Fixture user: {USERNAME}. '
            f'Company: {company.pk}. Prepared five synthetic employee records.'
        ))
