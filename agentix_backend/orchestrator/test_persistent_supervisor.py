from contextlib import ExitStack
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase
from langchain_core.messages import AIMessage

from companies.models import Company, CompanyUser
from orchestrator.core.agent_registry import Agent, AgentRegistry, Capability
from orchestrator.core.permissions import DatabaseExecutionContext, WRITER_ROLES
from orchestrator.graph.approvals import operation_key
from orchestrator.graph.checkpoints import ThreadBusy, memory_checkpoints, open_postgres_checkpoints
from orchestrator.graph.conversations import ConversationConflict, SupervisorConversations
from orchestrator.test_integrated_graph import Number, task


class ConversationFixtures:
    def setUp(self):
        super().setUp()
        self.user = SimpleNamespace(pk=1, is_authenticated=True)
        self.role = WRITER_ROLES[0]
        self.scopes = {(1, 10), (2, 10), (1, 20)}
        self.caps = {'mock.run', 'mock.approval'}
        self.worker = Mock(side_effect=lambda inputs, predecessors, context: inputs)
        self.planner = Mock()
        self.registry = AgentRegistry()
        self.registry.register(Agent('mock', 'Mock', 'Fixture', (
            Capability('mock.run', Number, Number, mock_executor=self.worker),
            Capability('mock.approval', Number, Number, approval_required=True,
                       mock_executor=self.worker),
        )))
        self.scope_patch = patch('orchestrator.graph.conversations._authenticated_scope',
                        side_effect=self.scope)
        self.scope_patch.start()
        self.addCleanup(self.scope_patch.stop)

    def scope(self, user, company_id):
        if not user.is_authenticated or (user.pk, company_id) not in self.scopes:
            raise PermissionDenied
        return DatabaseExecutionContext(user, SimpleNamespace(pk=company_id), self.role, True)

    def service(self, store, **options):
        return SupervisorConversations(
            self.registry, store, planner=self.planner,
            grants=lambda scope: (self.caps, {'approvals.decide'}), **options,
        )

    def plan(self, gated=True):
        tasks = [task('first', 7)]
        if gated:
            tasks += [
                task('gate', dependencies=['first'], reference='first', capability='mock.approval'),
                task('after', dependencies=['gate'], reference='gate'),
                task('independent', 9),
            ]
        self.planner.invoke.return_value = {
            'parsed': {'outcome': 'plan', 'response': 'Proposed plan',
                       'plan': {'goal': 'Fixture goal', 'tasks': tasks}},
            'raw': AIMessage(content=''),
        }

    def resume(self, service, thread, proposal, **overrides):
        params = {'approval_id': proposal['approval_id'], 'execution_id': proposal['execution_id'],
                  'approved': True, **overrides}
        return service.resume(thread, self.user, getattr(self, 'company_id', 10), **params)


class PersistentSupervisorTests(ConversationFixtures, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.store = memory_checkpoints()
        self.app = self.service(self.store)
        self.thread = self.app.create_thread(self.user, 10)

    def pause(self):
        self.plan()
        state = self.app.turn(self.thread, self.user, 10, 'Run the fixture')
        self.assertEqual(set(state['results']), {'first', 'independent'})
        proposal, = state['pending_approvals']
        self.assertEqual(proposal['status'], 'pending')
        self.assertEqual(proposal['inputs'], {'value': 7})
        self.assertEqual(self.worker.call_count, 2)
        return proposal

    def test_restart_approval_and_replay(self):
        proposal = self.pause()
        app = self.service(self.store)
        self.assertEqual(app.inspect(self.thread, self.user, 10)['pending_approvals'], [proposal])
        result = self.resume(app, self.thread, proposal)
        self.assertEqual(result['execution_summary'].status, 'done', result['errors'])
        self.assertEqual(result['results']['after'].output, {'value': 7})
        self.assertEqual(result['approval_records']['gate']['status'], 'approved')
        self.assertEqual(self.worker.call_count, 4)
        with self.assertRaises(ConversationConflict):
            self.resume(app, self.thread, proposal)
        self.assertEqual(self.worker.call_count, 4)

    def test_rejection_blocks_dependent_and_preserves_unrelated(self):
        proposal = self.pause()
        result = self.resume(self.app, self.thread, proposal, approved=False)
        self.assertEqual(result['results']['gate'].error.code, 'approval_rejected')
        self.assertEqual(result['results']['after'].error.code, 'prerequisite_failed')
        self.assertEqual(result['results']['independent'].output, {'value': 9})
        self.assertEqual(result['execution_summary'].status, 'partial')
        self.assertEqual(self.worker.call_count, 2)

    def test_expired_approval(self):
        proposal = self.pause()
        with patch('orchestrator.graph.approvals.time', return_value=proposal['expires_at']):
            result = self.resume(self.app, self.thread, proposal)
        self.assertEqual(result['approval_records']['gate']['status'], 'expired')
        self.assertEqual(self.worker.call_count, 2)

    def test_invalid_approvals_and_pending_turn(self):
        proposal = self.pause()
        for overrides in ({'execution_id': 'forged'}, {'approval_id': 'forged'}, {'approved': 'yes'}):
            with self.assertRaises(ConversationConflict):
                self.resume(self.app, self.thread, proposal, **overrides)
        with self.assertRaises(ConversationConflict):
            self.app.turn(self.thread, self.user, 10, 'Another turn')
        self.assertEqual(self.worker.call_count, 2)
        self.assertEqual(self.app.inspect(self.thread, self.user, 10)['pending_approvals'], [proposal])

    def test_role_permission_and_membership_rechecked(self):
        proposal = self.pause()
        self.role = 'employee'
        with self.assertRaises(PermissionDenied):
            self.resume(self.app, self.thread, proposal)
        self.role = WRITER_ROLES[0]
        self.caps.remove('mock.approval')
        with self.assertRaises(PermissionDenied):
            self.resume(self.app, self.thread, proposal)
        self.scopes.clear()
        with self.assertRaises(PermissionDenied):
            self.app.inspect(self.thread, self.user, 10)
        self.assertEqual(self.worker.call_count, 2)

    def test_thread_user_company_and_mode_isolation(self):
        self.pause()
        other = self.app.create_thread(self.user, 10)
        self.assertEqual(self.app.inspect(other, self.user, 10), {})
        for identifier, user, company in (
            (self.thread, SimpleNamespace(pk=2, is_authenticated=True), 10),
            (self.thread, self.user, 20), (self.thread + 'tampered', self.user, 10),
        ):
            with self.assertRaises(PermissionDenied):
                self.app.inspect(identifier, user, company)
        with self.assertRaises(PermissionDenied):
            self.service(self.store, mode='planning').inspect(self.thread, self.user, 10)

    @patch('orchestrator.graph.conversations.Project.objects')
    def test_followups_preserve_project_history_and_bound_messages(self, projects):
        projects.filter.return_value.only.return_value.first.return_value = SimpleNamespace(
            deadline=None,
        )
        self.plan(gated=False)
        self.app.turn(self.thread, self.user, 10, 'First', project_id=4,
                      project_requirements={'language': 'Python'})
        app = self.service(self.store)
        for index in range(13):
            state = app.turn(self.thread, self.user, 10, f'Follow-up {index}')
        self.assertEqual(len(state['messages']), 24)
        self.assertEqual(state['messages'][-2].content, 'Follow-up 12')
        self.assertEqual(state['previous_results']['first'].output, {'value': 7})
        self.assertEqual(state['project_requirements'], {'language': 'Python'})
        projects.filter.assert_called_with(pk=4, company_id=10)
        self.assertLessEqual(len(self.planner.invoke.call_args.args[0]), 15)

    @patch('orchestrator.graph.conversations.Project.objects')
    def test_turn_passes_saved_project_deadline_as_trusted_context(self, projects):
        projects.filter.return_value.only.return_value.first.return_value = SimpleNamespace(
            deadline=date(2027, 1, 15),
        )
        self.plan(gated=False)
        self.app.turn(self.thread, self.user, 10, 'Use this project', project_id=4)
        messages = self.planner.invoke.call_args.args[0]
        self.assertIn('"trusted_project_deadline": "2027-01-15"', messages[1].content)

    def test_planning_and_real_modes_do_not_execute_mock_or_approval(self):
        self.plan(gated=False)
        planning = self.service(self.store, mode='planning')
        thread = planning.create_thread(self.user, 10)
        result = planning.turn(thread, self.user, 10, 'Plan only')
        self.assertEqual(result['decision'].outcome, 'plan')
        self.plan()
        real = self.service(self.store, mode='real')
        thread = real.create_thread(self.user, 10)
        result = real.turn(thread, self.user, 10, 'Real mode')
        self.assertEqual(result['decision'].outcome, 'planning_error')
        self.worker.assert_not_called()

    def test_idempotency_scope(self):
        identity = ('thread', 'run', 'task', 'cap')
        key = operation_key(*identity, {'a': 1, 'b': 2})
        self.assertEqual(key, operation_key(*identity, {'b': 2, 'a': 1}))
        self.assertNotEqual(key, operation_key(*identity, {'a': 2, 'b': 2}))
        self.assertNotEqual(key, operation_key('thread', 'other-run', 'task', 'cap', {'a': 1, 'b': 2}))


class PostgresCheckpointTests(ConversationFixtures, TransactionTestCase):
    def test_disposable_postgres_reopen_and_resume(self):
        if connection.vendor != 'postgresql':
            self.skipTest('Requires a disposable PostgreSQL test database.')
        if not connection.settings_dict['NAME'].startswith('test_agentix_phase05_'):
            self.skipTest('Requires a dedicated test_agentix_phase05_ database.')
        self.scope_patch.stop()
        self.user = get_user_model().objects.create_user(username='phase05-owner')
        company = Company.objects.create(created_by_user=self.user, name='Disposable company')
        self.company_id = company.pk
        membership = CompanyUser.objects.create(
            user=self.user, company=company, role=CompanyUser.Role.OWNER,
        )
        self.plan()
        with patch.dict('os.environ', {'AGENTIX_CHECKPOINT_DSN': ''}), ExitStack() as stack:
            store = stack.enter_context(open_postgres_checkpoints(setup=True))
            app = self.service(store)
            thread = app.create_thread(self.user, company.pk)
            with open_postgres_checkpoints() as competing_store, store.lock('phase05-lock-fixture'):
                with self.assertRaises(ThreadBusy), competing_store.lock('phase05-lock-fixture'):
                    self.fail('A second PostgreSQL session acquired the same thread lock.')
            first = app.turn(thread, self.user, company.pk, 'Persist a pending approval')
            proposal, = first['pending_approvals']
            stack.close()
            store = stack.enter_context(open_postgres_checkpoints())
            restarted = self.service(store)
            membership.role = CompanyUser.Role.MEMBER
            membership.save(update_fields=['role'])
            with self.assertRaises(PermissionDenied):
                self.resume(restarted, thread, proposal)
            membership.role = CompanyUser.Role.OWNER
            membership.save(update_fields=['role'])
            result = self.resume(restarted, thread, proposal)
            self.assertEqual(result['execution_summary'].status, 'done', result['errors'])
            self.assertEqual(result['results']['after'].output, {'value': 7})
            self.assertEqual(self.worker.call_count, 4)
            self.plan(gated=False)
            continued = restarted.turn(thread, self.user, company.pk, 'Continue after resume')
            self.assertEqual(continued['previous_results']['after'].output, {'value': 7})
            get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
            with self.assertRaises(PermissionDenied):
                restarted.inspect(thread, self.user, company.pk)
