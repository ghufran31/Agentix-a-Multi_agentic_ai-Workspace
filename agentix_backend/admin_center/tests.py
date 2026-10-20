import os
import subprocess
import sys
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from agents.models import AIAgent
from companies.models import Company, CompanyUser
from admin_center.dashboard import build_dashboard
from admin_center.site import AgentixAdminSite
from projects.models import Project

User = get_user_model()
BACKEND_ROOT = Path(__file__).resolve().parent.parent


class DashboardMetricsTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.site = AgentixAdminSite(name='admin')
        self.password = 'Secure-admin-pass-482!'
        self.superuser = User.objects.create_superuser(
            username='ax-super',
            email='ax-super@example.test',
            password=self.password,
        )
        self.owner = User.objects.create_user(
            username='ax-owner',
            email='ax-owner@example.test',
            password=self.password,
        )
        self.company = Company.objects.create(
            name='Acme Labs',
            created_by_user=self.owner,
        )
        CompanyUser.objects.create(
            company=self.company,
            user=self.owner,
            role=CompanyUser.Role.OWNER,
        )
        self.project = Project.objects.create(
            company=self.company,
            name='Launch Pad',
            status='active',
        )
        AIAgent.objects.create(
            company=self.company,
            name='Planner',
            status='active',
        )

    def _request(self, user):
        request = self.factory.get('/admin/')
        request.user = user
        return request

    def test_dashboard_reports_real_counts_for_superuser(self):
        request = self._request(self.superuser)

        dashboard = build_dashboard(request, self.site)
        cards = {card.key: card for card in dashboard.cards}

        self.assertIn('users', cards)
        self.assertEqual(cards['users'].count, User.objects.count())
        self.assertEqual(cards['companies'].count, 1)
        self.assertEqual(cards['memberships'].count, 1)
        self.assertEqual(cards['projects'].count, 1)
        self.assertEqual(cards['agents'].count, 1)
        self.assertFalse(dashboard.is_empty)
        self.assertEqual(len(dashboard.recent_companies), 1)
        self.assertEqual(dashboard.recent_companies[0].label, 'Acme Labs')
        project_statuses = {
            item.label: item.count for item in cards['projects'].status_breakdown
        }
        self.assertEqual(project_statuses.get('active'), 1)

    def test_dashboard_empty_state_when_no_business_records(self):
        CompanyUser.objects.all().delete()
        AIAgent.objects.all().delete()
        Project.objects.all().delete()
        Company.objects.all().delete()
        request = self._request(self.superuser)

        dashboard = build_dashboard(request, self.site)
        cards = {card.key: card for card in dashboard.cards}

        self.assertEqual(cards['companies'].count, 0)
        self.assertEqual(cards['projects'].count, 0)
        self.assertEqual(cards['agents'].count, 0)
        self.assertTrue(dashboard.is_empty)
        self.assertEqual(dashboard.recent_companies, [])

    def test_dashboard_hides_cards_without_view_permission(self):
        limited = User.objects.create_user(
            username='ax-limited',
            email='ax-limited@example.test',
            password=self.password,
            is_staff=True,
        )
        company_ct = ContentType.objects.get_for_model(Company)
        view_company = Permission.objects.get(
            content_type=company_ct,
            codename='view_company',
        )
        limited.user_permissions.add(view_company)
        request = self._request(limited)

        dashboard = build_dashboard(request, self.site)
        keys = {card.key for card in dashboard.cards}

        self.assertEqual(keys, {'companies'})
        self.assertEqual(dashboard.cards[0].count, 1)
        self.assertEqual(dashboard.recent_projects, [])
        self.assertEqual(dashboard.quick_actions, [])


class AdminIndexCustomizationTests(TestCase):
    def setUp(self):
        self.password = 'Secure-admin-pass-482!'
        self.superuser = User.objects.create_superuser(
            username='ax-index-super',
            email='ax-index-super@example.test',
            password=self.password,
        )
        self.client = Client()

    def test_custom_admin_index_renders_dashboard_for_superuser(self):
        self.client.login(username='ax-index-super', password=self.password)

        response = self.client.get(reverse('admin:index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Master Control Center')
        self.assertContains(response, 'Platform overview')
        self.assertContains(response, 'admin_center/css/tokens.css')
        self.assertContains(response, 'admin_center/css/admin.css')
        self.assertIn('dashboard', response.context)
        self.assertTrue(response.context['dashboard'].cards)

    def test_custom_admin_site_keeps_existing_model_registrations(self):
        from django.contrib import admin

        registered_labels = {
            model._meta.label_lower for model in admin.site._registry
        }
        expected_labels = {
            'auth.user',
            'auth.group',
            'companies.company',
            'companies.companyuser',
            'workforce.department',
            'workforce.employee',
            'workforce.employeeaiprofile',
            'workforce.skill',
            'workforce.employeeskill',
            'documents.companydocument',
            'integrations.connection',
            'agents.aiagent',
            'projects.project',
            'projects.projectrequirement',
            'projects.projectmember',
            'recommendations.recommendation',
        }

        self.assertTrue(expected_labels.issubset(registered_labels))

    def test_company_owner_without_staff_cannot_access_admin(self):
        owner = User.objects.create_user(
            username='ax-api-owner',
            email='ax-api-owner@example.test',
            password=self.password,
        )
        company = Company.objects.create(name='No Admin Co', created_by_user=owner)
        CompanyUser.objects.create(
            company=company,
            user=owner,
            role=CompanyUser.Role.OWNER,
        )
        self.client.login(username='ax-api-owner', password=self.password)

        response = self.client.get(reverse('admin:index'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)


class FeatureFlagSettingsTests(SimpleTestCase):
    def test_customization_flag_enabled_by_default(self):
        from django.conf import settings

        self.assertTrue(settings.AGENTIX_ADMIN_CUSTOMIZATION_ENABLED)
        self.assertIn('admin_center', settings.INSTALLED_APPS)
        self.assertIn(
            'admin_center.admin_config.AgentixAdminConfig',
            settings.INSTALLED_APPS,
        )
        self.assertNotIn('django.contrib.admin', settings.INSTALLED_APPS)

    def test_disabled_flag_restores_stock_admin_apps_in_fresh_process(self):
        env = os.environ.copy()
        env['AGENTIX_ADMIN_CUSTOMIZATION_ENABLED'] = 'false'
        # Ensure dotenv values for secrets remain available to the child process.
        code = (
            'import django; '
            'from django.conf import settings; '
            'django.setup(); '
            'assert settings.AGENTIX_ADMIN_CUSTOMIZATION_ENABLED is False, settings.AGENTIX_ADMIN_CUSTOMIZATION_ENABLED; '
            'assert "django.contrib.admin" in settings.INSTALLED_APPS; '
            'assert "admin_center" not in settings.INSTALLED_APPS; '
            'assert "admin_center.admin_config.AgentixAdminConfig" not in settings.INSTALLED_APPS; '
            'from django.contrib import admin; '
            'from django.template.loader import get_template; '
            'from admin_center.site import AgentixAdminSite; '
            'assert not isinstance(admin.site, AgentixAdminSite), type(admin.site); '
            'assert admin.site.index_template is None; '
            'assert admin.site.login_template is None; '
            'template_path = get_template("admin/index.html").origin.name.replace("\\\\", "/"); '
            'assert template_path.endswith("/django/contrib/admin/templates/admin/index.html"), template_path; '
            'from django.apps import apps; '
            'expected = ("auth.User", "auth.Group", "companies.Company", "companies.CompanyUser", '
            '"workforce.Department", "workforce.Employee", "workforce.EmployeeAIProfile", '
            '"workforce.Skill", "workforce.EmployeeSkill", "documents.CompanyDocument", '
            '"integrations.Connection", "agents.AIAgent", "projects.Project", '
            '"projects.ProjectRequirement", "projects.ProjectMember", '
            '"recommendations.Recommendation"); '
            'missing = [label for label in expected if apps.get_model(label) not in admin.site._registry]; '
            'assert not missing, missing; '
            'print("FLAG_OFF_STOCK_TEMPLATE_AND_MODELS_OK")'
        )
        result = subprocess.run(
            [sys.executable, 'manage.py', 'shell', '-c', code],
            cwd=BACKEND_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f'stdout={result.stdout}\nstderr={result.stderr}',
        )
        self.assertIn('FLAG_OFF_STOCK_TEMPLATE_AND_MODELS_OK', result.stdout)


@override_settings(AGENTIX_ADMIN_CUSTOMIZATION_ENABLED=False)
class FeatureFlagOverrideDoesNotSwapInstalledAppsMidProcess(SimpleTestCase):
    """Document that the flag is applied at process start via INSTALLED_APPS."""

    def test_override_settings_alone_does_not_remove_admin_center_app(self):
        from django.conf import settings

        self.assertFalse(settings.AGENTIX_ADMIN_CUSTOMIZATION_ENABLED)
        # INSTALLED_APPS was already built when Django started for the test run.
        self.assertIn('admin_center', settings.INSTALLED_APPS)
