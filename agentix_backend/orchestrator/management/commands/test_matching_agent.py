import sys

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from orchestrator.agents.matching.agent import execute_matching_task
from orchestrator.core.permissions import database_context


class Command(BaseCommand):
    help = 'Run a read-only Employee Matching Agent conversation.'

    def add_arguments(self, parser):
        parser.add_argument('--user-id', type=int)
        parser.add_argument('--company-id', type=int)
        parser.add_argument('--model')

    def handle(self, *args, **options):
        if 'test' not in settings.DATABASES['default']['NAME'].lower():
            raise CommandError('Matching console requires an isolated database whose name contains test.')
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, 'reconfigure'):
                stream.reconfigure(encoding='utf-8', errors='replace')
        user_id, company_id = options['user_id'], options['company_id']
        if bool(user_id) != bool(company_id):
            raise CommandError('Supply both --user-id and --company-id.')
        if not user_id:
            user_id = int(input('Test user ID: '))
            company_id = int(input('Authorized company ID: '))
        user = get_user_model().objects.filter(id=user_id).first()
        if not user:
            raise CommandError('Test user does not exist.')
        context = database_context(user, company_id, read_only=True)
        conversation = []
        last_matching = None
        self.stdout.write('Matching Agent console. Commands: :reset, :quit')
        while True:
            try:
                prompt = input('You: ').strip()
            except (EOFError, KeyboardInterrupt):
                self.stdout.write('')
                break
            if prompt in {':quit', 'quit', 'exit'}:
                break
            if prompt == ':reset':
                conversation.clear()
                last_matching = None
                self.stdout.write('Conversation reset.')
                continue
            if not prompt:
                continue
            self.stdout.write(f'You: {prompt}')
            result = execute_matching_task(context, prompt, conversation, options['model'],
                                           last_matching=last_matching)
            if result.success and result.structured_output:
                last_matching = result.structured_output
            self.stdout.write(f'Agent: {result.answer}')
            self.stdout.write(f'Tools: {", ".join(result.tool_names) or "(none)"}')
            if result.structured_output:
                self.stdout.write(result.structured_output.model_dump_json(indent=2))
            if result.validation_errors:
                self.stderr.write('; '.join(result.validation_errors))
            self.stdout.write(f'LLM requests: {result.model_requests}, responses: {result.model_responses}')
            if result.token_usage:
                self.stdout.write(f'Token usage: {result.token_usage}')
            if 'RateLimitError' in result.validation_errors:
                self.stderr.write('Groq returned HTTP 429. Ending live testing.')
                break
            conversation.extend([
                {'role': 'user', 'content': prompt},
                {'role': 'assistant', 'content': result.answer},
            ])
