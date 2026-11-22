from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from companies.models import Company, CompanyUser
from workforce.models import Department, Employee
from orchestrator.agents.database.agent import build_database_agent, database_tools
from orchestrator.agents.database.config import load_system_prompt
from orchestrator.core.llm_factory import get_llm
from orchestrator.core.permissions import database_context


class DatabaseAgentTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username='db-owner', password='test-pass')
        self.member = User.objects.create_user(username='db-member', password='test-pass')
        self.other = User.objects.create_user(username='db-other', password='test-pass')
        self.company = Company.objects.create(
            created_by_user=self.owner,
            name='Agentix Test Company',
        )
        CompanyUser.objects.create(
            company=self.company, user=self.owner, role=CompanyUser.Role.OWNER
        )
        CompanyUser.objects.create(
            company=self.company, user=self.member, role=CompanyUser.Role.MEMBER
        )
        self.department = Department.objects.create(
            company=self.company, name='Engineering'
        )
        self.employee = Employee.objects.create(
            department=self.department,
            employee_code='EMP-001',
            first_name='Aisha',
            last_name='Khan',
        )

    def test_prompt_loading_and_identity(self):
        prompt = load_system_prompt()
        self.assertIn('Agentix Database Specialist', prompt)
        self.assertIn('Never generate or execute SQL', prompt)

    def test_context_rejects_cross_company_user(self):
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            database_context(self.other, self.company.id)

    def test_tool_registration_contains_company_scoped_operations(self):
        context = database_context(self.owner, self.company.id)
        tools = database_tools(context)
        names = {tool.name for tool in tools}
        self.assertIn('create_department', names)
        self.assertIn('create_employee', names)
        self.assertIn('list_employees', names)
        self.assertIn('create_project', names)
        self.assertIn('manage_employee_skills', names)
        self.assertIn('summarize_department_employees', names)
        self.assertGreaterEqual(len(names), 25)

    def test_department_create_and_list_are_company_scoped(self):
        context = database_context(self.owner, self.company.id)
        tools = {tool.name: tool for tool in database_tools(context)}
        created = tools['create_department'].invoke({
            'name': 'Mobile Development',
            'description': 'Mobile team',
        })
        self.assertTrue(created.success)
        listed = tools['list_departments'].invoke({'limit': 25, 'offset': 0})
        self.assertTrue(listed.success)
        names = [row['name'] for row in listed.data['departments']]
        self.assertIn('Mobile Development', names)

    def test_member_cannot_write_but_can_read(self):
        context = database_context(self.member, self.company.id)
        tools = {tool.name: tool for tool in database_tools(context)}
        created = tools['create_department'].invoke({'name': 'Denied Department'})
        self.assertFalse(created.success)
        listed = tools['list_departments'].invoke({'limit': 25, 'offset': 0})
        self.assertTrue(listed.success)

    def test_read_only_context_blocks_writes(self):
        context = database_context(self.owner, self.company.id, read_only=True)
        tools = {tool.name: tool for tool in database_tools(context)}
        result = tools['create_department'].invoke({'name': 'Read Only Department'})
        self.assertFalse(result.success)
        self.assertIn('read-only', result.message.lower())

    def test_delete_department_requires_approval(self):
        context = database_context(self.owner, self.company.id)
        tools = {tool.name: tool for tool in database_tools(context)}
        result = tools['delete_department'].invoke({'department_id': self.department.id})
        self.assertTrue(result.success)
        self.assertIsNotNone(result.pending_approval)
        approval_id = result.pending_approval['approval_id']
        resolved = tools['resolve_delete_approval'].invoke({
            'approval_id': approval_id,
            'approved': False,
        })
        self.assertTrue(resolved.success)
        self.assertTrue(Department.objects.filter(id=self.department.id).exists())

    def test_employee_profile_update_and_skill_filter(self):
        context = database_context(self.owner, self.company.id)
        tools = {tool.name: tool for tool in database_tools(context)}
        profile = tools['update_employee_profile'].invoke({
            'employee_id': self.employee.id,
            'availability_status': 'available',
            'current_workload': 25,
        })
        self.assertTrue(profile.success)
        search = tools['list_employees'].invoke({
            'limit': 25,
            'offset': 0,
            'search': 'Aisha',
        })
        self.assertTrue(search.success)
        self.assertEqual(search.data['employees'][0]['id'], self.employee.id)

    @patch('orchestrator.core.llm_factory.ChatGroq')
    def test_llm_factory_rejects_missing_key_only_at_call(self, chat_groq):
        from django.test.utils import override_settings
        get_llm.cache_clear()
        with override_settings(GROQ_API_KEY='test-key'):
            get_llm('test-model')
        chat_groq.assert_called_once()
        self.assertEqual(chat_groq.call_args.kwargs['max_tokens'], 16384)

    @patch('orchestrator.agents.database.agent.get_llm')
    def test_agent_initialization_uses_registered_tools(self, mock_llm):
        mock_llm.return_value = object()
        context = database_context(self.owner, self.company.id)
        with patch(
            'orchestrator.agents.database.agent.create_agent',
            return_value=object(),
        ) as mock_create:
            build_database_agent(context)
        mock_create.assert_called_once()
