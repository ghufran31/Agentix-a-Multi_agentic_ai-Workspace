from django.core.management.base import BaseCommand

from orchestrator.graph.checkpoints import open_postgres_checkpoints
from orchestrator.graph.console_journal import setup_console_tables


class Command(BaseCommand):
    help = 'Provision Supervisor checkpoint and developer console storage in PostgreSQL.'

    def handle(self, *args, **options):
        with open_postgres_checkpoints(setup=True) as store:
            setup_console_tables(store.connection)
        self.stdout.write(self.style.SUCCESS('Supervisor storage is ready.'))
