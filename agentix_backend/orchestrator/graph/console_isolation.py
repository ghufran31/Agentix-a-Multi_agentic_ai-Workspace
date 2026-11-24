"""Guard the disposable browser write workflow before touching business rows."""
from django.core.exceptions import ImproperlyConfigured
from django.db import connection


TEST_DATABASE = 'test_Agentix'


class ConsoleIsolationError(ImproperlyConfigured):
    pass


def require_test_orm():
    if connection.vendor != 'postgresql' or connection.settings_dict['NAME'] != TEST_DATABASE:
        raise ConsoleIsolationError('Console test writes require Django PostgreSQL test_Agentix.')
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database()')
        if cursor.fetchone()[0] != TEST_DATABASE:
            raise ConsoleIsolationError('The live Django connection is outside test_Agentix.')


def require_test_checkpoint(conn):
    if conn.execute('SELECT current_database() AS name').fetchone()['name'] != TEST_DATABASE:
        raise ConsoleIsolationError('The live checkpoint connection is outside test_Agentix.')
