from getpass import getpass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from orchestrator.agents.database.agent import execute_database_task
from orchestrator.core.permissions import database_context


class Command(BaseCommand):
    help = 'Run an isolated interactive Database Agent conversation.'

    def add_arguments(self, parser):
        parser.add_argument('--user-id', type=int)
        parser.add_argument('--company-id', type=int)
        parser.add_argument('--allow-live-writes', action='store_true')
        parser.add_argument('--model')

    def handle(self, *args, **options):
        database_name = settings.DATABASES['default']['NAME'].lower()
        is_test_database = 'test' in database_name
        if not is_test_database:
            raise CommandError(
                'The testing console refuses a database that is not clearly isolated. '
                'Use a PostgreSQL database name containing "test".'
            )

        user_id = options['user_id']
        company_id = options['company_id']
        if not user_id:
            user_id = int(input('Known test user ID: ').strip())
        if not company_id:
            company_id = int(input('Known test company ID: ').strip())

        user = get_user_model().objects.filter(id=user_id).first()
        if not user:
            raise CommandError('The test user ID does not exist.')
        context = database_context(
            user,
            company_id,
            read_only=not options['allow_live_writes'],
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'Database Agent console | company={company_id} '
                f'read_only={not options["allow_live_writes"]}'
            )
        )
        self.stdout.write('Type "exit" or "quit" to leave.\n')
        conversation = []
        while True:
            try:
                message = input('You: ').strip()
            except (EOFError, KeyboardInterrupt):
                self.stdout.write('')
                break
            if not message:
                continue
            if message.lower() in ('exit', 'quit'):
                break
            try:
                result = execute_database_task(
                    context,
                    message,
                    conversation=conversation,
                    model_name=options['model'],
                    read_only=not options['allow_live_writes'],
                )
            except Exception as exc:
                self.stderr.write(self.style.ERROR(
                    f'Agent execution failed: {type(exc).__name__}'
                ))
                continue

            conversation.append({'role': 'user', 'content': message})
            conversation.append({'role': 'assistant', 'content': result.answer})
            self.stdout.write(f'Agent: {result.answer}')
            self.stdout.write(f'Selected tools: {", ".join(result.tool_names) or "(none)"}')
            for execution in result.execution_results:
                status = 'SUCCESS' if execution.success else 'FAILURE'
                self.stdout.write(f'{status}: {execution.operation}')
                self.stdout.write(str(execution.data))
            if result.pending_approval:
                self.stdout.write(
                    self.style.WARNING(
                        'Pending approval: '
                        + str(result.pending_approval)
                    )
                )
