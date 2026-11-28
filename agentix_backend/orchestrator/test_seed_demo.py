from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from companies.models import Company
from orchestrator.ml_engine.ranking import rank_project_candidates
from workforce.models import Employee, EmployeeAIProfile, EmployeeSkill


class DemoSeedTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username='demo-owner')
        self.other_user = get_user_model().objects.create_user(username='other-owner')
        self.other_company = Company.objects.create(created_by_user=self.other_user, name='Existing company')

    def seed(self, **options):
        call_command('seed_agentix_demo', owner=self.owner.username, confirm_demo_seed=True,
                     stdout=StringIO(), **options)

    def test_defaults_ranking_and_idempotency(self):
        self.seed()
        company = Company.objects.get(created_by_user=self.owner)
        staff = Employee.objects.filter(department__company=company)
        self.assertEqual(company.departments.count(), 10)
        self.assertEqual(company.projects.count(), 20)
        self.assertEqual(company.memberships.get(user=self.owner).role, 'owner')
        self.assertEqual(staff.count(), 1000)
        self.assertEqual(staff.values('employee_code').distinct().count(), 1000)
        self.assertEqual(staff.filter(email__endswith='.invalid').values('email').distinct().count(), 1000)
        self.assertEqual(EmployeeAIProfile.objects.filter(employee__in=staff).count(), 1000)
        self.assertEqual(EmployeeSkill.objects.filter(employee__in=staff, skill__company=company).count(), 3000)

        for project in company.projects.order_by('pk').prefetch_related('requirements'):
            self.assertGreater(project.deadline, project.start_date)
            self.assertEqual(len(project.requirements.all()), 2)
        project = company.projects.get(name='Retail Order Tracker')
        employee = staff.filter(department__name='Mobile Engineering').order_by('pk').first()
        ranked, _ = rank_project_candidates(project, [employee], timezone.localdate())
        self.assertEqual(len(ranked), 1)
        employee.first_name = 'Edited'
        employee.save(update_fields=['first_name'])
        self.seed(departments=2, employees=12, projects=4, seed=88)
        employee.refresh_from_db()
        self.assertEqual(employee.first_name, 'Edited')
        self.assertEqual(staff.count(), 1000)
        self.assertEqual(company.projects.count(), 20)
        self.assertFalse(self.other_company.departments.exists())

    def test_requires_confirmation_and_rejects_existing_company(self):
        with self.assertRaisesMessage(CommandError, '--confirm-demo-seed'):
            call_command('seed_agentix_demo', owner=self.owner.username)
        with self.assertRaisesMessage(CommandError, 'already owns another company'):
            call_command('seed_agentix_demo', owner=self.other_user.username, confirm_demo_seed=True)
        self.assertEqual(Company.objects.count(), 1)

    def test_failure_rolls_back_and_alternate_sizes_work(self):
        with patch('projects.models.ProjectRequirement.objects.bulk_create', side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.seed(departments=2, employees=12, projects=4)
        self.assertEqual(Company.objects.count(), 1)
        self.assertFalse(Employee.objects.exists())
        self.seed(departments=2, employees=12, projects=4)
        company = Company.objects.get(created_by_user=self.owner)
        self.assertEqual(company.departments.count(), 2)
        self.assertEqual(company.projects.count(), 4)
        self.assertEqual(Employee.objects.filter(department__company=company).count(), 12)
