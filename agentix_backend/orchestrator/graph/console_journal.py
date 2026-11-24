"""Replayable console events stored alongside graph checkpoints."""
from psycopg.types.json import Jsonb


def setup_console_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS console_threads (
            thread text PRIMARY KEY, user_id bigint NOT NULL, company_id bigint NOT NULL,
            mode text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS console_threads_owner
        ON console_threads (user_id, company_id, mode, created_at DESC)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS console_events (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            thread text NOT NULL REFERENCES console_threads(thread), event jsonb NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS console_events_thread ON console_events (thread, id)
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS console_events_submission
        ON console_events (thread, (event->>'execution_id'))
        WHERE event->>'type' = 'submission_accepted'
    """)


class ConsoleJournal:
    def __init__(self, connection):
        self.connection = connection

    def create(self, thread, user_id, company_id, mode):
        self.connection.execute(
            'INSERT INTO console_threads (thread, user_id, company_id, mode) VALUES (%s, %s, %s, %s)',
            (thread, user_id, company_id, mode),
        )

    def list(self, user_id, company_id, mode):
        return self.connection.execute(
            'SELECT thread, created_at FROM console_threads WHERE user_id=%s AND company_id=%s '
            'AND mode=%s ORDER BY created_at DESC, thread LIMIT 100', (user_id, company_id, mode),
        ).fetchall()

    def owns(self, thread, user_id, company_id, mode):
        return self.connection.execute(
            'SELECT 1 FROM console_threads WHERE thread=%s AND user_id=%s AND company_id=%s AND mode=%s',
            (thread, user_id, company_id, mode),
        ).fetchone() is not None

    def acknowledged(self, thread, execution_id):
        return self.connection.execute(
            "SELECT 1 FROM console_events WHERE thread=%s AND event->>'type'='submission_accepted' "
            "AND event->>'execution_id'=%s", (thread, execution_id),
        ).fetchone() is not None

    def append(self, thread, event):
        self.connection.execute(
            'INSERT INTO console_events (thread, event) VALUES (%s, %s)', (thread, Jsonb(event)),
        )

    def after(self, thread, cursor):
        return self.connection.execute(
            "SELECT id, event FROM console_events WHERE thread=%s AND id>%s "
            "AND event->>'type' <> 'submission_accepted' ORDER BY id LIMIT 100", (thread, cursor),
        ).fetchall()
