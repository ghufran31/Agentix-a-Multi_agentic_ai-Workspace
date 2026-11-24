from threading import Barrier, Lock
from unittest.mock import Mock

from django.test import SimpleTestCase
from langchain_core.messages import AIMessage, HumanMessage

from orchestrator.core.agent_registry import Agent, AgentRegistry, Capability
from orchestrator.core.execution_context import ExecutionContext
from orchestrator.core.plan_schemas import Contract, TaskResult
from orchestrator.core.plan_validator import PlanLimits
from orchestrator.graph.builder import build_integrated_graph


class Number(Contract):
    value: int


def task(identifier, value=1, *, dependencies=(), reference=None, capability='mock.run'):
    return {
        'task_id': identifier, 'capability': capability, 'description': 'Fixture task',
        'inputs': {'value': value} if reference is None else {},
        'depends_on': list(dependencies),
        'references': {} if reference is None else {'value': {'task_id': reference, 'field': 'value'}},
    }


class IntegratedGraphTests(SimpleTestCase):
    def setUp(self):
        self.planner = Mock()
        self.worker = Mock(side_effect=lambda inputs, predecessors, context: inputs)
        self.context = ExecutionContext(
            4, 8, frozenset({'mock.run', 'mock.approval', 'mock.unbound'}),
        )
        self.registry = AgentRegistry()
        self.registry.register(Agent('mock', 'Mock', 'Fixture', (
            Capability('mock.run', Number, Number, mock_executor=self.worker),
            Capability('mock.unbound', Number, Number),
            Capability('mock.approval', Number, Number, approval_required=True,
                       mock_executor=self.worker),
        )))
        self.graph = build_integrated_graph(self.registry, planner=self.planner)

    def invoke(self, *tasks, outcome='plan', **state):
        decision = {'outcome': outcome, 'response': 'Planner reply'}
        if tasks:
            decision['plan'] = {'goal': 'Fixture goal', 'tasks': list(tasks)}
        self.planner.invoke.return_value = {'parsed': decision, 'raw': AIMessage(content='')}
        return self.graph.invoke({'request': 'Original request', **state}, context=self.context)

    def test_non_execution_routes(self):
        for outcome in ('direct_response', 'clarification', 'unsupported', 'planning_error'):
            with self.subTest(outcome=outcome):
                result = self.invoke(outcome=outcome)
                self.assertEqual(result['decision'].outcome, outcome)
                self.assertIsNone(result.get('execution_summary'))
                self.assertFalse(result.get('results'))
                self.assertEqual(len(result['messages']), 2)
        self.worker.assert_not_called()

    def test_valid_single_plan_dispatches_once_and_reports_output(self):
        result = self.invoke(task('one', 7))
        summary = result['execution_summary']
        self.assertEqual(summary.request, 'Original request')
        self.assertEqual(summary.goal, 'Fixture goal')
        self.assertEqual(summary.plan, result['plan'])
        self.assertEqual(summary.status, 'done')
        self.assertEqual(summary.completed[0].output, {'value': 7})
        self.assertIn('"value": 7', result['final_response'])
        self.assertEqual(result['messages'][-1].content, result['final_response'])
        self.assertEqual(result['metadata']['invocations'], 1)
        self.assertEqual(len(result['messages']), 2)
        self.worker.assert_called_once()
        self.assertIs(self.worker.call_args.args[2], self.context)
        self.planner.invoke.assert_called_once()

    def test_invalid_plan_and_unauthorized_capability_never_execute(self):
        for planned in (
            (task('a'), task('a')),
            (task('a', dependencies=['a']),),
            (task('a', capability='mock.approval'),),
            (task('a', capability='mock.secret'),),
            (task('a', value='invalid'),),
        ):
            with self.subTest(planned=planned):
                result = self.invoke(*planned)
                self.assertEqual(result['errors'][0].code, 'invalid_plan')
                self.assertIsNone(result['plan'])
        self.context = ExecutionContext(4, 8, frozenset())
        self.assertEqual(self.invoke(task('a'))['errors'][0].code, 'invalid_plan')
        self.worker.assert_not_called()

    def test_allowed_plan_without_mock_binding_is_rejected_before_any_work(self):
        with self.assertLogs('orchestrator.core.plan_validator', level='WARNING') as captured:
            result = self.invoke(task('a'), task('b', capability='mock.unbound'))
        self.assertEqual(result['decision'].outcome, 'planning_error')
        self.assertIsNone(result['plan'])
        self.assertEqual(result['errors'][0].message, 'The proposed plan did not pass validation.')
        self.assertEqual(
            captured.records[0].plan_validation['error_code'],
            'mock_executor_missing',
        )
        self.worker.assert_not_called()

    def test_parallel_tasks_overlap_and_fan_in_references_actual_output(self):
        barrier = Barrier(2, timeout=5)
        seen = []
        lock = Lock()

        def worker(inputs, predecessors, context):
            if not predecessors:
                with lock:
                    seen.append(inputs.value)
                barrier.wait()
                return Number(value=inputs.value * 10)
            self.assertEqual(set(predecessors), {'a', 'b'})
            self.assertEqual(inputs.value, 20)
            return Number(value=inputs.value + predecessors['b'].output['value'])

        self.worker.side_effect = worker
        result = self.invoke(task('a', 2), task('b', 3),
                             task('c', dependencies=['a', 'b'], reference='a'))
        self.assertCountEqual(seen, [2, 3])
        self.assertEqual(result['task_statuses'], {'a': 'done', 'b': 'done', 'c': 'done'})
        self.assertEqual(result['results']['c'].output, {'value': 50})
        self.assertEqual(self.worker.call_count, 3)

    def test_sequential_chain_terminates_at_depth_limit_without_duplicates(self):
        self.graph = build_integrated_graph(self.registry, planner=self.planner,
                                            limits=PlanLimits(max_tasks=6, max_depth=6))
        scheduled = [task('a', 1)]
        for index in range(1, 6):
            prior = scheduled[-1]['task_id']
            scheduled.append(task(f'a{index}', dependencies=[prior], reference=prior))
        self.worker.side_effect = lambda inputs, previous, context: Number(value=inputs.value + 1)
        result = self.invoke(*scheduled)
        self.assertEqual(result['results']['a5'].output, {'value': 7})
        self.assertEqual(self.worker.call_count, 6)
        self.assertEqual(result['metadata']['status'], 'done')

    def test_failed_prerequisite_blocks_branch_but_unrelated_tasks_continue(self):
        def worker(inputs, predecessors, context):
            if inputs.value == 1:
                raise RuntimeError('private fixture')
            return inputs

        self.worker.side_effect = worker
        result = self.invoke(task('a'), task('blocked', dependencies=['a']),
                             task('b', 2), task('c', 3, dependencies=['b']))
        summary = result['execution_summary']
        self.assertEqual(summary.status, 'partial')
        self.assertEqual([item.task_id for item in summary.completed], ['b', 'c'])
        self.assertEqual([item.task_id for item in summary.failed], ['a'])
        self.assertEqual([item.task_id for item in summary.blocked], ['blocked'])
        self.assertEqual({error.code for error in summary.errors},
                         {'mock_execution_failed', 'prerequisite_failed'})
        self.assertNotIn('private fixture', result['final_response'])
        self.assertEqual(self.worker.call_count, 3)

    def test_invalid_worker_output_fails_and_has_no_completed_output(self):
        self.worker.side_effect = None
        self.worker.return_value = {'value': 'invalid'}
        result = self.invoke(task('a'))
        self.assertEqual(result['execution_summary'].status, 'failed')
        self.assertEqual(result['results']['a'].error.code, 'invalid_task_output')
        self.assertIsNone(result['results']['a'].output)

    def test_prior_messages_and_results_remain_separate_even_with_reused_task_id(self):
        previous = TaskResult(task_id='a', agent='mock', capability='mock.run',
                              status='done', output={'value': 99})
        result = self.invoke(
            task('a', 2), previous_results={'a': previous},
            messages=[HumanMessage(content='Earlier'), AIMessage(content='Earlier reply')],
            project_id=42, project_requirements={'scope': 'fixture'},
        )
        self.assertEqual([message.content for message in result['messages'][:3]],
                         ['Earlier', 'Earlier reply', 'Original request'])
        self.assertEqual(result['previous_results']['a'].output, {'value': 99})
        self.assertEqual(result['results']['a'].output, {'value': 2})
        self.assertEqual(result['project_id'], 42)
        self.assertEqual(result['project_requirements'], {'scope': 'fixture'})
        self.assertNotIn('"value": 99', result['final_response'])
        self.assertIn('"task_id": "a"', str(self.planner.invoke.call_args.args[0][-2].content))
        self.worker.assert_called_once()

    def test_graph_refuses_implicit_live_planner(self):
        with self.assertRaises(ValueError):
            build_integrated_graph(self.registry, planner=None)
