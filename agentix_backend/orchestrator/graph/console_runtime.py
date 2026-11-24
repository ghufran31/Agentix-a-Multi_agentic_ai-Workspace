"""Server-owned console capability policy and offline demonstration."""
from contextlib import contextmanager

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from langchain_core.messages import AIMessage

from orchestrator.core.agent_registry import Agent, AgentRegistry, Capability, specialist_registry
from orchestrator.core.plan_schemas import Contract

from .checkpoints import open_postgres_checkpoints
from .console_isolation import require_test_checkpoint, require_test_orm
from .console_journal import ConsoleJournal
from .conversations import SupervisorConversations


class DemoInput(Contract):
    topic: str


class DemoResult(Contract):
    topic: str
    simulated: bool = True


def _demo(inputs, predecessors, context):
    if inputs.topic == 'failure':
        raise ValueError('Demonstration failure.')
    return DemoResult(topic=inputs.topic)


class DemoPlanner:
    def invoke(self, messages):
        command = messages[-1].content.strip().lower()

        def task(task_id, *, topic, depends_on=(), capability='demo.preview'):
            return dict(task_id=task_id, capability=capability, description='Simulated preview',
                        inputs={'topic': topic}, depends_on=list(depends_on))

        decision = {'outcome': 'direct_response',
                    'response': 'Offline demo. Try “demo”, “demo approval”, or “demo failure”.'}
        if command in {'demo', 'demo approval', 'demo failure'}:
            tasks = [
                task('preview', topic='failure' if command == 'demo failure' else 'preview'),
                task('independent', topic='independent'),
            ]
            if command == 'demo approval':
                tasks.append(task('review', topic='review', depends_on=['preview'],
                                  capability='demo.approval'))
                tasks.append(task('after_review', topic='after review', depends_on=['review']))
            decision = {'outcome': 'plan', 'response': 'Prepared an offline demonstration.',
                        'plan': {'goal': 'Demonstrate Supervisor execution', 'tasks': tasks}}
        return {'parsed': decision, 'raw': AIMessage(content='')}


@contextmanager
def console_services(*, journal_only=False):
    mode = settings.AGENTIX_SUPERVISOR_CONSOLE_MODE
    test_writes = mode == 'real' and settings.AGENTIX_SUPERVISOR_CONSOLE_TEST_WRITES
    if test_writes:
        require_test_orm()
    if journal_only:
        with open_postgres_checkpoints() as store:
            if test_writes:
                require_test_checkpoint(store.connection)
            yield None, ConsoleJournal(store.connection)
        return
    if mode == 'mock':
        registry = AgentRegistry()
        registry.register(Agent('demo', 'Offline Demo', 'Simulated console operations', (
            Capability('demo.preview', DemoInput, DemoResult, mock_executor=_demo),
            Capability('demo.approval', DemoInput, DemoResult, approval_required=True, mock_executor=_demo),
        )))
        caps = {'demo.preview', 'demo.approval'}
        permissions = {'approvals.decide'}
        planner = DemoPlanner()
    elif mode == 'real':
        registry = specialist_registry()
        caps = {
            'database.get_project',
            'matching.rank',
            'project.plan',
            'research.search',
        }
        permissions = {'projects.read', 'workforce.read'}
        if test_writes:
            caps.add('database.create_project')
            permissions.update({'projects.write', 'approvals.decide'})
        planner = None
    else:
        raise ImproperlyConfigured('Supervisor console mode must be mock or real.')
    # The saver can be committing from a background thread while streaming yields.
    with open_postgres_checkpoints() as store, open_postgres_checkpoints() as journal_store:
        if test_writes:
            require_test_checkpoint(store.connection)
            require_test_checkpoint(journal_store.connection)
        yield SupervisorConversations(
            registry, store, mode=mode, planner=planner,
            grants=lambda scope: (caps, permissions),
        ), ConsoleJournal(journal_store.connection)
