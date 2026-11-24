from datetime import date
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import ValidationError

from companies.models import Company, CompanyUser
from orchestrator.agents.project.agent import (
    build_project_agent, execute_project_task, project_tools,
)
from orchestrator.agents.project.config import load_system_prompt
from orchestrator.agents.project.schemas import (
    ProjectAgentOutput, ProjectSpecification, RequiredSkill,
)
from orchestrator.core.permissions import database_context
from orchestrator.tools.project.planning_tools import generate_roadmap
from orchestrator.tools.project.full_plan_tools import full_plan_tools
from orchestrator.tools.project.requirements_tools import analyze_description
from orchestrator.tools.project.role_tools import identify_roles
from orchestrator.tools.project.technology_tools import recommend_stack
from workforce.models import Skill


def specification_data():
    return {
        'name': 'Commerce Project',
        'description': 'An e-commerce application.',
        'project_type': 'e-commerce',
        'features': [{
            'name': 'Checkout', 'description': 'Allow customer checkout.',
            'priority': 'must', 'source': 'user',
        }],
        'functional_requirements': [{
            'identifier': 'FR-001', 'description': 'Customers can check out.',
            'related_features': ['Checkout'], 'priority': 'must', 'source': 'user',
        }],
        'nonfunctional_requirements': [],
        'technology_stack': {
            'choices': [{
                'layer': 'backend', 'name': 'Django REST Framework',
                'purpose': 'API', 'rationale': 'Mature API framework.',
                'source': 'recommended', 'alternatives': ['FastAPI'],
            }],
            'architecture_style': 'Modular API', 'notes': [],
        },
        'required_roles': [{
            'name': 'Backend Engineer', 'responsibilities': ['Build API'],
            'skills': ['Python'], 'suggested_count': 1,
        }],
        'required_skills': [{
            'name': 'Python', 'category': 'Technical', 'roles': ['Backend Engineer'],
            'taxonomy_status': 'proposed', 'existing_skill_id': None,
        }],
        'milestones': [{
            'name': 'Build', 'objective': 'Build features', 'deliverables': ['API'],
            'dependencies': [], 'estimated_duration_weeks': 4,
        }],
        'constraints': [], 'assumptions': [], 'risks': [{
            'description': 'Scope growth', 'likelihood': 'medium',
            'impact': 'high', 'mitigation': 'Control the backlog.',
        }], 'missing_information': [],
        'limitations': ['No persistence performed.'],
    }


class ProjectSchemaTests(TestCase):
    def test_valid_nested_specification_serializes(self):
        spec = ProjectSpecification.model_validate(specification_data())
        self.assertEqual(spec.model_dump()['functional_requirements'][0]['identifier'], 'FR-001')
        self.assertEqual(spec.risks[0].impact, 'high')
        self.assertIsNone(spec.deadline)

    def test_deadline_accepts_valid_iso_date_and_rejects_invalid_values(self):
        data = specification_data()
        data['deadline'] = '2027-01-15'
        self.assertEqual(
            ProjectSpecification.model_validate(data).deadline,
            date(2027, 1, 15),
        )
        for invalid in ('2027-1-15', '2027-02-30', 'next month'):
            with self.subTest(deadline=invalid):
                data['deadline'] = invalid
                with self.assertRaises(ValidationError):
                    ProjectSpecification.model_validate(data)

    def test_invalid_identifier_is_rejected(self):
        data = specification_data()
        data['functional_requirements'][0]['identifier'] = 'REQ-1'
        with self.assertRaises(ValidationError):
            ProjectSpecification.model_validate(data)

    def test_existing_skill_requires_database_id(self):
        with self.assertRaises(ValidationError):
            RequiredSkill(name='Python', category='Technical', taxonomy_status='existing')

    def test_output_cannot_claim_persistence(self):
        with self.assertRaises(ValidationError):
            ProjectAgentOutput(
                outcome='unsupported', response='Not available.',
                persistence_performed=True,
            )

    def test_clarification_requires_questions(self):
        with self.assertRaises(ValidationError):
            ProjectAgentOutput(
                outcome='clarification', response='Please clarify.',
                clarification={'understood_request': 'App', 'questions': []},
            )


class ProjectToolTests(TestCase):
    def test_requirement_extraction_preserves_explicit_items(self):
        result = analyze_description(
            'Build a food delivery app with payments, order tracking, an admin dashboard, Flutter, and PostgreSQL within four months.'
        )
        self.assertIn('Payments', result['features'])
        self.assertIn('Real-time tracking', result['features'])
        self.assertIn('Flutter', result['user_required_technologies'])
        self.assertEqual(result['constraints'][0]['category'], 'timeline')

    def test_hyphenated_deadline_and_drf_are_normalized(self):
        result = analyze_description(
            'Use Django REST Framework with a four-month deadline.'
        )
        self.assertEqual(result['constraints'][0]['description'], 'four-month')
        self.assertIn('Django REST Framework', result['user_required_technologies'])
        self.assertNotIn('Django', result['user_required_technologies'])

    def test_vague_request_identifies_essential_gap(self):
        result = analyze_description('Build an app.')
        self.assertTrue(result['missing_essential_information'][0]['essential'])

    def test_stack_honors_user_backend_override(self):
        stack = recommend_stack('social media', ['mobile feed'], ['Flutter', 'FastAPI', 'PostgreSQL'])
        choices = {item['layer']: item for item in stack['choices']}
        self.assertEqual(choices['backend']['name'], 'FastAPI')
        self.assertEqual(choices['backend']['source'], 'user_required')

    def test_role_and_skill_mapping(self):
        result = identify_roles('mobile commerce', ['Flutter', 'Django'], ['Payments'])
        names = {role['name'] for role in result['roles']}
        self.assertIn('Mobile Engineer', names)
        self.assertIn('Backend Engineer', names)

    def test_milestones_have_ordered_dependencies(self):
        roadmap = generate_roadmap(['Authentication', 'Payments'], deadline_weeks=16)
        self.assertEqual(roadmap['milestones'][0]['dependencies'], [])
        self.assertEqual(
            roadmap['milestones'][1]['dependencies'],
            [roadmap['milestones'][0]['name']],
        )

    def test_complete_planning_evidence_combines_validated_tools(self):
        tool = full_plan_tools()[0]
        output = tool.invoke({
            'description': 'Plan a Flutter food delivery app with payments in four months.'
        })
        self.assertEqual(output['roadmap']['estimated_total_weeks'], 16.0)
        self.assertEqual(output['technology_stack']['choices'][0]['name'], 'Flutter')
        self.assertFalse(output['persistence_performed'])

    def test_company_taxonomy_marks_existing_skill(self):
        User = get_user_model()
        owner = User.objects.create_user(username='planning-owner')
        company = Company.objects.create(created_by_user=owner, name='Planning Co')
        CompanyUser.objects.create(company=company, user=owner, role=CompanyUser.Role.OWNER)
        skill = Skill.objects.create(company=company, name='Python', category='Backend')
        context = database_context(owner, company.id, read_only=True)
        tool = {item.name: item for item in project_tools(context)}['identify_project_roles_and_skills']
        output = tool.invoke({
            'project_type': 'web app', 'technologies': ['Django'], 'features': [],
        })
        python = next(item for item in output['skills'] if item['name'] == 'Python')
        self.assertEqual(python['taxonomy_status'], 'existing')
        self.assertEqual(python['existing_skill_id'], skill.id)


class ProjectAgentTests(TestCase):
    def test_prompt_is_external_and_defines_boundaries(self):
        prompt = load_system_prompt()
        self.assertIn('Agentix Project Planning Specialist', prompt)
        self.assertIn('Never fabricate an ID', prompt)
        self.assertIn('YYYY-MM-DD', prompt)

    def test_all_planning_tools_are_registered(self):
        names = {tool.name for tool in project_tools()}
        self.assertEqual(names, {
            'analyze_project_description', 'prepare_project_specification',
            'recommend_technology_stack', 'compare_frameworks',
            'identify_project_roles_and_skills', 'generate_project_roadmap',
            'create_complete_planning_evidence',
        })

    @patch('orchestrator.agents.project.agent.get_llm', return_value=object())
    @patch('orchestrator.agents.project.agent.create_agent', return_value=object())
    def test_agent_initialization_uses_structured_response(self, create_agent, get_llm):
        build_project_agent()
        kwargs = create_agent.call_args.kwargs
        self.assertEqual(kwargs['name'], 'project_planning_agent')
        self.assertEqual(len(kwargs['tools']), 7)
        self.assertNotIn('response_format', kwargs)

    def test_execution_returns_validated_structured_output(self):
        structured = ProjectAgentOutput(
            outcome='specification', response='Plan ready.',
            specification=specification_data(),
        )
        fake = Mock()
        fake.invoke.return_value = {
            'messages': [AIMessage(content='Plan ready.')],
            'structured_response': structured,
        }
        result = execute_project_task(None, 'Plan it', agent=fake)
        self.assertTrue(result.success)
        self.assertEqual(result.structured_output.specification.name, 'Commerce Project')

    def test_tool_results_are_correlated_by_tool_call_id(self):
        structured = ProjectAgentOutput(
            outcome='specification', response='Plan ready.',
            specification=specification_data(),
        )
        fake = Mock()
        fake.invoke.return_value = {
            'messages': [
                AIMessage(content='', tool_calls=[
                    {'id': 'call-a', 'name': 'analyze_project_description', 'args': {'description': 'A'}},
                    {'id': 'call-b', 'name': 'recommend_technology_stack', 'args': {'requirements': 'B'}},
                ]),
                ToolMessage(name='recommend_technology_stack', tool_call_id='call-b',
                            content='{"value": "B"}'),
                ToolMessage(name='analyze_project_description', tool_call_id='call-a',
                            content='{"value": "A"}'),
            ],
            'structured_response': structured,
        }
        result = execute_project_task(None, 'Plan it', agent=fake)
        executions = {(item.name, item.input.get('description')): item.output
                      for item in result.tool_executions}
        self.assertEqual(executions[('analyze_project_description', 'A')]['value'], 'A')
        executions = {(item.name, item.input.get('requirements')): item.output
                      for item in result.tool_executions}
        self.assertEqual(executions[('recommend_technology_stack', 'B')]['value'], 'B')

    def test_conversation_continuity_and_revision_are_forwarded(self):
        structured = ProjectAgentOutput(
            outcome='specification', response='Updated to FastAPI.',
            specification=specification_data(),
        )
        fake = Mock()
        fake.invoke.return_value = {'messages': [], 'structured_response': structured}
        conversation = [
            {'role': 'user', 'content': 'Use Django and PostgreSQL.'},
            {'role': 'assistant', 'content': 'Noted.'},
        ]
        execute_project_task(None, 'Change Django to FastAPI.', conversation, agent=fake)
        messages = fake.invoke.call_args.args[0]['messages']
        self.assertEqual([message.content for message in messages], [
            'Use Django and PostgreSQL.', 'Noted.', 'Change Django to FastAPI.',
        ])

    def test_invalid_model_output_is_reported(self):
        fake = Mock()
        fake.invoke.return_value = {
            'messages': [AIMessage(content='Invalid')],
            'structured_response': {'outcome': 'specification', 'response': 'Invalid'},
        }
        result = execute_project_task(None, 'Plan it', agent=fake)
        self.assertFalse(result.success)
        self.assertTrue(result.validation_errors)

    def test_unsupported_persistence_request_is_representable(self):
        output = ProjectAgentOutput(
            outcome='unsupported',
            response='Persistence requires an authorized database workflow.',
        )
        self.assertFalse(output.persistence_performed)

    def test_clarification_questions_are_shown_in_answer(self):
        structured = ProjectAgentOutput(
            outcome='clarification', response='Please clarify.',
            clarification={
                'understood_request': 'An application',
                'questions': [{
                    'field': 'users', 'question': 'Who are the primary users?',
                    'impact': 'User scope determines core workflows.', 'essential': True,
                }],
            },
        )
        fake = Mock()
        fake.invoke.return_value = {'messages': [], 'structured_response': structured}
        result = execute_project_task(None, 'Build an app', agent=fake)
        self.assertIn('1. Who are the primary users?', result.answer)

    def test_agent_errors_are_safe_and_reported(self):
        fake = Mock()
        fake.invoke.side_effect = RuntimeError('provider unavailable')
        result = execute_project_task(None, 'Plan it', agent=fake)
        self.assertFalse(result.success)
        self.assertIn('RuntimeError', result.validation_errors[0])
        self.assertEqual(result.model_requests, 1)

    def test_two_stage_validator_returns_typed_output(self):
        draft = Mock()
        draft.invoke.return_value = {
            'messages': [AIMessage(content='Draft plan.')],
        }
        parsed = ProjectAgentOutput(
            outcome='specification', response='Validated plan.',
            specification=specification_data(),
        )
        validator = Mock()
        validator.invoke.return_value = {
            'raw': AIMessage(content='{}'),
            'parsed': parsed,
            'parsing_error': None,
        }
        result = execute_project_task(
            None, 'Plan it', agent=draft, structured_model=validator,
        )
        self.assertTrue(result.success)
        self.assertEqual(result.answer, 'Validated plan.')
        self.assertEqual(result.model_requests, 1)

    def test_wrapped_and_bare_specification_outputs_are_supported(self):
        payload = {'outcome': 'specification', 'response': 'Ready', 'specification': specification_data()}
        for output in (payload, {'parsed': payload, 'parsing_error': None}):
            with self.subTest(wrapped='parsed' in output):
                draft = Mock()
                draft.invoke.return_value = {'messages': []}
                synthesis = Mock()
                synthesis.invoke.return_value = output
                result = execute_project_task(None, 'Draft a store', agent=draft, structured_model=synthesis)
                self.assertTrue(result.success)
                self.assertEqual(result.structured_output.specification.name, 'Commerce Project')

    def test_nested_model_and_strict_scalar_errors_include_safe_types(self):
        spec = specification_data()
        spec['technology_stack'] = ['private-technology-value']
        spec['milestones'][0]['estimated_duration_weeks'] = '4'
        draft = Mock()
        draft.invoke.return_value = {'messages': []}
        synthesis = Mock()
        synthesis.invoke.return_value = {
            'parsed': {'outcome': 'specification', 'response': 'Ready', 'specification': spec},
            'raw': AIMessage(content='', response_metadata={'finish_reason': 'stop'}),
        }
        with self.assertLogs('orchestrator.agents.project.agent', 'WARNING') as logs:
            result = execute_project_task(None, 'Draft a store', agent=draft, structured_model=synthesis)
        self.assertFalse(result.success)
        self.assertIsNone(result.structured_output)
        self.assertEqual(result.finish_reason, 'stop')
        self.assertEqual([issue.model_dump() for issue in result.validation_issues], [
            {'loc': ['specification', 'technology_stack'], 'type': 'model_type',
             'expected_type': 'TechnologyStack', 'received_type': 'array'},
            {'loc': ['specification', 'milestones', 0, 'estimated_duration_weeks'], 'type': 'float_type',
             'expected_type': 'number', 'received_type': 'string'},
        ])
        self.assertNotIn('private-technology-value', str(logs.output))

    def test_unknown_output_keys_are_redacted_in_diagnostics(self):
        spec = specification_data()
        spec['private-field-name'] = 'private value'
        draft = Mock()
        draft.invoke.return_value = {'messages': []}
        synthesis = Mock()
        synthesis.invoke.return_value = {
            'parsed': {'outcome': 'specification', 'response': 'Ready', 'specification': spec},
        }
        result = execute_project_task(None, 'Draft a store', agent=draft, structured_model=synthesis)
        self.assertFalse(result.success)
        self.assertEqual(result.validation_issues[0].loc, ['specification', '<unknown>'])
        self.assertNotIn('private-field-name', str(result.validation_issues))
