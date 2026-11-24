import json
from datetime import date
from unittest.mock import Mock

from django.test import SimpleTestCase
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

from orchestrator.agents.project.schemas import ProjectAgentOutput, ProjectAgentResult
from orchestrator.core.agent_registry import specialist_registry
from orchestrator.core.execution_context import ExecutionContext
from orchestrator.core.llm_factory import LLMProviderError
from orchestrator.core.plan_schemas import ExecutionPlan, PlannerDecision, TaskResult
from orchestrator.core.plan_validator import PlanLimits
from orchestrator.core.specialist_dispatch import validate_real_plan
from orchestrator.graph.builder import build_planning_graph
from orchestrator.graph.nodes import resolve_inputs
from orchestrator.graph.planner import _bind_deadline_inputs


def task(task_id, capability, inputs, *, depends_on=(), references=None):
    return dict(task_id=task_id, capability=capability, inputs=inputs,
                description='Fixture', depends_on=list(depends_on), references=references or {})


class PlannerTests(SimpleTestCase):
    def setUp(self):
        self.context = ExecutionContext(
            7, 20,
            frozenset({'project.plan', 'research.search', 'database.get_project', 'matching.rank'}),
            frozenset({'projects.read', 'workforce.read'}),
        )
        self.model = Mock()
        self.graph = build_planning_graph(specialist_registry(), planner=self.model)

    def decision(self, outcome, *tasks, request='Fixture request', **state):
        parsed = {'outcome': outcome, 'response': 'Fixture response'}
        if tasks:
            parsed['plan'] = {'goal': 'Fixture goal', 'tasks': list(tasks)}
        self.model.invoke.return_value = {'parsed': parsed, 'parsing_error': None,
                                          'raw': AIMessage(content='')}
        return self.graph.invoke({'request': request, **state}, context=self.context)

    def test_direct_reply(self):
        result = self.decision('direct_response', request='Hello')
        self.assertEqual(result['decision'].outcome, 'direct_response')
        self.assertIsNone(result['plan'])
        self.assertEqual(result['metadata']['mode'], 'planning_only')

    def test_single_agent_plan_does_not_dispatch(self):
        result = self.decision('plan', task('draft', 'project.plan', {'task': 'Plan a store'}))
        self.assertEqual(result['plan'].tasks[0].capability, 'project.plan')
        self.assertIsNone(result['plan'].tasks[0].inputs['explicit_deadline'])
        self.assertEqual(result['results'], {})
        self.model.invoke.assert_called_once()

    def test_explicit_iso_deadline_is_bound_to_project_planning_input(self):
        result = self.decision(
            'plan',
            task('draft', 'project.plan', {'task': 'Plan a store'}),
            request='Plan a store with deadline 2027-01-15.',
        )
        self.assertEqual(
            result['plan'].tasks[0].inputs['explicit_deadline'],
            '2027-01-15',
        )

    def test_explicit_month_name_deadline_is_normalized_to_iso(self):
        result = self.decision(
            'plan',
            task('draft', 'project.plan', {'task': 'Plan the Flutter application'}),
            request=(
                'The project deadline is March 30, 2027.'
            ),
        )
        self.assertEqual(
            result['plan'].tasks[0].inputs['explicit_deadline'],
            '2027-03-30',
        )

    def test_independent_tasks(self):
        result = self.decision('plan', task('draft', 'project.plan', {'task': 'Plan a store'}),
                               task('search', 'research.search', {'question': 'Research Flutter'}))
        self.assertTrue(all(not item.depends_on for item in result['plan'].tasks))

    def test_dependent_plan(self):
        self.context = ExecutionContext(
            7, 20,
            frozenset({'project.plan', 'research.search', 'database.get_project', 'matching.rank'}),
            frozenset({'projects.read', 'workforce.read'}),
            project_deadline='2027-01-15',
        )
        result = self.decision('plan',
                               task('lookup', 'database.get_project', {'project_id': 42}),
                               task('rank', 'matching.rank', {'project_id': 42}, depends_on=['lookup']),
                               project_id=42)
        self.assertEqual(result['plan'].tasks[1].depends_on, ['lookup'])

    def test_mixed_plan_and_typed_reference(self):
        result = self.decision(
            'plan', task('draft', 'project.plan', {'task': 'Plan a store'}),
            task('search', 'research.search', {'question': 'Research Flutter'}),
            task('revise', 'project.plan', {}, depends_on=['draft', 'search'],
                 references={'task': {'task_id': 'draft', 'field': 'answer'}}),
        )
        self.assertEqual(result['plan'].tasks[2].references['task'].field, 'answer')

    def test_clarification_and_unsupported(self):
        for outcome in ('clarification', 'unsupported'):
            with self.subTest(outcome=outcome):
                self.assertEqual(self.decision(outcome)['decision'].outcome, outcome)

    def test_unauthorized_capability_hidden_and_rejected(self):
        self.context = ExecutionContext(7, 20, frozenset({'project.plan', 'matching.rank'}))
        result = self.decision('plan', task('rank', 'matching.rank', {'project_id': 42}), project_id=42)
        self.assertEqual(result['errors'][0].code, 'invalid_plan')
        self.assertIsNone(result['plan'])
        context = self.model.invoke.call_args.args[0][-2].content.split(':\n', 1)[1]
        self.assertEqual([entry['name'] for entry in json.loads(context)['capabilities']], ['project.plan'])

    def test_bad_dependencies_and_references(self):
        for error_code, invalid in (
            (
                'dependency_not_found',
                task('b', 'project.plan', {'task': 'Draft'}, depends_on=['missing']),
            ),
            (
                'reference_output_field_unknown',
                task('b', 'project.plan', {}, depends_on=['a'],
                     references={'task': {'task_id': 'a', 'field': 'missing'}}),
            ),
        ):
            with self.assertLogs('orchestrator.core.plan_validator', level='WARNING') as captured:
                result = self.decision(
                    'plan',
                    task('a', 'project.plan', {'task': 'Draft'}),
                    invalid,
                )
            self.assertEqual(result['errors'][0].code, 'invalid_plan')
            self.assertEqual(result['decision'].response, 'The proposed plan did not pass validation.')
            diagnostic = captured.records[0].plan_validation
            self.assertEqual(diagnostic['error_code'], error_code)
            self.assertEqual(diagnostic['task_ids'], ['b'])
            self.assertEqual(diagnostic['capability'], 'project.plan')

    def test_invented_project_id_forces_clarification(self):
        planned = task('rank', 'matching.rank', {'project_id': 42})
        for project_id in (None, 41):
            result = self.decision('plan', planned, project_id=project_id)
            self.assertEqual(result['decision'].outcome, 'clarification')
            self.assertIsNone(result['plan'])

    def test_matching_without_saved_deadline_requires_clarification(self):
        result = self.decision(
            'plan',
            task('rank', 'matching.rank', {'project_id': 42}),
            request='Recommend employees for this project.',
            project_id=42,
        )
        self.assertEqual(result['decision'].outcome, 'clarification')
        self.assertIn('saved deadline', result['final_response'])
        self.assertIsNone(result['plan'])

    def test_matching_uses_deadline_from_trusted_project_context(self):
        self.context = ExecutionContext(
            7, 20,
            frozenset({'project.plan', 'research.search', 'database.get_project', 'matching.rank'}),
            frozenset({'projects.read', 'workforce.read'}),
            project_deadline='2027-01-15',
        )
        result = self.decision(
            'plan',
            task('rank', 'matching.rank', {'project_id': 42}),
            request='Recommend employees for this project.',
            project_id=42,
        )
        self.assertEqual(result['decision'].outcome, 'plan')

    def test_invalid_requested_deadline_requires_clarification(self):
        result = self.decision(
            'plan',
            task('rank', 'matching.rank', {'project_id': 42}),
            request='Recommend employees with deadline 2027-02-30.',
            project_id=42,
        )
        self.assertEqual(result['decision'].outcome, 'clarification')
        self.assertIn('valid project deadline', result['final_response'])
        self.assertIsNone(result['plan'])

    def test_invalid_month_name_deadline_requires_clarification(self):
        result = self.decision(
            'plan',
            task('rank', 'matching.rank', {'project_id': 42}),
            request='Recommend employees with deadline February 30, 2027.',
            project_id=42,
        )
        self.assertEqual(result['decision'].outcome, 'clarification')
        self.assertIsNone(result['plan'])

    def test_invalid_output_and_schema_invariant(self):
        with self.assertRaises(ValidationError):
            PlannerDecision(outcome='plan', response='No plan')
        self.model.invoke.return_value = {'parsed': None, 'parsing_error': ValueError('private')}
        result = self.graph.invoke({'request': 'Hello'}, context=self.context)
        self.assertEqual(result['errors'][0].code, 'invalid_model_output')
        self.assertNotIn('private', result['final_response'])

    def test_pydantic_plan_failure_logs_location_without_input_values(self):
        invalid_task = task('x' * 81, 'project.plan', {'task': 'secret task text'})
        self.model.invoke.return_value = {
            'parsed': {
                'outcome': 'plan',
                'response': 'Plan prepared.',
                'plan': {'goal': 'Fixture goal', 'tasks': [invalid_task]},
            },
            'parsing_error': None,
            'raw': AIMessage(content=''),
        }
        with self.assertLogs('orchestrator.core.plan_validator', level='WARNING') as captured:
            result = self.graph.invoke({'request': 'Hello'}, context=self.context)
        diagnostic = captured.records[0].plan_validation
        self.assertEqual(diagnostic['error_code'], 'invalid_model_output')
        self.assertEqual(result['metadata']['plan_validation'], diagnostic)
        self.assertEqual(diagnostic['pydantic_errors'], [{
            'loc': ['plan', 'tasks', 0, 'task_id'],
            'type': 'string_too_long',
        }])
        self.assertNotIn('secret task text', captured.output[0])
        self.assertEqual(result['errors'][0].code, 'invalid_model_output')
        self.assertNotIn('secret task text', result['final_response'])

    def test_three_task_project_creation_and_matching_plan_is_valid(self):
        self.context = ExecutionContext(
            7, 20,
            frozenset({'project.plan', 'database.create_project', 'matching.rank'}),
            frozenset({'projects.write', 'projects.read', 'workforce.read', 'approvals.decide'}),
        )
        registry = specialist_registry()
        plan = ExecutionPlan.model_validate({
            'goal': 'Prepare, save, and match the explicitly requested project.',
            'tasks': [
                task('plan_project', 'project.plan', {
                    'task': 'Create a Flutter e-commerce specification.',
                }),
                task(
                    'save_project', 'database.create_project', {'top_n': 5},
                    depends_on=['plan_project'],
                    references={'specification': {
                        'task_id': 'plan_project', 'field': 'structured_output',
                    }},
                ),
                task(
                    'rank_employees', 'matching.rank', {'top_n': 5},
                    depends_on=['save_project'],
                    references={'project_id': {
                        'task_id': 'save_project', 'field': 'project_id',
                    }},
                ),
            ],
        })
        plan = _bind_deadline_inputs(plan, date(2027, 3, 30))
        order = validate_real_plan(plan, registry, self.context, PlanLimits(max_tasks=3))

        self.assertEqual(order, ('plan_project', 'save_project', 'rank_employees'))
        self.assertEqual(plan.tasks[0].inputs['explicit_deadline'], '2027-03-30')
        self.assertEqual(plan.tasks[1].inputs['trusted_deadline'], '2027-03-30')
        self.assertNotIn('database.create_project', registry.visible(self.context))
        self.assertIn(
            'database.create_project',
            registry.visible(self.context, allow_approvals=True),
        )
        self.assertTrue(registry.lookup('database.create_project')[1].approval_required)

        project_output = ProjectAgentOutput.model_validate({
            'outcome': 'specification',
            'response': 'Specification prepared.',
            'specification': {
                'name': 'Flutter Commerce',
                'description': 'A Flutter e-commerce application.',
                'project_type': 'e-commerce',
                'deadline': '2027-03-30',
                'features': [{
                    'name': 'Authentication',
                    'description': 'Authenticate users.',
                }],
                'functional_requirements': [{
                    'identifier': 'FR-001',
                    'description': 'Users can authenticate.',
                }],
                'technology_stack': {
                    'architecture_style': 'API-backed mobile application',
                    'choices': [{
                        'layer': 'mobile',
                        'name': 'Flutter',
                        'purpose': 'Mobile client',
                        'rationale': 'Requested platform.',
                        'source': 'user_required',
                    }],
                },
                'required_roles': [{
                    'name': 'Mobile Engineer',
                    'responsibilities': ['Build the mobile client.'],
                    'skills': ['Flutter'],
                }],
                'required_skills': [{
                    'name': 'Flutter',
                    'category': 'Technical',
                }],
                'milestones': [{
                    'name': 'MVP',
                    'objective': 'Deliver the first release.',
                    'deliverables': ['Working application'],
                    'estimated_duration_weeks': 4,
                }],
            },
        })
        project_result = ProjectAgentResult(
            answer=project_output.response,
            structured_output=project_output,
        )
        project_task_result = TaskResult(
            task_id='plan_project',
            agent='project',
            capability='project.plan',
            status='done',
            output=project_result.model_dump(mode='json'),
        )
        create_inputs = resolve_inputs(
            plan.tasks[1],
            registry.lookup('database.create_project')[1],
            {'plan_project': project_task_result},
        )
        self.assertEqual(create_inputs.trusted_deadline, '2027-03-30')
        self.assertEqual(create_inputs.specification['outcome'], 'specification')
        self.assertEqual(
            create_inputs.specification['specification']['deadline'],
            '2027-03-30',
        )

        create_output = {
            'project_id': 123,
            'name': 'Flutter Commerce',
            'deadline': '2027-03-30',
            'requirements_created': 1,
        }
        create_task_result = TaskResult(
            task_id='save_project',
            agent='database',
            capability='database.create_project',
            status='done',
            output=create_output,
        )
        matching_inputs = resolve_inputs(
            plan.tasks[2],
            registry.lookup('matching.rank')[1],
            {'save_project': create_task_result},
        )
        self.assertEqual(matching_inputs.project_id, 123)

    def test_three_task_plan_still_requires_write_authorization(self):
        plan = ExecutionPlan.model_validate({
            'goal': 'Save and match a planned project.',
            'tasks': [
                task('plan_project', 'project.plan', {'task': 'Plan a store'}),
                task(
                    'save_project', 'database.create_project', {'top_n': 5},
                    depends_on=['plan_project'],
                    references={'specification': {
                        'task_id': 'plan_project', 'field': 'structured_output',
                    }},
                ),
                task(
                    'rank_employees', 'matching.rank', {'top_n': 5},
                    depends_on=['save_project'],
                    references={'project_id': {
                        'task_id': 'save_project', 'field': 'project_id',
                    }},
                ),
            ],
        })
        permissions = {'projects.write', 'projects.read', 'workforce.read', 'approvals.decide'}
        for missing_permission, blocked_capability in (
            ('projects.write', 'database.create_project'),
            ('projects.read', 'matching.rank'),
            ('workforce.read', 'matching.rank'),
        ):
            with self.subTest(permission=missing_permission):
                context = ExecutionContext(
                    7, 20,
                    frozenset({'project.plan', 'database.create_project', 'matching.rank'}),
                    frozenset(permissions - {missing_permission}),
                )
                registry = specialist_registry()
                with self.assertLogs('orchestrator.core.plan_validator', level='WARNING') as captured:
                    with self.assertRaises(ValueError) as raised:
                        validate_real_plan(plan, registry, context, PlanLimits(max_tasks=3))
                self.assertEqual(str(raised.exception), 'The proposed plan did not pass validation.')
                diagnostic = captured.records[0].plan_validation
                self.assertEqual(diagnostic['error_code'], 'capability_not_authorized')
                self.assertEqual(diagnostic['capability'], blocked_capability)
                self.assertNotIn(
                    blocked_capability,
                    registry.visible(context, allow_approvals=True),
                )

    def test_multiturn_preserves_history_and_results(self):
        previous = TaskResult(task_id='old', agent='project', capability='project.plan',
                              status='done', output={'answer': 'Confidential fixture'})
        result = self.decision(
            'direct_response', request='Next?',
            messages=[HumanMessage(content='Earlier'), AIMessage(content='Earlier answer')],
            results={'old': previous}, project_id=42, project_requirements={'scope': 'fixture'},
        )
        self.assertEqual([message.content for message in result['messages']],
                         ['Earlier', 'Earlier answer', 'Next?', 'Fixture response'])
        self.assertEqual(result['results']['old'], previous)
        sent = str(self.model.invoke.call_args.args[0])
        self.assertIn('Earlier answer', sent)
        self.assertIn('project.plan', sent)
        self.assertNotIn('Confidential fixture', sent)

    def test_provider_errors_are_safe(self):
        for status, code in ((429, 'rate_limited'), (503, 'provider_error')):
            self.model.invoke.side_effect = LLMProviderError(status)
            result = self.graph.invoke({'request': 'Hello'}, context=self.context)
            self.assertEqual(result['decision'].outcome, 'planning_error')
            self.assertEqual(result['errors'][0].code, code)
            self.assertEqual(result['metadata']['provider_status'], status)

    def test_plan_limits(self):
        self.graph = build_planning_graph(specialist_registry(), planner=self.model,
                                          limits=PlanLimits(max_tasks=1))
        result = self.decision('plan', task('a', 'project.plan', {'task': 'Draft'}),
                               task('b', 'project.plan', {'task': 'Revise'}))
        self.assertEqual(result['errors'][0].code, 'invalid_plan')
