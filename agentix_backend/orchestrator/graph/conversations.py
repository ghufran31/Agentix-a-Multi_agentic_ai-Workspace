from dataclasses import replace
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import PermissionDenied
from langgraph.types import Command
from pydantic import ValidationError

from orchestrator.core.execution_context import ExecutionContext
from orchestrator.core.permissions import WRITER_ROLES, database_context
from projects.models import Project

from .approvals import ApprovalDecision, ApprovalRequest
from .builder import build_persistent_graph
from .events import stream_execution


class ConversationConflict(RuntimeError):
    pass


def _authenticated_scope(user, company_id):
    if not getattr(user, 'is_authenticated', False):
        raise PermissionDenied('Authentication is required.')
    active_user = get_user_model().objects.filter(pk=user.pk, is_active=True).first()
    return database_context(active_user, company_id, read_only=True)


class SupervisorConversations:
    """Server-side entry point; grants must come from application policy."""

    _salt = 'agentix.supervisor.thread.v1'

    def __init__(self, registry, store, *, grants, mode='mock', **graph_options):
        self._registry = registry
        self._store = store
        self._grants = grants
        self._mode = mode
        self._graph = build_persistent_graph(
            registry, checkpointer=store.saver, mode=mode, **graph_options,
        )

    def _context(self, user, company_id):
        scope = _authenticated_scope(user, company_id)
        caps, permissions = self._grants(scope)
        caps = set(caps)
        permissions = set(permissions)
        if scope.role not in WRITER_ROLES:
            caps.discard('database.create_project')
            permissions.discard('projects.write')
            permissions -= {'approvals.decide'}
        return ExecutionContext.from_django(
            scope,
            allowed_capabilities=frozenset(caps),
            permissions=frozenset(permissions),
        )

    def create_thread(self, user, company_id):
        context = self._context(user, company_id)
        return signing.dumps([self._mode, context.company_id, context.user_id, uuid4().hex],
                             salt=self._salt)

    def _config(self, thread, context):
        try:
            mode, company_id, user_id, identifier = signing.loads(thread, salt=self._salt)
        except (signing.BadSignature, TypeError, ValueError):
            raise PermissionDenied('Invalid conversation identifier.') from None
        if (mode, company_id, user_id) != (self._mode, context.company_id, context.user_id):
            raise PermissionDenied('The conversation is outside the authenticated scope.')
        return {'configurable': {'thread_id': f'agentix:{mode}:{company_id}:{user_id}:{identifier}'}}

    def read_state(self, thread, user, company_id):
        """Read a consistent saved checkpoint without taking the execution lock."""
        config = self._config(thread, self._context(user, company_id))
        snapshot = self._graph.get_state(config)
        return snapshot.values, bool(snapshot.next)

    def inspect(self, thread, user, company_id):
        config = self._config(thread, self._context(user, company_id))
        with self._store.lock(config['configurable']['thread_id']):
            return self._graph.get_state(config).values

    def turn(self, thread, user, company_id, request, *, project_id=None, project_requirements=None,
             execution_id=None, events=None, claim=None):
        if not isinstance(request, str) or not request.strip() or len(request) > 4000:
            raise ValueError('A request of 1 to 4000 characters is required.')
        context = self._context(user, company_id)
        config = self._config(thread, context)
        thread_id = config['configurable']['thread_id']
        with self._store.lock(thread_id):
            snapshot = self._graph.get_state(config)
            if claim is not None and claim(execution_id, check_only=True):
                return snapshot.values
            if snapshot.next:
                raise ConversationConflict('Resolve the current execution before starting a new turn.')
            data = {'request': request, 'execution_id': execution_id or uuid4().hex, 'thread_id': thread_id}
            effective_project = project_id if project_id is not None else snapshot.values.get('project_id')
            if effective_project is not None:
                project = Project.objects.filter(
                    pk=effective_project, company_id=context.company_id,
                ).only('deadline').first()
                if project is None:
                    raise PermissionDenied('The project is outside the authenticated scope.')
                context = replace(
                    context,
                    project_deadline=project.deadline.isoformat() if project.deadline else None,
                )
                data['project_id'] = effective_project
            if project_id is not None:
                data.update(project_id=project_id, project_requirements={})
            if project_requirements is not None:
                data['project_requirements'] = project_requirements
            if claim is not None:
                claim(data['execution_id'], check_only=False)
            return self._run(data, config, context, data['execution_id'], events)

    def _run(self, data, config, context, execution_id, events):
        if events is None:
            return self._graph.invoke(data, config, context=context, durability='sync')
        return stream_execution(self._graph, data, config, context, execution_id, events)

    def resume(self, thread, user, company_id, *, approval_id, execution_id, approved, events=None):
        try:
            decision = ApprovalDecision(approval_id=approval_id, approved=approved)
        except ValidationError:
            raise ConversationConflict('Invalid approval decision.') from None
        context = self._context(user, company_id)
        config = self._config(thread, context)
        thread_id = config['configurable']['thread_id']
        if 'approvals.decide' not in context.permissions:
            raise PermissionDenied('The current role or grants cannot decide approvals.')
        with self._store.lock(thread_id):
            snapshot = self._graph.get_state(config)
            pending = snapshot.values.get('pending_approvals', [])
            interrupts = [item for task in snapshot.tasks for item in task.interrupts]
            if len(pending) != 1 or len(interrupts) != 1 or pending[0] != interrupts[0].value:
                raise ConversationConflict('No matching approval is pending.')
            proposal = ApprovalRequest.model_validate(pending[0])
            if (proposal.approval_id != approval_id or proposal.execution_id != execution_id
                    or snapshot.values.get('execution_id') != execution_id
                    or proposal.thread_id != thread_id or proposal.status != 'pending'
                    or (proposal.user_id, proposal.company_id) != (context.user_id, context.company_id)):
                raise ConversationConflict('No matching approval is pending.')
            if proposal.capability not in self._registry.visible(context, allow_approvals=True):
                raise PermissionDenied('The capability is no longer authorized.')
            command = Command(resume={interrupts[0].id: decision.model_dump()})
            return self._run(command, config, context, execution_id, events)
