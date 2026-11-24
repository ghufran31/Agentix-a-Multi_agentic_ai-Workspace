import json
import sys
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from orchestrator.agents.project.agent import execute_project_task
from orchestrator.core.llm_factory import resolve_llm_selection
from orchestrator.core.permissions import database_context


SCENARIOS = {
    'basic': ['I want to build an e-commerce application.'],
    'detailed': [
        'Create a complete development plan for a food delivery application with '
        'Flutter, Django REST Framework, PostgreSQL, customer and rider apps, order '
        'tracking, payments, an admin dashboard, and a four-month deadline.'
    ],
    'technology': [
        'I want to create a social media application. Choose the best technology '
        'stack for mobile, backend, and database.'
    ],
    'memory': [
        'I want to build a university management system.',
        'Use Flutter for the frontend.',
        'Use Django for the backend and PostgreSQL for the database.',
        'Generate the complete project specification.',
        'Change the backend from Django to FastAPI.',
        'What employees and technical skills would we need to develop this project?',
        'Divide the project into development phases and milestones.',
    ],
    'persistence': ['Save this project to the database and give me its ID.'],
    'long': [
        'Plan a multi-tenant healthcare appointment platform for patients, doctors, '
        'clinic administrators, and support staff. It needs web and Flutter mobile '
        'clients, Django REST Framework, PostgreSQL, authentication with MFA, doctor '
        'search, appointment scheduling and cancellation, reminders, audit logs, '
        'payments, refunds, an admin dashboard, analytics, data export, WCAG-friendly '
        'interfaces, encryption, 99.9% availability, automated tests, Docker delivery, '
        'and completion within six months. Include backend, mobile, QA, security, '
        'DevOps, and product roles. Assume external payment and notification providers '
        'but flag compliance jurisdiction as missing.'
    ],
}


class Command(BaseCommand):
    help = 'Run the independent Project Agent console or live Groq scenarios.'

    def add_arguments(self, parser):
        parser.add_argument('--model')
        parser.add_argument('--scenario', choices=[*SCENARIOS, 'all'])
        parser.add_argument('--user-id', type=int)
        parser.add_argument('--company-id', type=int)
        parser.add_argument('--summary', action='store_true')
        parser.add_argument('--report-file')

    def _context(self, options):
        user_id, company_id = options['user_id'], options['company_id']
        if bool(user_id) != bool(company_id):
            raise CommandError('--user-id and --company-id must be supplied together.')
        if not user_id:
            return None
        user = get_user_model().objects.filter(id=user_id).first()
        if not user:
            raise CommandError('The user ID does not exist.')
        return database_context(user, company_id, read_only=True)

    def _run_turn(self, context, message, conversation, model, verbose=True):
        self.stdout.write(f'User: {message}')
        result = execute_project_task(
            context, message, conversation=conversation, model_name=model,
        )
        self.stdout.write(f'Agent: {result.answer}')
        self.stdout.write(f'Tools: {", ".join(result.tool_names) or "(none)"}')
        if verbose:
            for execution in result.tool_executions:
                self.stdout.write(f'  {execution.name} input={json.dumps(execution.input, default=str)}')
                self.stdout.write(f'  {execution.name} output={json.dumps(execution.output, default=str)}')
            if result.structured_output:
                self.stdout.write('Structured output:')
                self.stdout.write(result.structured_output.model_dump_json(indent=2))
        if result.validation_errors:
            self.stderr.write('Validation/errors: ' + '; '.join(result.validation_errors))
        self.stdout.write(f'Validation: {"PASS" if result.success else "FAIL"}')
        self.stdout.write(f'Model API responses observed: {result.model_calls}\n')
        self.stdout.write(f'Model API requests attempted: {result.model_requests}\n')
        conversation.extend([
            {'role': 'user', 'content': message},
            {'role': 'assistant', 'content': result.answer},
        ])
        if hasattr(self, '_report_records'):
            self._report_records.append({
                'user_message': message,
                'agent_response': result.answer,
                'tool_names': result.tool_names,
                'tool_executions': [
                    item.model_dump(mode='json') for item in result.tool_executions
                ],
                'structured_output': (
                    result.structured_output.model_dump(mode='json')
                    if result.structured_output else None
                ),
                'validation_passed': result.success,
                'validation_errors': result.validation_errors,
                'model_api_responses': result.model_calls,
                'model_api_requests': result.model_requests,
            })
        return result

    def _write_report(self, report_file, model):
        if not report_file:
            return
        path = Path(report_file).resolve()
        repository_root = settings.BASE_DIR.parent.resolve()
        if not path.is_relative_to(repository_root):
            raise CommandError('The report file must be inside the repository.')
        if not path.parent.exists():
            raise CommandError('The report parent directory does not exist.')
        payload = {
            'model': resolve_llm_selection(model)[1],
            'contains_secrets': False,
            'turns': self._report_records,
            'total_model_api_responses': sum(
                item['model_api_responses'] for item in self._report_records
            ),
            'total_model_api_requests': sum(
                item['model_api_requests'] for item in self._report_records
            ),
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8'
        )
        self.stdout.write(self.style.SUCCESS(f'Sanitized report written to {path}'))

    def handle(self, *args, **options):
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, 'reconfigure'):
                stream.reconfigure(encoding='utf-8', errors='replace')
        context = self._context(options)
        model = options['model']
        scenario = options['scenario']
        self._report_records = []
        if scenario:
            names = list(SCENARIOS) if scenario == 'all' else [scenario]
            total_calls = 0
            total_requests = 0
            for name in names:
                self.stdout.write(self.style.MIGRATE_HEADING(f'=== Scenario: {name} ==='))
                conversation = []
                for message in SCENARIOS[name]:
                    result = self._run_turn(
                        context, message, conversation, model,
                        verbose=not options['summary'],
                    )
                    total_calls += result.model_calls
                    total_requests += result.model_requests
            self.stdout.write(self.style.SUCCESS(
                f'Observed real model API responses across scenarios: {total_calls}'
            ))
            self.stdout.write(self.style.SUCCESS(
                f'Attempted real model API requests across scenarios: {total_requests}'
            ))
            self._write_report(options['report_file'], model)
            return

        self.stdout.write(self.style.SUCCESS('Project Agent interactive console'))
        self.stdout.write(
            'Commands: :reset, :structured, :tools, :scenario NAME, :scenarios, :quit'
        )
        conversation = []
        last_result = None
        while True:
            try:
                message = input('You: ').strip()
            except (EOFError, KeyboardInterrupt):
                self.stdout.write('')
                break
            if not message:
                continue
            if message in (':quit', 'exit', 'quit'):
                break
            if message == ':reset':
                conversation = []
                last_result = None
                self.stdout.write('Conversation reset.')
                continue
            if message == ':structured':
                self.stdout.write(
                    last_result.structured_output.model_dump_json(indent=2)
                    if last_result and last_result.structured_output else '(none)'
                )
                continue
            if message == ':tools':
                self.stdout.write(
                    ', '.join(last_result.tool_names) if last_result else '(none)'
                )
                continue
            if message == ':scenarios':
                self.stdout.write(', '.join(SCENARIOS))
                continue
            if message.startswith(':scenario '):
                name = message.split(maxsplit=1)[1]
                if name not in SCENARIOS:
                    self.stderr.write('Unknown scenario.')
                    continue
                conversation = []
                for scenario_message in SCENARIOS[name]:
                    last_result = self._run_turn(
                        context, scenario_message, conversation, model
                    )
                continue
            last_result = self._run_turn(context, message, conversation, model)
        self._write_report(options['report_file'], model)
