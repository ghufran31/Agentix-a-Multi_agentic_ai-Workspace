import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from orchestrator.agents.research.agent import execute_research


class Command(BaseCommand):
    help = 'Run a standalone web research conversation.'

    def add_arguments(self, parser):
        parser.add_argument('--question', action='append')

    def handle(self, *args, **options):
        if not os.getenv('TAVILY_API_KEY', '').strip() or not settings.GROQ_API_KEY:
            raise CommandError('Set TAVILY_API_KEY and GROQ_API_KEY before running live research.')
        history = []
        questions = iter(options['question']) if options['question'] else None
        while True:
            try:
                question = (next(questions) if questions is not None else input('Research: ')).strip()
            except (EOFError, KeyboardInterrupt, StopIteration):
                break
            if question == ':quit':
                break
            if question == ':reset':
                history.clear()
                continue
            if not question:
                continue
            if len(question) > 4000:
                raise CommandError('Research questions are limited to 4,000 characters.')
            result = execute_research(question, history)
            self.stdout.write(result.model_dump_json(indent=2, ensure_ascii=True))
            if set(result.errors) & {'RateLimitError', 'search_quota', 'missing_tavily_key', 'tavily_auth_failed'}:
                break
            if result.summary:
                history = [*history, ('user', question), ('assistant', result.summary.answer)][-6:]
