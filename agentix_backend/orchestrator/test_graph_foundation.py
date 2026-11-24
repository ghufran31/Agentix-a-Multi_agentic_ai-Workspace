import json
from threading import Barrier
from unittest.mock import Mock

from django.test import SimpleTestCase
from langchain_core.messages import HumanMessage
from pydantic import Field, ValidationError

from orchestrator.agents.project.schemas import ProjectAgentResult
from orchestrator.core.agent_registry import Agent, AgentRegistry, Capability, specialist_registry
from orchestrator.core.execution_context import ExecutionContext
from orchestrator.core.plan_schemas import Contract, ExecutionPlan
from orchestrator.core.plan_validator import PlanLimits
from orchestrator.graph.builder import build_graph


class Number(Contract):
    value: int = Field(gt=0)


class Text(Contract):
    value: str


def task(task_id, *, capability='mock.number', depends_on=(), inputs=None, references=None):
    return dict(task_id=task_id, capability=capability, description='Mock task',
                depends_on=list(depends_on), inputs={'value': 1} if inputs is None else inputs,
                references=references or {})


def registry_with(handler):
    registry = AgentRegistry()
    registry.register(Agent('mock', 'Mock', 'Fixture', (
        Capability('mock.number', Number, Number, frozenset({'mock.read'}), mock_executor=handler),
        Capability('mock.text', Text, Text, mock_executor=handler),
        Capability('mock.approval', Number, Number, approval_required=True, mock_executor=handler),
    )))
    return registry


class FoundationTests(SimpleTestCase):
    context = ExecutionContext(7, 20, frozenset({'mock.number', 'mock.text', 'mock.approval'}),
                               frozenset({'mock.read'}))

    def setUp(self):
        self.handler = Mock(side_effect=lambda inputs, previous, context: inputs)
        self.registry = registry_with(self.handler)
        self.graph = build_graph(self.registry)

    def invoke(self, *tasks, graph=None, **kwargs):
        return (graph or self.graph).invoke({
            'request': 'Fixture request', 'messages': [HumanMessage(content='Fixture message')],
            'project_id': None, 'project_requirements': {'key': 'value'},
            'plan': {'goal': 'Fixture goal', 'tasks': list(tasks)}, **kwargs,
        }, context=self.context)

    def rejected(self, fragment, *tasks, **kwargs):
        with self.assertLogs('orchestrator.core.plan_validator', level='WARNING') as captured:
            result = self.invoke(*tasks, **kwargs)
        self.assertEqual(result['errors'][0].code, 'invalid_plan')
        self.assertEqual(
            result['errors'][0].message,
            'The proposed plan did not pass validation.',
        )
        self.assertEqual(captured.records[0].plan_validation['error_code'], fragment)
        self.assertEqual(result['task_statuses'], {})
        self.handler.assert_not_called()

    def test_global_state_uses_trusted_identity(self):
        result = self.invoke(task('a'), user_id=99, company_id=99, task_statuses={'fake': 'done'})
        self.assertEqual((result['user_id'], result['company_id']), (7, 20))
        self.assertEqual(len(result['messages']), 1)
        self.assertEqual(result['request'], 'Fixture request')
        self.assertEqual(result['project_requirements'], {'key': 'value'})
        self.assertEqual(result['pending_approvals'], [])
        self.assertEqual(result['metadata']['mode'], 'mock')
        self.assertEqual(result['task_statuses'], {'a': 'done'})

    def test_registry_and_lookup(self):
        registry = specialist_registry()
        agent, capability = registry.lookup('matching.rank')
        self.assertEqual(agent.identifier, 'matching')
        self.assertEqual(capability.input_schema.__name__, 'MatchingRequest')
        self.assertIsNone(capability.mock_executor)
        self.assertEqual(registry.visible(self.context), {})
        with self.assertRaises(ValueError):
            self.registry.register(Agent('mock', 'Duplicate', '', ()))

    def test_specialist_metadata_accepts_mock_only_binding(self):
        self.context = ExecutionContext(7, 20, frozenset({'project.plan'}))
        planned = task('plan', capability='project.plan', inputs={'task': 'Plan a fixture'})
        self.rejected('mock_executor_missing', planned, graph=build_graph(specialist_registry()))
        mock = Mock(return_value=ProjectAgentResult(answer='Fixture'))
        graph = build_graph(specialist_registry({'project.plan': mock}))
        result = self.invoke(planned, graph=graph)
        self.assertEqual(result['results']['plan'].output['answer'], 'Fixture')
        self.assertEqual(mock.call_args.args[0].task, 'Plan a fixture')

    def test_resolved_reference_revalidates_constraints(self):
        self.handler.return_value = Text(value='wrong')
        self.handler.side_effect = None
        # The producer and consumer have the same JSON type, but distinct constraints.
        class LimitedText(Contract):
            value: str = Field(max_length=2)

        self.registry.register(Agent('limited', 'Limited', 'Fixture', (
            Capability('limited.text', LimitedText, Text, mock_executor=self.handler),
        )))
        self.context = ExecutionContext(7, 20, frozenset({'mock.text', 'limited.text'}))
        result = self.invoke(
            task('a', capability='mock.text', inputs={'value': 'x'}),
            task('b', capability='limited.text', inputs={}, depends_on=['a'],
                 references={'value': {'task_id': 'a', 'field': 'value'}}),
        )
        self.assertEqual(result['results']['b'].error.code, 'invalid_resolved_inputs')
        self.assertEqual(self.handler.call_count, 1)

    def test_schema_rejects_extra_fields(self):
        with self.assertRaises(ValidationError):
            ExecutionPlan.model_validate({'goal': 'Test', 'tasks': [task('a')], 'company_id': 99})

    def test_execution_plan_schema_errors_are_logged_without_values(self):
        private_value = 'private-input-value'
        with self.assertLogs('orchestrator.core.plan_validator', level='WARNING') as captured:
            result = self.invoke(
                task('a'),
                plan={
                    'goal': 'Fixture goal',
                    'tasks': [task('a')],
                    'private_field': private_value,
                },
            )
        diagnostic = captured.records[0].plan_validation
        self.assertEqual(diagnostic['error_code'], 'invalid_plan_schema')
        self.assertEqual(diagnostic['pydantic_errors'], [{
            'loc': ['[redacted]'],
            'type': 'extra_forbidden',
        }])
        self.assertNotIn(private_value, captured.output[0])
        self.assertEqual(result['errors'][0].code, 'invalid_plan')
        self.assertNotIn(private_value, result['errors'][0].message)

    def test_unknown_capability(self):
        self.rejected('capability_unknown', task('a', capability='mock.missing'))

    def test_duplicate_task(self):
        self.rejected('duplicate_task_id', task('a'), task('a'))

    def test_missing_dependency(self):
        self.rejected('dependency_not_found', task('a', depends_on=['b']))

    def test_cycle(self):
        self.rejected('dependency_cycle', task('a', depends_on=['b']), task('b', depends_on=['a']))

    def test_approval_rejected(self):
        self.rejected('approval_not_enabled', task('a', capability='mock.approval'))

    def test_unauthorized_capability(self):
        self.context = ExecutionContext(7, 20, frozenset({'mock.number'}))
        self.rejected('capability_not_authorized', task('a'))

    def test_count_and_depth_limits(self):
        self.rejected('task_limit_exceeded', task('a'), task('b'),
                      graph=build_graph(self.registry, limits=PlanLimits(max_tasks=1)))
        self.rejected('dependency_depth_exceeded', task('a'), task('b', depends_on=['a']),
                      graph=build_graph(self.registry, limits=PlanLimits(max_depth=1)))

    def test_invalid_literal_input(self):
        with self.assertLogs('orchestrator.core.plan_validator', level='WARNING') as captured:
            result = self.invoke(task('a', inputs={'value': '1'}))
        self.assertEqual(result['errors'][0].code, 'invalid_plan')
        diagnostic = captured.records[0].plan_validation
        self.assertEqual(diagnostic['error_code'], 'task_inputs_invalid')
        self.assertEqual(diagnostic['task_ids'], ['a'])
        self.assertEqual(diagnostic['capability'], 'mock.number')
        self.assertEqual(diagnostic['pydantic_errors'], [{'loc': ['value'], 'type': 'int_type'}])
        self.assertNotIn("'1'", json.dumps(diagnostic))
        self.assertEqual(result['errors'][0].message, 'The proposed plan did not pass validation.')
        self.assertEqual(result['task_statuses'], {})
        self.handler.assert_not_called()

    def test_bad_references(self):
        self.rejected('reference_not_direct_dependency', task('a'), task(
            'b', inputs={}, references={'value': {'task_id': 'a', 'field': 'value'}}))
        self.rejected('reference_output_field_unknown', task('a'), task(
            'b', depends_on=['a'], inputs={}, references={'value': {'task_id': 'a', 'field': 'missing'}}))
        self.rejected('reference_type_incompatible', task('a'), task(
            'b', capability='mock.text', depends_on=['a'], inputs={},
            references={'value': {'task_id': 'a', 'field': 'value'}}))

    def test_single_task_and_graph_reuse(self):
        for key in ('a', 'b'):
            result = self.invoke(task(key))
            self.assertEqual(set(result['results']), {key})
            self.assertEqual(result['results'][key].output, {'value': 1})

    def test_parallel_overlap_and_concurrent_updates(self):
        barrier = Barrier(2, timeout=4)
        self.handler.side_effect = lambda inputs, previous, context: (
            barrier.wait(), inputs
        )[1]
        result = self.invoke(task('a'), task('b', inputs={'value': 2}))
        self.assertEqual(result['task_statuses'], {'a': 'done', 'b': 'done'})
        self.assertEqual({key: item.output['value'] for key, item in result['results'].items()},
                         {'a': 1, 'b': 2})

    def test_sequential_typed_reference(self):
        result = self.invoke(task('a', inputs={'value': 7}), task(
            'b', depends_on=['a'], inputs={}, references={'value': {'task_id': 'a', 'field': 'value'}}))
        self.assertEqual(result['results']['b'].output, {'value': 7})
        self.assertEqual(list(self.handler.call_args_list[1].args[1]), ['a'])

    def test_parallel_join_reads_both_results(self):
        barrier = Barrier(2, timeout=4)

        def run(inputs, previous, context):
            if not previous:
                barrier.wait()
                return inputs
            return Number(value=sum(item.output['value'] for item in previous.values()))

        self.handler.side_effect = run
        result = self.invoke(task('a'), task('b', inputs={'value': 3}),
                             task('c', depends_on=['a', 'b']))
        self.assertEqual(result['results']['c'].output, {'value': 4})

    def test_failure_blocks_transitively_and_independent_task_survives(self):
        def run(inputs, previous, context):
            if inputs.value == 1:
                raise RuntimeError('sensitive message')
            return inputs

        self.handler.side_effect = run
        result = self.invoke(task('a'), task('b', depends_on=['a']),
                             task('c', depends_on=['b']), task('d', inputs={'value': 2}))
        self.assertEqual(result['task_statuses'], {'a': 'failed', 'b': 'blocked',
                                                  'c': 'blocked', 'd': 'done'})
        self.assertEqual(result['results']['a'].error.code, 'mock_execution_failed')
        self.assertEqual(result['results']['c'].error.code, 'prerequisite_failed')
        self.assertNotIn('sensitive message', str(result['errors']))
        self.assertEqual(self.handler.call_count, 2)

    def test_invalid_output_is_rejected(self):
        self.handler.side_effect = None
        self.handler.return_value = {'value': 'wrong'}
        result = self.invoke(task('a'))
        self.assertEqual(result['results']['a'].error.code, 'invalid_task_output')
