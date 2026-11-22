from datetime import date, timedelta
from unittest.mock import Mock, patch
import json

from langchain_core.messages import AIMessage, ToolMessage

from django.contrib.auth import get_user_model
from django.test import TestCase
from pydantic import ValidationError

from companies.models import Company, CompanyUser
from projects.models import Project, ProjectRequirement
from workforce.models import Department, Employee, EmployeeAIProfile, EmployeeSkill, Skill
from orchestrator.core.permissions import database_context
from orchestrator.ml_engine.loader import FEATURES, load_model
from orchestrator.ml_engine.feature_extractor import extract_features
from orchestrator.ml_engine.predictor import predict

from .agent import build_matching_agent, execute_matching_task, matching_tools
from .schemas import MatchingResponse


class MatchingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = get_user_model().objects.create_user(username='match-stage-one')
        company = Company.objects.create(created_by_user=user, name='Matching fixture')
        CompanyUser.objects.create(company=company, user=user)
        cls.context = database_context(user, company.pk, read_only=True)
        department = Department.objects.create(company=company, name='Engineering')
        cls.project = Project.objects.create(company=company, name='Fixture',
                                             deadline=date.today() + timedelta(days=30))
        _, info = load_model()
        title = info['categories']['job_title'][0]
        ProjectRequirement.objects.create(project=cls.project, requirement='Backend',
                                          required_skills='Python,Django', required_roles=title)
        skill = Skill.objects.create(company=company, name='Python')
        cls.employees = []
        for index, status in enumerate(['available', 'available', 'unavailable']):
            employee = Employee.objects.create(department=department, employee_code=str(index),
                                               first_name='Fixture', last_name=str(index))
            EmployeeAIProfile.objects.create(employee=employee, job_title=title,
                                             availability_status=status, experience_years=4 + index,
                                             performance_score=80, previous_project_score=75,
                                             completed_projects=3, current_workload=20)
            EmployeeSkill.objects.create(employee=employee, skill=skill,
                                         proficiency=4, years_experience=3)
            cls.employees.append(employee)
        other_user = get_user_model().objects.create_user(username='match-other')
        other = Company.objects.create(created_by_user=other_user, name='Other')
        cls.foreign = Project.objects.create(company=other, name='Foreign')
        other_department = Department.objects.create(company=other, name='Foreign')
        Employee.objects.create(department=other_department, employee_code='other',
                                first_name='Foreign', last_name='Fixture')

    def setUp(self):
        self.tools = {tool.name: tool for tool in matching_tools(self.context)}

    @patch('orchestrator.agents.matching.agent.create_agent')
    @patch('orchestrator.agents.matching.agent.get_llm')
    def test_initialization(self, factory, create):
        build_matching_agent(self.context)
        factory.assert_called_once_with(None)
        self.assertIn('Agentix Employee Matching Specialist', create.call_args.kwargs['system_prompt'])
        self.assertEqual(len(create.call_args.kwargs['tools']), 2)

    def test_project_scope(self):
        for project_id in (self.foreign.pk, 999999999):
            output = self.tools['rank_project_employees'].invoke({'project_id': project_id})
            self.assertFalse(MatchingResponse.model_validate(output).success)
        context = self.tools['get_project_matching_context'].invoke({'project_id': self.project.pk})
        self.assertEqual(context['project']['requirements'][0]['required_skills'], 'Python,Django')

    @patch('orchestrator.tools.matching.context_tools.BATCH_SIZE', 1)
    def test_real_predictions_across_batches(self):
        result = MatchingResponse.model_validate(self.tools['rank_project_employees'].invoke(
            {'project_id': self.project.pk, 'available_only': True, 'skill_filter': [' Python ']}))
        self.assertEqual(result.metadata.candidate_count, 3)
        self.assertEqual(result.metadata.eligible_count, 2)
        self.assertEqual(result.metadata.ranked_count, 2)
        model, info = load_model()
        expected = []
        for employee in self.employees[:2]:
            features, _ = extract_features(employee, self.project, date.today())
            self.assertEqual(list(features), FEATURES)
            self.assertEqual(len(features), 16)
            score = predict(model, [features], info['categories'])[0]['positive_probability']
            expected.append((employee.pk, score))
        expected.sort(key=lambda row: (-row[1], row[0]))
        self.assertEqual([(row.employee_id, row.model_score) for row in result.candidates], expected)
        self.assertEqual([row.rank for row in result.candidates], [1, 2])
        print('Independent fixture scores:', [score for _, score in expected])

    def test_missing_features_and_empty_ranking(self):
        EmployeeAIProfile.objects.filter(employee__in=self.employees[:2]).update(performance_score=None)
        result = self.tools['rank_project_employees'].invoke({'project_id': self.project.pk})
        self.assertEqual(result['candidates'], [])
        self.assertEqual(result['metadata']['ranked_count'], 0)
        self.assertIn('performance_score', str(result['exclusions']))

    def test_invalid_response(self):
        with self.assertRaises(ValidationError):
            MatchingResponse.model_validate({'success': True, 'answer': 'x', 'unknown': True})

    def test_follow_up_uses_verified_ranking_without_new_tool_call(self):
        previous = MatchingResponse.model_validate(self.tools['rank_project_employees'].invoke(
            {'project_id': self.project.pk, 'top_n': 2}))
        runtime = Mock()
        runtime.invoke.return_value = {'messages': [AIMessage(content='Invented score 999.')]}
        result = execute_matching_task(self.context, 'Why was the first employee ranked higher?',
                                       agent=runtime, last_matching=previous)
        self.assertTrue(result.success)
        self.assertEqual(result.structured_output.candidates, previous.candidates)
        self.assertIn('Required-skill overlap: 50.0%', result.answer)
        self.assertIn('do not establish what caused', result.answer)
        self.assertNotIn('999', result.answer)
        runtime.invoke.return_value['messages'].append(ToolMessage(
            content=previous.model_dump_json(), name='rank_project_employees', tool_call_id='2',
        ))
        repeated = execute_matching_task(self.context, 'Why was the first employee ranked higher?',
                                         agent=runtime, last_matching=previous)
        self.assertEqual(repeated.answer, result.answer)

    def test_invalid_project_lookup_preserves_not_found(self):
        runtime = Mock()
        lookup = self.tools['get_project_matching_context'].invoke({'project_id': 999999999})
        runtime.invoke.return_value = {'messages': [
            ToolMessage(content=json.dumps(lookup), name='get_project_matching_context', tool_call_id='1'),
        ]}
        result = execute_matching_task(self.context, 'Find employees for project 999999999.', agent=runtime)
        self.assertEqual(result.structured_output.error, 'not_found')
        self.assertEqual(result.structured_output.candidates, [])
        self.assertIn('Project not found', result.answer)
