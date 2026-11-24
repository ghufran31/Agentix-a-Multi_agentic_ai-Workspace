from django.core.management.base import BaseCommand

from orchestrator.graph.checkpoints import open_postgres_checkpoints


class Command(BaseCommand):
    help = 'Initialize the dedicated PostgreSQL schema for Supervisor checkpoints.'

    def handle(self, *args, **kwargs):
        with open_postgres_checkpoints(setup=True):
            pass
        self.stdout.write(self.style.SUCCESS('Supervisor checkpoint storage is ready.'))
