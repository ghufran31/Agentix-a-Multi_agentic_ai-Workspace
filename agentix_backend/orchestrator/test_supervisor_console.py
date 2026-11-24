from contextlib import closing
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connection
from asgiref.sync import async_to_sync
from django.test import AsyncClient, Client, SimpleTestCase, TransactionTestCase, override_settings

from companies.models import Company, CompanyUser
from orchestrator.graph.checkpoints import memory_checkpoints, open_postgres_checkpoints
from orchestrator.graph.console_contract import execution_state
from orchestrator.graph.console_journal import setup_console_tables
from orchestrator.test_persistent_supervisor import ConversationFixtures


BASE = '/dev/supervisor/'
API = BASE + 'api/v1/conversations/'


class StreamTests(ConversationFixtures, SimpleTestCase):
    def test_parallel_stream_reports_actual_worker_overlap_and_dependencies(self):
        barrier = Barrier(2)

        def parallel(inputs, predecessors, context):
            if not predecessors:
                barrier.wait(3)
            return inputs

        self.worker.side_effect = parallel
        service = self.service(memory_checkpoints())
        thread = service.create_thread(self.user, 10)
        events = []
        self.plan()
        first = service.turn(thread, self.user, 10, 'Parallel run', events=events.append)
        proposal, = first['pending_approvals']
        result = self.resume(service, thread, proposal, events=events.append)
        self.assertEqual(result['execution_summary'].status, 'done')
        self.assertEqual({event['execution_id'] for event in events}, {proposal['execution_id']})
        sequence = [(event['type'], event['task_id']) for event in events]

        def before(left, right):
            self.assertLess(sequence.index(left), sequence.index(right), sequence)

        for identifier in ('first', 'independent', 'gate', 'after'):
            before(('task_scheduled', identifier), ('agent_started', identifier))
            before(('agent_started', identifier), ('agent_completed', identifier))
        before(('conversation_started', None), ('planner_decision', None))
        before(('planner_decision', None), ('plan_validated', None))
        before(('agent_started', 'first'), ('agent_completed', 'independent'))
        before(('agent_started', 'independent'), ('agent_completed', 'first'))
        before(('approval_requested', 'gate'), ('approval_resolved', 'gate'))
        before(('approval_resolved', 'gate'), ('agent_started', 'gate'))
        before(('agent_completed', 'gate'), ('agent_started', 'after'))
        self.assertEqual(sequence[-1], ('execution_completed', None))
        self.assertNotIn('inputs', str(events))

    def test_failure_events_and_blocked_dependents(self):
        self.worker.side_effect = ValueError('private diagnostic')
        self.plan()
        service = self.service(memory_checkpoints())
        thread = service.create_thread(self.user, 10)
        events = []
        service.turn(thread, self.user, 10, 'Run failure', events=events.append)
        self.assertEqual(events[-1]['type'], 'execution_failed')
        self.assertEqual({event['task_id'] for event in events if event['type'] == 'task_blocked'},
                         {'gate', 'after'})
        self.assertNotIn('private diagnostic', str(events))

    def test_research_projection_exposes_citations_without_tool_payloads(self):
        from orchestrator.core.plan_schemas import ExecutionPlan, TaskResult

        plan = ExecutionPlan.model_validate({'goal': 'Research', 'tasks': [{
            'task_id': 'read', 'capability': 'research.search', 'description': 'Read', 'inputs': {
                'question': 'private tool input',
            },
        }]})
        result = TaskResult(task_id='read', agent='research', capability='research.search',
                            status='done', output={
                                'summary': {'findings': []},
                                'sources': [{'title': 'Source', 'url': 'https://example.com/',
                                             'excerpt': 'private tool input'}],
                                'tool_results': [{'provider_response': 'private tool input'}],
                            })
        projected = execution_state({'plan': plan, 'results': {'read': result}}, False, 'real')
        self.assertEqual(projected['plan']['tasks'][0]['output']['sources'],
                         [{'title': 'Source', 'url': 'https://example.com/'}])
        self.assertNotIn('private tool input', str(projected))


@override_settings(AGENTIX_SUPERVISOR_CONSOLE_ENABLED=True, AGENTIX_SUPERVISOR_CONSOLE_MODE='mock')
class ConsoleTests(TransactionTestCase):
    def setUp(self):
        if (connection.vendor != 'postgresql'
                or not connection.settings_dict['NAME'].startswith('test_agentix_phase06_')):
            self.skipTest('Requires a dedicated test_agentix_phase06_ PostgreSQL database.')
        self.env = patch.dict('os.environ', {'AGENTIX_CHECKPOINT_DSN': ''})
        self.env.start()
        self.addCleanup(self.env.stop)
        with open_postgres_checkpoints(setup=True) as store:
            setup_console_tables(store.connection)
        users = get_user_model().objects
        self.owner = users.create_user(username='console-owner', is_staff=True)
        self.peer = users.create_user(username='console-peer', is_staff=True)
        self.member = users.create_user(username='console-member')
        self.company = Company.objects.create(created_by_user=self.owner, name='Console company')
        self.other = Company.objects.create(created_by_user=self.peer, name='Other company')
        CompanyUser.objects.bulk_create([
            CompanyUser(company=self.company, user=self.owner, role=CompanyUser.Role.OWNER),
            CompanyUser(company=self.company, user=self.peer, role=CompanyUser.Role.OWNER),
            CompanyUser(company=self.company, user=self.member),
            CompanyUser(company=self.other, user=self.owner, role=CompanyUser.Role.OWNER),
        ])
        self.client.force_login(self.owner)

    def post(self, url, payload=None, **kwargs):
        return self.client.post(url, payload or {}, content_type='application/json', **kwargs)

    def create(self):
        response = self.post(API)
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()['thread']

    def send(self, thread, message, request_id=None, **options):
        return self.post(f'{API}{thread}/messages/', {
            'message': message, 'request_id': str(request_id or uuid4()), **options,
        })

    def state(self, thread):
        return self.client.get(f'{API}{thread}/execution/').json()

    def test_auth_staff_csrf_and_disabled(self):
        self.assertEqual(Client().get(API).status_code, 401)
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(BASE).status_code, 403)
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.owner)
        self.assertEqual(self.post(API).status_code, 403)
        page = self.client.get(BASE)
        self.assertContains(page, 'Supervisor Console')
        self.assertContains(page, 'Mock mode')
        token = page.cookies['csrftoken'].value
        self.assertEqual(self.post(API, HTTP_X_CSRFTOKEN=token).status_code, 201)
        with self.settings(AGENTIX_SUPERVISOR_CONSOLE_ENABLED=False):
            self.assertEqual(self.client.get(BASE).status_code, 404)

    def test_create_list_send_refresh_and_replay(self):
        thread = self.create()
        self.assertEqual(self.client.get(API).json()['conversations'][0]['thread'], thread)
        self.assertEqual(self.state(thread)['status'], 'idle')
        identifier = uuid4()
        response = self.send(thread, 'demo', identifier)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.send(thread, 'demo', identifier).status_code, 200)
        refreshed = Client()
        refreshed.force_login(self.owner)
        messages = refreshed.get(f'{API}{thread}/messages/').json()['messages']
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]['content'], 'demo')
        state = self.state(thread)
        self.assertEqual(state['execution_id'], identifier.hex)
        self.assertEqual(state['status'], 'done')
        self.assertEqual(state['plan']['tasks'][0]['output'], {'topic': 'preview', 'simulated': True})
        self.assertEqual(self.send(thread, 'another turn').status_code, 200)
        messages = refreshed.get(f'{API}{thread}/messages/').json()['messages']
        self.assertEqual(len(messages), 4)

    def test_scopes_and_browser_overrides(self):
        thread = self.create()
        self.assertEqual(self.send(thread, 'demo', company_id=self.other.pk).status_code, 400)
        self.assertEqual(self.send(thread, 'demo', mode='real').status_code, 400)
        self.assertEqual(self.send(thread, 'demo', project_id=99999999).status_code, 403)
        peer = Client()
        peer.force_login(self.peer)
        for endpoint in ('messages', 'execution', 'events'):
            self.assertEqual(peer.get(f'{API}{thread}/{endpoint}/').status_code, 403)
        session = self.client.session
        session['agentix_supervisor_company_id'] = self.other.pk
        session.save()
        self.assertEqual(self.client.get(API).json()['conversations'], [])
        self.assertEqual(self.client.get(f'{API}{thread}/events/').status_code, 403)
        with self.settings(AGENTIX_SUPERVISOR_CONSOLE_MODE='real'):
            self.assertEqual(self.client.get(API).json()['mode'], 'real')
            self.assertEqual(self.client.get(f'{API}{thread}/execution/').status_code, 403)

    def test_sse_reconnect_is_read_only(self):
        thread = self.create()
        self.assertEqual(self.send(thread, 'demo').status_code, 200)
        url = f'{API}{thread}/events/'
        first = self.client.get(url)
        self.assertEqual(first['Content-Type'], 'text/event-stream')
        stream = iter(first.streaming_content)
        next(stream)
        event = next(stream).decode()
        first.close()
        cursor = event.splitlines()[0].removeprefix('id: ')
        self.assertIn('conversation_started', event)
        resumed = self.client.get(url, HTTP_LAST_EVENT_ID=cursor)
        stream = iter(resumed.streaming_content)
        next(stream)
        event = next(stream).decode()
        resumed.close()
        self.assertIn('planner_decision', event)
        self.assertGreater(int(event.splitlines()[0].removeprefix('id: ')), int(cursor))
        self.assertEqual(len(self.client.get(f'{API}{thread}/messages/').json()['messages']), 2)

    def test_asgi_event_stream(self):
        thread = self.create()
        self.assertEqual(self.send(thread, 'demo failure').status_code, 200)
        client = AsyncClient()
        client.cookies = self.client.cookies

        async def read_initial_events():
            response = await client.get(f'{API}{thread}/events/')
            self.assertTrue(response.is_async)
            self.assertEqual(response.headers['X-Accel-Buffering'], 'no')
            stream = aiter(response.streaming_content)
            await anext(stream)
            frame = (await anext(stream)).decode()
            await stream.aclose()
            return frame

        self.assertIn('conversation_started', async_to_sync(read_initial_events)())
        self.assertEqual(self.state(thread)['status'], 'partial')

    def test_approval_rejection_and_role_revalidation(self):
        thread = self.create()
        for approved in (False, True):
            response = self.send(thread, 'demo approval')
            self.assertEqual(response.status_code, 200, response.content)
            state = self.state(thread)
            self.assertEqual(state['status'], 'awaiting_approval')
            pending, = state['pending_approvals']
            self.assertEqual(pending['inputs'], {'topic': 'review'})
            payload = {key: pending[key] for key in ('execution_id', 'approval_id')}
            payload['approved'] = approved
            url = f'{API}{thread}/approval/'
            memberships = CompanyUser.objects.filter(user=self.owner, company=self.company)
            memberships.update(role=CompanyUser.Role.MEMBER)
            self.assertEqual(self.post(url, payload).status_code, 403)
            memberships.update(role=CompanyUser.Role.OWNER)
            response = self.post(url, payload)
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(self.state(thread)['status'], 'done' if approved else 'partial')
            self.assertEqual(self.state(thread)['approval_records'][0]['status'],
                             'approved' if approved else 'rejected')
            self.assertEqual(self.post(url, payload).status_code, 409)

    @override_settings(AGENTIX_SUPERVISOR_CONSOLE_MODE='real', SUPERVISOR_FALLBACK_ENABLED=False)
    @patch('orchestrator.graph.planner.structured_llm')
    @patch('orchestrator.graph.planner.get_llm')
    @patch('orchestrator.core.specialist_dispatch.execute_project_task')
    def test_real_console_dispatch_and_followup_history(self, project, model, structured):
        from orchestrator.agents.project.schemas import ProjectAgentOutput, ProjectAgentResult
        from orchestrator.agents.project.tests.test_project_agent import specification_data
        from orchestrator.test_real_dispatch import mock_planner, task
        from projects.models import Project

        count = Project.objects.count()
        structured.return_value = mock_planner(
            task('draft', 'project.plan', {'task': 'Plan a Flutter store. Do not save.'}),
        )
        project.return_value = ProjectAgentResult(answer='Draft', structured_output=ProjectAgentOutput(
            outcome='specification', response='Draft', specification=specification_data(),
        ))
        thread = self.create()
        response = self.send(thread, 'Prepare a project specification for a Flutter store.')
        self.assertEqual(response.status_code, 200, response.content)
        state = self.state(thread)
        self.assertEqual(state['mode'], 'real')
        self.assertEqual(state['status'], 'done')
        self.assertEqual(state['plan']['tasks'][0]['output']['specification']['name'], 'Commerce Project')
        project.assert_called_once_with(None, 'Plan a Flutter store. Do not save.')
        structured.return_value.invoke.return_value = {
            'parsed': {'outcome': 'direct_response', 'response': 'Follow-up received.'},
        }
        response = self.send(thread, 'What did we plan?')
        self.assertEqual(response.status_code, 200, response.content)
        messages = structured.return_value.invoke.call_args.args[0]
        self.assertTrue(any('Flutter store' in item.content for item in messages[:-1]))
        self.assertEqual(Project.objects.count(), count)
        model.assert_called_with(role='supervisor')

    @override_settings(AGENTIX_SUPERVISOR_CONSOLE_MODE='real', SUPERVISOR_FALLBACK_ENABLED=False)
    @patch('orchestrator.graph.planner.structured_llm')
    @patch('orchestrator.graph.planner.get_llm')
    @patch('orchestrator.agents.project.agent.build_project_output_model')
    @patch('orchestrator.agents.project.agent.build_project_agent')
    def test_project_parser_details_reach_checkpoint_state_and_sse(self, build, synthesis, model, planner):
        from langchain_core.exceptions import OutputParserException
        from langchain_core.messages import AIMessage
        from langchain_core.output_parsers import PydanticOutputParser

        from orchestrator.agents.project.schemas import ProjectAgentOutput
        from orchestrator.test_real_dispatch import mock_planner, task

        planner.return_value = mock_planner(task('task1', 'project.plan', {'task': 'Draft a store'}))
        build.return_value.invoke.return_value = {'messages': [AIMessage(content='Draft')]}
        parser = PydanticOutputParser(pydantic_object=ProjectAgentOutput)
        cases = [
            ('{"outcome":"specification","response":"private payload","specification":"wrong shape"}',
             'stop', 'model_type'),
            ('{"outcome":"specification","response":"private payload","specification":{"name":"Store"}}',
             'stop', 'missing'),
            ('private payload is not JSON', 'stop', 'invalid_json'),
            ('{"outcome":"specification","response":"private payload","specification":{"name":"Store',
             'length', 'missing'),
        ]
        thread = self.create()
        last_id = 0
        for raw, finish, category in cases:
            with self.subTest(category=category, finish=finish):
                with self.assertRaises(OutputParserException) as captured:
                    parser.parse(raw)
                synthesis.return_value.invoke.return_value = {
                    'parsed': None, 'parsing_error': captured.exception,
                    'raw': AIMessage(content=raw, response_metadata={'finish_reason': finish}),
                }
                response = self.send(thread, 'Prepare an unsaved Flutter specification.')
                self.assertEqual(response.status_code, 200, response.content)
                error = self.state(thread)['plan']['tasks'][0]['error']
                issues = error.pop('validation_issues', [])
                if category == 'model_type':
                    self.assertEqual(issues[0], {
                        'loc': ['specification'], 'type': 'model_type',
                        'expected_type': 'ProjectSpecification | null', 'received_type': 'string',
                    })
                self.assertEqual(error, {
                    'code': 'project_planning_failed', 'stage': 'output_validation',
                    'validation_codes': [category], 'finish_reason': finish,
                })
                response = self.client.get(f'{API}{thread}/events/?after={last_id}')
                with closing(response):
                    stream = iter(response.streaming_content)
                    for _ in range(9):
                        frame = next(stream).decode()
                        if '"type": "agent_failed"' in frame:
                            break
                    self.assertIn('"type": "agent_failed"', frame)
                    self.assertIn('"stage": "output_validation"', frame)
                    self.assertIn(f'"validation_codes": ["{category}"]', frame)
                    self.assertIn(f'"finish_reason": "{finish}"', frame)
                    self.assertNotIn('private payload', frame)
                    last_id = int(frame.splitlines()[0].removeprefix('id: '))

    @override_settings(AGENTIX_SUPERVISOR_CONSOLE_MODE='real',
                       AGENTIX_SUPERVISOR_CONSOLE_TEST_WRITES=True)
    def test_write_mode_refuses_other_database(self):
        response = self.post(API)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'test_database_required')
