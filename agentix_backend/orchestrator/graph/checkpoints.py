from contextlib import contextmanager
from hashlib import blake2b
from os import environ
from threading import RLock

import psycopg
from django.db import connections
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg.rows import dict_row


class ThreadBusy(RuntimeError):
    pass


def _serializer():
    return JsonPlusSerializer(allowed_msgpack_modules=[
        ('orchestrator.core.plan_schemas', name)
        for name in ('ExecutionError', 'ExecutionPlan', 'ExecutionSummary', 'PlannedTask',
                     'OutputRef', 'PlannerDecision', 'TaskResult')
    ] + [('langchain_core.messages.human', 'HumanMessage'),
         ('langchain_core.messages.ai', 'AIMessage')])


class CheckpointStore:
    def __init__(self, saver, connection=None):
        self.saver = saver
        self.connection = connection
        self._lock = RLock()

    @contextmanager
    def lock(self, thread_id):
        with self._lock:
            if self.connection is None:
                yield
                return
            key = int.from_bytes(blake2b(thread_id.encode(), digest_size=8).digest(), 'big', signed=True)
            acquired = self.connection.execute(
                'SELECT pg_try_advisory_lock(%s) AS acquired', (key,),
            ).fetchone()['acquired']
            if not acquired:
                raise ThreadBusy('This conversation already has an active request.')
            try:
                yield
            finally:
                self.connection.execute('SELECT pg_advisory_unlock(%s)', (key,))


def memory_checkpoints():
    return CheckpointStore(InMemorySaver(serde=_serializer()))


@contextmanager
def open_postgres_checkpoints(*, setup=False):
    """Open a dedicated session. Run setup explicitly with a provisioning role."""
    dsn = environ.get('AGENTIX_CHECKPOINT_DSN')
    params = {}
    if not dsn:
        db = connections['default']
        if db.vendor != 'postgresql':
            raise ValueError('PostgreSQL checkpoint storage requires PostgreSQL settings.')
        params = db.get_connection_params().copy()
        for key in ('cursor_factory', 'context', 'prepare_threshold'):
            params.pop(key, None)
    with psycopg.connect(dsn or '', **params, autocommit=True, row_factory=dict_row) as conn:
        if setup:
            conn.execute('CREATE SCHEMA IF NOT EXISTS agentix_checkpoints')
        conn.execute('SET search_path TO agentix_checkpoints')
        saver = PostgresSaver(conn, serde=_serializer())
        if setup:
            saver.setup()
        yield CheckpointStore(saver, conn)
