import json
from unittest.mock import patch

import httpx
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from openrouter import OpenRouter
from pydantic import BaseModel

from orchestrator.core.llm_factory import LLMProviderError, get_llm, structured_llm


class TaskPlan(BaseModel):
    tasks: list[str]


def double(number: int) -> int:
    """Double an integer."""
    return number * 2


@override_settings(
    GROQ_API_KEY='mock-groq',
    OPENROUTER_API_KEY='mock-router',
    SPECIALIST_LLM_PROVIDER='groq',
    SPECIALIST_LLM_MODEL='specialist-model',
    SUPERVISOR_LLM_PROVIDER='openrouter',
    SUPERVISOR_LLM_MODEL='openrouter/free',
)
class LLMFactoryTests(SimpleTestCase):
    @patch('orchestrator.core.llm_factory.ChatGroq')
    def test_specialist_default_and_supervisor_are_independent(self, groq):
        self.assertIs(get_llm(), groq.return_value)
        self.assertEqual(groq.call_args.kwargs['model'], 'specialist-model')
        self.assertEqual(get_llm(role='supervisor').model, 'openrouter/free')

    def test_paid_models_and_unknown_providers_are_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            get_llm('openrouter/auto', provider='openrouter')
        with self.assertRaises(ImproperlyConfigured):
            get_llm(provider='unknown')

    @override_settings(OPENROUTER_API_KEY='')
    def test_missing_key(self):
        with self.assertRaisesMessage(ImproperlyConfigured, 'Set OPENROUTER_API_KEY'):
            get_llm(role='supervisor')

    def mock_model(self, handler):
        client = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(client.close)
        model = get_llm(role='supervisor')
        return model.model_copy(update={'client': OpenRouter(
            api_key='mock-router', server_url='https://openrouter.ai/api/v1', client=client,
        )})

    def test_chat_task_plan_and_tool_call(self):
        requests = []

        def handler(request):
            self.assertEqual(str(request.url), 'https://openrouter.ai/api/v1/chat/completions')
            payload = json.loads(request.content)
            requests.append(payload)
            self.assertEqual(payload['model'], 'openrouter/free')
            self.assertEqual(payload['provider'], {
                'require_parameters': True, 'allow_fallbacks': False,
            })
            message = {'role': 'assistant', 'content': 'READY'}
            if payload.get('tools'):
                name = payload['tools'][0]['function']['name']
                arguments = {'tasks': ['Verify inputs']} if name == 'TaskPlan' else {'number': 3}
                message = {'role': 'assistant', 'content': None, 'tool_calls': [{
                    'id': 'call_1', 'type': 'function',
                    'function': {'name': name, 'arguments': json.dumps(arguments)},
                }]}
            return httpx.Response(200, json={
                'id': 'gen-test', 'model': 'mock-free-model', 'created': 1,
                'object': 'chat.completion', 'system_fingerprint': None,
                'choices': [{'index': 0, 'message': message,
                             'finish_reason': 'tool_calls' if payload.get('tools') else 'stop'}],
                'usage': {'prompt_tokens': 5, 'completion_tokens': 3, 'total_tokens': 8},
            })

        model = self.mock_model(handler)
        self.assertEqual(model.invoke('Reply READY').content, 'READY')
        result = structured_llm(model, TaskPlan, include_raw=True).invoke('Plan verification')
        self.assertEqual(result['parsed'], TaskPlan(tasks=['Verify inputs']))
        self.assertEqual(result['raw'].usage_metadata['total_tokens'], 8)
        self.assertNotIn('response_format', requests[1])
        response = model.bind_tools([double], tool_choice='double').invoke('Double 3')
        call = response.tool_calls[0]
        self.assertEqual((call['name'], double(**call['args'])), ('double', 6))
        self.assertEqual(len(requests), 3)

    def test_rate_limit_and_unavailable_model_are_safe_and_not_retried(self):
        for status in (429, 404, 503):
            with self.subTest(status=status):
                count = []

                def handler(request):
                    count.append(request)
                    return httpx.Response(status, json={'error': {'message': 'sensitive body'}})

                with self.assertRaises(LLMProviderError) as captured:
                    self.mock_model(handler).invoke('Test')
                self.assertEqual(captured.exception.status_code, status)
                self.assertNotIn('sensitive body', str(captured.exception))
                self.assertEqual(len(count), 1)


    @override_settings(SUPERVISOR_LLM_PROVIDER='groq', SUPERVISOR_LLM_MODEL='openai/gpt-oss-120b',
                       SUPERVISOR_FALLBACK_ENABLED=False)
    def test_groq_supervisor_transport_and_strict_parsing(self):
        from groq import Groq
        from orchestrator.core.agent_registry import specialist_registry
        from orchestrator.core.execution_context import ExecutionContext
        from orchestrator.graph.builder import build_planning_graph

        cases = [
            ('{"private payload":', 'malformed_tool_arguments'),
            ('{"outcome":"plan","response":"Draft"}', 'pydantic_validation'),
            ('{"outcome":"direct_response","response":"Ready"}', None),
        ]
        context = ExecutionContext(1, 1, frozenset())
        graph = build_planning_graph(specialist_registry())
        for arguments, category in cases:
            with self.subTest(category=category):
                calls = []

                def handler(request):
                    payload = json.loads(request.content)
                    calls.append(payload)
                    self.assertNotIn('response_format', payload)
                    self.assertFalse(payload['parallel_tool_calls'])
                    self.assertEqual(payload['tool_choice']['function']['name'], 'PlannerDecision')
                    self.assertEqual(payload['tools'][0]['function']['parameters']['type'], 'object')
                    return httpx.Response(200, json={
                        'id': 'fixture', 'model': 'openai/gpt-oss-120b', 'created': 1,
                        'object': 'chat.completion',
                        'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {
                            'role': 'assistant', 'content': None, 'tool_calls': [{
                                'id': 'fixture-call', 'type': 'function',
                                'function': {'name': 'PlannerDecision', 'arguments': arguments},
                            }],
                        }}],
                        'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
                    })

                with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                    transport = Groq(api_key='fake', http_client=client, max_retries=0)
                    model = get_llm(role='supervisor').model_copy(update={
                        'client': transport.chat.completions,
                    })
                    with patch('orchestrator.graph.planner.get_llm', return_value=model):
                        result = graph.invoke({'request': 'Hello'}, context=context)
                self.assertEqual(len(calls), 1)
                if category:
                    self.assertEqual(result['errors'][0].code, 'invalid_model_output')
                    detail = result['metadata']['planner_diagnostic']
                    self.assertEqual(detail['stage'], 'structured_parse')
                    self.assertEqual(detail['category'], category)
                    self.assertEqual(detail['structured_output_method'], 'function_calling')
                    self.assertEqual(detail['finish_reason'], 'tool_calls')
                    self.assertEqual(detail['total_tokens'], 15)
                    self.assertNotIn('private payload', str(detail))
                else:
                    self.assertEqual(result['decision'].outcome, 'direct_response')
                    self.assertFalse(result['errors'])
