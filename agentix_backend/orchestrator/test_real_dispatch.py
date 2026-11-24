from dataclasses import replace
from threading import Barrier

import httpx
from groq import APIStatusError
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase, TransactionTestCase
from langchain_core.exceptions import OutputParserException
from pydantic import ValidationError
from langchain_core.messages import AIMessage

from orchestrator.agents.matching import test_matching
from orchestrator.agents.project.schemas import ProjectAgentOutput, ProjectAgentResult
from orchestrator.agents.project.tests.test_project_agent import specification_data
from orchestrator.agents.research.schemas import ResearchResult
from companies.models import Company, CompanyUser
from orchestrator.core.agent_registry import Agent, Capability, PlanningInput, specialist_registry
from orchestrator.core.execution_context import ExecutionContext
from orchestrator.core.specialist_dispatch import DispatchFailure, dispatch_real
from orchestrator.graph.builder import build_integrated_graph
from projects.models import Project, ProjectRequirement
from workforce.models import Department, Employee, EmployeeAIProfile, EmployeeSkill, Skill


def task(identifier, capability, inputs, *, depends_on=(), references=None):
    return {'task_id': identifier, 'capability': capability, 'description': 'Fixture task',
            'inputs': inputs, 'depends_on': list(depends_on), 'references': references or {}}


def mock_planner(*tasks):
    return Mock(invoke=Mock(return_value={'parsed': {
        'outcome': 'plan', 'response': 'Fixture plan',
        'plan': {'goal': 'Fixture workflow', 'tasks': list(tasks)},
    }}))


def research_result(question):
    url = 'https://example.org/'
    return ResearchResult(
        question=question, status='ok', model_responses=2, tokens=45,
        summary={'answer': 'Fixture', 'findings': [{'claim': 'Fixture', 'urls': [url]}]},
        sources=[{'title': 'Fixture', 'url': url, 'excerpt': 'Fixture', 'provider': 'webpage'}],
        tool_results=[{'requests': 1, 'credits': 1}],
    )


class RealDispatchTests(SimpleTestCase):
    context = ExecutionContext(7, 9, frozenset({'project.plan', 'research.search'}))
    registry = specialist_registry()

    @patch('orchestrator.core.specialist_dispatch._read_context')
    @patch('orchestrator.agents.project.agent.build_project_output_model')
    @patch('orchestrator.agents.project.agent.build_project_agent')
    def test_project_agent_specification_reaches_supervisor(self, build, structured, read_context):
        usage = {'input_tokens': 7, 'output_tokens': 3, 'total_tokens': 10}
        build.return_value.invoke.return_value = {
            'messages': [AIMessage(content='Planning evidence', usage_metadata=usage)],
        }
        structured.return_value.invoke.return_value = {
            'raw': AIMessage(content='', usage_metadata=usage), 'parsing_error': None,
            'parsed': ProjectAgentOutput(
                outcome='specification', response='Plan ready', specification=specification_data(),
            ),
        }
        graph = build_integrated_graph(
            self.registry, mode='real',
            planner=mock_planner(task('draft', 'project.plan', {'task': 'Plan a store'})),
        )
        result = graph.invoke({'request': 'Plan a store'}, context=self.context)
        completed = result['results']['draft']
        self.assertEqual(completed.status, 'done')
        self.assertEqual(completed.output['structured_output']['specification']['name'], 'Commerce Project')
        self.assertFalse(completed.output['structured_output']['persistence_performed'])
        self.assertEqual(completed.metadata['model_requests'], 2)
        build.assert_called_once_with(None, model_name=None)

    @patch('orchestrator.core.specialist_dispatch._read_context')
    @patch('orchestrator.agents.project.agent.build_project_output_model')
    @patch('orchestrator.agents.project.agent.build_project_agent')
    def test_project_synthesis_rate_limit_is_sanitized(self, build, structured, read_context):
        build.return_value.invoke.return_value = {
            'messages': [AIMessage(content='Preliminary plan')],
        }
        failure = RuntimeError('private provider payload')
        failure.status_code = 429
        structured.return_value.invoke.side_effect = failure
        graph = build_integrated_graph(
            self.registry, mode='real',
            planner=mock_planner(task('draft', 'project.plan', {'task': 'Plan a store'})),
        )
        result = graph.invoke({'request': 'Plan a store'}, context=self.context)['results']['draft']
        self.assertEqual(result.error.code, 'rate_limited')
        self.assertEqual(result.metadata['failure_stage'], 'structured_synthesis')
        self.assertIsNone(result.output)
        self.assertNotIn('private provider payload', str(result))
        messages = structured.return_value.invoke.call_args.args[0]
        self.assertIn('Preliminary plan', messages[-2].content)

    @patch('orchestrator.core.specialist_dispatch._read_context')
    @patch('orchestrator.agents.project.agent.build_project_output_model')
    @patch('orchestrator.agents.project.agent.build_project_agent')
    def test_missing_project_fields_are_never_fabricated(self, build, structured, read_context):
        build.return_value.invoke.return_value = {'messages': []}
        structured.return_value.invoke.return_value = {
            'parsed': {'outcome': 'specification', 'response': 'Draft',
                       'specification': {'name': 'Incomplete'}},
        }
        graph = build_integrated_graph(
            self.registry, mode='real',
            planner=mock_planner(task('draft', 'project.plan', {'task': 'Plan a store'})),
        )
        result = graph.invoke({'request': 'Plan a store'}, context=self.context)['results']['draft']
        self.assertEqual(result.error.code, 'project_planning_failed')
        self.assertEqual(result.metadata['failure_stage'], 'output_validation')
        self.assertIsNone(result.output)

    @patch('orchestrator.core.specialist_dispatch._read_context')
    @patch('orchestrator.agents.project.agent.build_project_output_model')
    @patch('orchestrator.agents.project.agent.build_project_agent')
    def test_project_parser_failure_preserves_only_safe_diagnostics(self, build, structured, read_context):
        from orchestrator.graph.console_contract import execution_state

        build.return_value.invoke.return_value = {
            'messages': [AIMessage(content='Draft')],
        }
        try:
            ProjectAgentOutput.model_validate({
                'outcome': 'specification', 'response': 'Draft',
                'specification': {'name': 'private model content'},
            })
        except ValidationError as exc:
            parser_error = OutputParserException('private provider reply')
            parser_error.__cause__ = exc
        structured.return_value.invoke.return_value = {
            'raw': AIMessage(content='private model content', response_metadata={'finish_reason': 'length'}),
            'parsed': None, 'parsing_error': parser_error,
        }
        graph = build_integrated_graph(
            self.registry, mode='real',
            planner=mock_planner(task('spec_1', 'project.plan', {'task': 'Plan a Flutter store'})),
        )
        state = graph.invoke({'request': 'Plan a Flutter store'}, context=self.context)
        task_result = state['results']['spec_1']
        self.assertIsNone(task_result.output)
        self.assertEqual(task_result.metadata['validation_codes'], ['missing'])
        self.assertEqual(task_result.metadata['finish_reason'], 'length')
        self.assertNotIn('private', str(task_result))
        error = execution_state(state, False, 'real')['plan']['tasks'][0]['error']
        issues = error.pop('validation_issues')
        self.assertEqual(issues[0], {
            'loc': ['specification', 'description'], 'type': 'missing',
            'expected_type': 'string', 'received_type': 'missing',
        })
        self.assertEqual(error, {
            'code': 'project_planning_failed', 'stage': 'output_validation',
            'validation_codes': ['missing'], 'finish_reason': 'length',
        })

    @patch('orchestrator.agents.project.agent.build_project_output_model')
    @patch('orchestrator.agents.project.agent.build_project_agent')
    def test_project_revalidates_already_typed_output(self, build, structured):
        from orchestrator.agents.project.agent import execute_project_task

        build.return_value.invoke.return_value = {'messages': []}
        structured.return_value.invoke.return_value = {'parsed': ProjectAgentOutput.model_construct(
            outcome='specification', response='Draft without required specification',
        )}
        result = execute_project_task(None, 'Draft a Flutter store')
        self.assertFalse(result.success)
        self.assertIsNone(result.structured_output)
        self.assertEqual(result.failure_stage, 'output_validation')

    @patch('orchestrator.core.specialist_dispatch._read_context')
    @patch('orchestrator.core.specialist_dispatch.execute_research')
    @patch('orchestrator.agents.project.agent.build_project_output_model')
    @patch('orchestrator.agents.project.agent.build_project_agent')
    def test_parallel_groq_413_limit_preserves_research(self, draft, synthesis, research, read_context):
        from orchestrator.graph.console_contract import execution_state

        barrier = Barrier(2, timeout=5)
        question = 'Research Flutter architecture'
        draft.return_value.invoke.return_value = {
            'messages': [AIMessage(content='Draft')],
        }

        def fail_synthesis(messages):
            barrier.wait()
            response = httpx.Response(413, request=httpx.Request('POST', 'https://example.invalid/'))
            raise APIStatusError('private provider payload', response=response, body={
                'error': {'code': 'rate_limit_exceeded', 'message': 'private provider payload'},
            })

        def finish_research(question):
            barrier.wait()
            return research_result(question)

        research.side_effect = finish_research
        synthesis.return_value.invoke.side_effect = fail_synthesis
        graph = build_integrated_graph(self.registry, mode='real', planner=mock_planner(
            task('research', 'research.search', {'question': question}),
            task('draft', 'project.plan', {'task': 'Draft a Flutter store without saving.'}),
        ))
        state = graph.invoke({'request': 'Research and plan independently'}, context=self.context)
        self.assertEqual(state['execution_summary'].status, 'partial')
        project = state['results']['draft']
        self.assertEqual(project.error.code, 'rate_limited')
        self.assertEqual(project.metadata['failure_stage'], 'structured_synthesis')
        self.assertNotIn('finish_reason', project.metadata)
        self.assertIsNone(project.output)
        self.assertEqual(state['results']['research'].output['sources'][0]['url'], 'https://example.org/')
        projected = execution_state(state, False, 'real')
        self.assertEqual(projected['plan']['tasks'][1]['error'], {
            'code': 'rate_limited', 'stage': 'structured_synthesis',
            'provider_status': 413, 'provider_code': 'rate_limit_exceeded',
        })
        self.assertNotIn('private provider payload', str(projected))
        synthesis.return_value.invoke.assert_called_once()
        research.assert_called_once_with(question)

    @patch('orchestrator.core.specialist_dispatch._read_context')
    @patch('orchestrator.core.specialist_dispatch.execute_research')
    def test_research_failure_preserves_safe_diagnostics(self, execute, read_context):
        execute.return_value = ResearchResult(
            question='Fixture', status='error', errors=['ungrounded_citation', 'private raw value'],
            tool_results=[{'name': 'search_web', 'requests': 1, 'credits': 1}],
        )
        graph = build_integrated_graph(
            self.registry, mode='real',
            planner=mock_planner(task('search', 'research.search', {'question': 'Fixture'})),
        )
        result = graph.invoke({'request': 'Research'}, context=self.context)['results']['search']
        self.assertEqual(result.error.code, 'research_failed')
        self.assertEqual(result.metadata['research_errors'], ['ungrounded_citation'])
        self.assertEqual(result.metadata['search_credits'], 1)
        self.assertIsNone(result.output)

    @patch('orchestrator.core.specialist_dispatch.database_context')
    @patch('orchestrator.core.specialist_dispatch.get_user_model')
    @patch('orchestrator.core.specialist_dispatch.execute_research')
    def test_trusted_identity_and_research_usage(self, execute, user_model, db_context):
        execute.return_value = research_result('Fixture')
        _, cap = self.registry.lookup('research.search')
        output, metadata = dispatch_real(
            self.registry, cap.name, cap.input_schema(question='Fixture'), self.context,
        )
        user_model.return_value.objects.filter.assert_called_once_with(pk=7, is_active=True)
        db_context.assert_called_once_with(
            user_model.return_value.objects.filter.return_value.first.return_value,
            9, read_only=True,
        )
        execute.assert_called_once_with('Fixture')
        self.assertEqual(output.status, 'ok')
        self.assertEqual(metadata['total_tokens'], 45)
        self.assertEqual(metadata['search_credits'], 1)

    @patch('orchestrator.core.specialist_dispatch._read_context', side_effect=PermissionDenied)
    @patch('orchestrator.core.specialist_dispatch.execute_research')
    def test_revoked_membership_never_calls_agent(self, execute, read_context):
        _, cap = self.registry.lookup('research.search')
        with self.assertRaises(DispatchFailure) as failure:
            dispatch_real(self.registry, cap.name, cap.input_schema(question='Fixture'), self.context)
        self.assertEqual(failure.exception.error.code, 'unauthorized')
        execute.assert_not_called()

    @patch('orchestrator.core.specialist_dispatch._read_context')
    @patch('orchestrator.core.specialist_dispatch.execute_project_task')
    def test_project_clarification_is_not_successful_execution(self, execute, read_context):
        execute.return_value = ProjectAgentResult(
            answer='What scope?', structured_output=ProjectAgentOutput(
                outcome='clarification', response='What scope?',
                clarification={'understood_request': 'Plan', 'questions': [{
                    'field': 'scope', 'question': 'What scope?', 'impact': 'Required', 'essential': True,
                }]},
            ), model_calls=1,
        )
        _, cap = self.registry.lookup('project.plan')
        with self.assertRaises(DispatchFailure) as failure:
            dispatch_real(self.registry, cap.name, cap.input_schema(task='Plan'), self.context)
        execute.assert_called_once_with(None, 'Plan')
        self.assertEqual(failure.exception.error.code, 'clarification')

    @patch('orchestrator.core.specialist_dispatch._read_context')
    @patch('orchestrator.core.specialist_dispatch.execute_research')
    def test_real_and_mock_modes_do_not_fallback(self, research, read_context):
        mock = Mock(return_value=research_result('Fixture'))
        registry = specialist_registry({'research.search': mock})
        planned = task('a', 'research.search', {'question': 'Fixture'})
        research.side_effect = TimeoutError('private provider details')
        real = build_integrated_graph(registry, planner=mock_planner(planned), mode='real')
        result = real.invoke({'request': 'Research'}, context=self.context)
        self.assertEqual(result['results']['a'].error.code, 'specialist_timeout')
        self.assertNotIn('private provider details', result['final_response'])
        mock.assert_not_called()
        mocked = build_integrated_graph(registry, planner=mock_planner(planned))
        result = mocked.invoke({'request': 'Research'}, context=self.context)
        self.assertEqual(result['results']['a'].status, 'done')
        mock.assert_called_once()
        research.assert_called_once()

    @patch('orchestrator.core.specialist_dispatch._read_context')
    @patch('orchestrator.core.specialist_dispatch.execute_research')
    def test_bad_output_blocks_dependent_while_independent_branch_runs(self, execute, read_context):
        barrier = Barrier(2, timeout=5)

        def research(question):
            barrier.wait()
            return {'status': 'ok'} if question == 'Invalid' else research_result(question)

        execute.side_effect = research
        graph = build_integrated_graph(
            self.registry, mode='real', planner=mock_planner(
                task('bad', 'research.search', {'question': 'Invalid'}),
                task('good', 'research.search', {'question': 'Good'}),
                task('child', 'research.search', {'question': 'Child'}, depends_on=['bad']),
            ),
        )
        result = graph.invoke({'request': 'Research'}, context=self.context)
        self.assertEqual(result['task_statuses'], {'bad': 'failed', 'good': 'done', 'child': 'blocked'})
        self.assertEqual(result['results']['bad'].error.code, 'invalid_task_output')
        self.assertEqual(result['execution_summary'].status, 'partial')
        self.assertEqual(execute.call_count, 2)

    @patch('orchestrator.core.specialist_dispatch._read_context')
    def test_arbitrary_registered_operation_rejected_before_all_dispatch(self, read_context):
        registry = specialist_registry()
        registry.register(Agent('other', 'Other', 'Fixture', (
            Capability('other.write', PlanningInput, ProjectAgentResult),
        )))
        context = ExecutionContext(7, 9, frozenset({'other.write', 'project.plan'}))
        planner = mock_planner(task('a', 'project.plan', {'task': 'Fixture'}),
                               task('b', 'other.write', {'task': 'Fixture'}))
        graph = build_integrated_graph(registry, mode='real', planner=planner)
        with self.assertLogs('orchestrator.core.plan_validator', level='WARNING') as captured:
            result = graph.invoke({'request': 'Fixture'}, context=context)
        self.assertEqual(result['decision'].outcome, 'planning_error')
        self.assertEqual(result['errors'][0].message, 'The proposed plan did not pass validation.')
        self.assertEqual(
            captured.records[-1].plan_validation['error_code'],
            'real_adapter_missing',
        )
        self.assertNotIn('other.write', planner.invoke.call_args.args[0][-2].content)
        read_context.assert_not_called()

    @patch('orchestrator.core.specialist_dispatch._read_context')
    @patch('orchestrator.core.specialist_dispatch.execute_research', side_effect=research_result)
    def test_real_dispatch_uses_validated_reference(self, execute, read_context):
        graph = build_integrated_graph(
            self.registry, mode='real', planner=mock_planner(
                task('source', 'research.search', {'question': 'From predecessor'}),
                task('followup', 'research.search', {}, depends_on=['source'],
                     references={'question': {'task_id': 'source', 'field': 'question'}}),
            ),
        )
        result = graph.invoke({'request': 'Fixture'}, context=self.context)
        self.assertEqual(result['results']['followup'].output['question'], 'From predecessor')
        self.assertEqual([call.args[0] for call in execute.call_args_list], ['From predecessor'] * 2)


class ScopedDataDispatchTests(TransactionTestCase):
    def setUp(self):
        self._fixture_user_ids = []
        self._fixture_company_ids = []
        self._fixture_membership_ids = []
        self._fixture_project_ids = []
        self._fixture_requirement_ids = []
        self._fixture_employee_ids = []
        self._fixture_profile_ids = []
        self._fixture_skill_ids = []
        self._fixture_assignment_ids = []
        self._fixture_department_ids = []
        self.addCleanup(self._cleanup_scoped_fixtures)
        test_matching.MatchingTests.setUpTestData.__func__(self)
        self._fixture_user_ids = [
            self.context.user.pk,
            self.foreign.company.created_by_user_id,
        ]
        self._fixture_company_ids = [
            self.context.company.pk,
            self.foreign.company_id,
        ]
        self._fixture_membership_ids = list(
            CompanyUser.objects.filter(
                company_id__in=self._fixture_company_ids,
            ).values_list('pk', flat=True)
        )
        self._fixture_project_ids = [self.project.pk, self.foreign.pk]
        self._fixture_requirement_ids = list(
            ProjectRequirement.objects.filter(
                project_id__in=self._fixture_project_ids,
            ).values_list('pk', flat=True)
        )
        self._fixture_employee_ids = list(
            Employee.objects.filter(
                department__company_id__in=self._fixture_company_ids,
            ).values_list('pk', flat=True)
        )
        self._fixture_profile_ids = list(
            EmployeeAIProfile.objects.filter(
                employee_id__in=self._fixture_employee_ids,
            ).values_list('pk', flat=True)
        )
        self._fixture_assignment_ids = list(
            EmployeeSkill.objects.filter(
                employee_id__in=self._fixture_employee_ids,
            ).values_list('pk', flat=True)
        )
        self._fixture_skill_ids = list(
            Skill.objects.filter(company_id__in=self._fixture_company_ids)
            .values_list('pk', flat=True)
        )
        self._fixture_department_ids = list(
            Department.objects.filter(company_id__in=self._fixture_company_ids)
            .values_list('pk', flat=True)
        )
        self.runtime = ExecutionContext.from_django(
            self.context, allowed_capabilities={'database.get_project', 'matching.rank'},
            permissions={'projects.read', 'workforce.read'},
        )
        self.runtime = replace(
            self.runtime,
            project_deadline=self.project.deadline.isoformat(),
        )

    def _cleanup_scoped_fixtures(self):
        ProjectRequirement.objects.filter(pk__in=self._fixture_requirement_ids).delete()
        Project.objects.filter(pk__in=self._fixture_project_ids).delete()
        EmployeeSkill.objects.filter(pk__in=self._fixture_assignment_ids).delete()
        EmployeeAIProfile.objects.filter(pk__in=self._fixture_profile_ids).delete()
        Employee.objects.filter(pk__in=self._fixture_employee_ids).delete()
        Department.objects.filter(pk__in=self._fixture_department_ids).delete()
        Skill.objects.filter(pk__in=self._fixture_skill_ids).delete()
        CompanyUser.objects.filter(pk__in=self._fixture_membership_ids).delete()
        Company.objects.filter(pk__in=self._fixture_company_ids).delete()
        get_user_model().objects.filter(pk__in=self._fixture_user_ids).delete()

    def _fixture_teardown(self):
        self._cleanup_scoped_fixtures()

    def run_project(self, project_id):
        graph = build_integrated_graph(
            specialist_registry(), mode='real', planner=mock_planner(
                task('lookup', 'database.get_project', {'project_id': project_id}),
                task('rank', 'matching.rank', {'project_id': project_id, 'top_n': 2},
                     depends_on=['lookup']),
            ),
        )
        return graph.invoke({'request': 'Look up the project and rank employees.', 'project_id': project_id},
                            context=self.runtime)

    def test_existing_project_and_real_xgboost_rank(self):
        result = self.run_project(self.project.pk)
        self.assertEqual(result['task_statuses'], {'lookup': 'done', 'rank': 'done'})
        output = result['results']['rank'].output['structured_output']
        self.assertEqual(output['metadata']['project_id'], self.project.pk)
        self.assertEqual(len(output['candidates']), 2)
        self.assertEqual(result['results']['lookup'].output['execution_results'][0]['data']['project']['id'],
                         self.project.pk)
        self.assertEqual([candidate['employee_id'] for candidate in output['candidates']],
                         [self.employees[1].pk, self.employees[0].pk])
        self.assertGreater(output['candidates'][0]['model_score'], output['candidates'][1]['model_score'])

    def test_foreign_project_is_not_found_and_matching_is_blocked(self):
        result = self.run_project(self.foreign.pk)
        self.assertEqual(result['results']['lookup'].error.code, 'not_found')
        self.assertIsNone(result['results']['lookup'].output)
        self.assertEqual(result['results']['rank'].status, 'blocked')
