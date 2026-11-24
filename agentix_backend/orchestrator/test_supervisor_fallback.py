from unittest.mock import Mock, patch

import httpx
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from google.genai.errors import ClientError, ServerError
from google.genai.types import GenerateContentResponse

from orchestrator.core.agent_registry import specialist_registry
from orchestrator.core.execution_context import ExecutionContext
from orchestrator.core.llm_factory import LLMProviderError, get_llm, structured_llm
from orchestrator.core.plan_schemas import PlannerDecision
from orchestrator.graph.builder import build_integrated_graph, build_planning_graph
from orchestrator.test_real_dispatch import research_result, task


DIRECT = {'parsed': {'outcome': 'direct_response', 'response': 'Ready.'}}


@override_settings(
    SUPERVISOR_LLM_PROVIDER='groq', SUPERVISOR_LLM_MODEL='openai/gpt-oss-120b',
    SUPERVISOR_FALLBACK_ENABLED=True,
    SUPERVISOR_FALLBACK_PROVIDERS=(('gemini', 'gemini-2.5-flash'), ('openrouter', 'openrouter/free')),
    GEMINI_FREE_TIER_CONFIRMED=True,
    GROQ_API_KEY='fake-groq', GOOGLE_API_KEY='fake-gemini', OPENROUTER_API_KEY='fake-router',
    SPECIALIST_LLM_PROVIDER='groq', SPECIALIST_LLM_MODEL='specialist-model', GROQ_MAX_RETRIES=2,
)
class SupervisorFallbackTests(SimpleTestCase):
    def setUp(self):
        self.registry = specialist_registry()
        self.context = ExecutionContext(1, 1, frozenset({'research.search'}))
        self.graph = build_planning_graph(self.registry)
        for provider in ('groq', 'gemini', 'openrouter'):
            self.addCleanup(cache.delete, f'agentix:supervisor:retry-after:{provider}')
        factory = patch('orchestrator.graph.planner.get_llm', side_effect=lambda *args, **kw: kw['provider'])
        self.providers = factory.start()
        self.addCleanup(factory.stop)
        binder = patch('orchestrator.graph.planner.structured_llm')
        self.invoke = binder.start().return_value.invoke
        self.addCleanup(binder.stop)

    def plan(self, chain):
        self.invoke.side_effect = chain
        return self.graph.invoke({'request': 'Research safely.'}, context=self.context)

    def order(self):
        return [call.kwargs['provider'] for call in self.providers.call_args_list]

    def test_primary_success(self):
        result = self.plan([DIRECT])
        self.assertEqual(self.order(), ['groq'])
        self.assertEqual(result['decision'].outcome, 'direct_response')

    def test_rate_limit_then_gemini(self):
        result = self.plan([LLMProviderError(429), DIRECT])
        self.assertEqual(self.order(), ['groq', 'gemini'])
        self.assertEqual(result['metadata']['provider'], 'gemini')
        self.assertEqual(result['metadata']['provider_attempts'][0]['status'], 'rate_limited')

    def test_temporary_failures_then_openrouter(self):
        result = self.plan([httpx.ReadTimeout('private'), ServerError(503, {}), DIRECT])
        self.assertEqual(self.order(), ['groq', 'gemini', 'openrouter'])
        self.assertEqual(result['metadata']['provider'], 'openrouter')
        self.assertNotIn('private', str(result['metadata']))

    def test_all_temporarily_unavailable(self):
        result = self.plan([LLMProviderError(503), ClientError(429, {}), LLMProviderError(429)])
        self.assertEqual(self.order(), ['groq', 'gemini', 'openrouter'])
        self.assertEqual(result['errors'][0].code, 'rate_limited')
        self.assertEqual(result['metadata']['invocations'], 3)

    @override_settings(GOOGLE_API_KEY='')
    def test_missing_gemini_key(self):
        result = self.plan([LLMProviderError(429), DIRECT])
        self.assertEqual(self.order(), ['groq', 'openrouter'])
        self.assertEqual(result['metadata']['provider_attempts'][1]['status'], 'missing_credentials')

    @override_settings(GEMINI_FREE_TIER_CONFIRMED=False)
    def test_unconfirmed_gemini_is_skipped(self):
        result = self.plan([LLMProviderError(503), DIRECT])
        self.assertEqual(self.order(), ['groq', 'openrouter'])
        self.assertEqual(result['metadata']['provider_attempts'][1]['status'], 'free_tier_not_confirmed')

    def test_invalid_output_is_terminal(self):
        result = self.plan([{'parsed': {'outcome': 'nonsense'}}])
        self.assertEqual(self.order(), ['groq'])
        self.assertEqual(result['errors'][0].code, 'invalid_model_output')

    def test_provider_authentication_failure_is_terminal(self):
        result = self.plan([LLMProviderError(403)])
        self.assertEqual(self.order(), ['groq'])
        self.assertEqual(result['metadata']['provider_status'], 403)

    def test_unauthorized_plan_is_terminal(self):
        result = self.plan([{'parsed': {'outcome': 'plan', 'response': 'Proposed', 'plan': {
            'goal': 'Draft', 'tasks': [task('write', 'project.plan', {'task': 'Draft'})],
        }}}])
        self.assertEqual(self.order(), ['groq'])
        self.assertEqual(result['errors'][0].code, 'invalid_plan')

    @override_settings(SUPERVISOR_FALLBACK_PROVIDERS=(('GROQ', 'other'), ('openrouter', 'openrouter/free')))
    def test_duplicates_are_never_invoked(self):
        self.plan([LLMProviderError(429), DIRECT])
        self.assertEqual(self.order(), ['groq', 'openrouter'])

    def test_retry_after_skips_provider_on_next_operation(self):
        self.plan([LLMProviderError(429, headers=httpx.Headers({'Retry-After': '30'})), DIRECT])
        self.providers.reset_mock()
        result = self.plan([DIRECT])
        self.assertEqual(self.order(), ['gemini'])
        self.assertEqual(result['metadata']['provider_attempts'][0]['status'], 'retry_after')

    @patch('orchestrator.core.specialist_dispatch._read_context')
    @patch('orchestrator.core.specialist_dispatch.execute_research')
    def test_only_successful_plan_executes_once(self, research, read_context):
        research.return_value = research_result('Research safely.')
        self.invoke.side_effect = [LLMProviderError(429), {
            'parsed': {'outcome': 'plan', 'response': 'Proposed', 'plan': {
                'goal': 'Research', 'tasks': [task('read', 'research.search', {'question': 'Research safely.'})],
            }},
        }]
        result = build_integrated_graph(self.registry, mode='real').invoke(
            {'request': 'Research safely.'}, context=self.context,
        )
        self.assertEqual(self.order(), ['groq', 'gemini'])
        research.assert_called_once_with('Research safely.')
        self.assertEqual(result['results']['read'].status, 'done')

    def test_specialist_and_supervisor_retry_policies_are_independent(self):
        self.assertEqual(get_llm().model_name, 'specialist-model')
        self.assertEqual(get_llm().max_retries, 2)
        self.assertEqual(get_llm(role='supervisor').max_retries, 0)

    def test_gemini_sdk_builds_json_schema_and_parses_pydantic(self):
        model = get_llm(provider='gemini')
        self.assertFalse(model.vertexai)
        self.assertEqual(model.max_retries, 0)
        response = GenerateContentResponse.model_validate({
            'candidates': [{'content': {'role': 'model', 'parts': [{
                'text': '{"outcome":"direct_response","response":"Ready."}',
            }]}, 'finish_reason': 'STOP'}],
        })
        client = Mock()
        client.models.generate_content.return_value = response
        model = model.model_copy(update={'client': client})
        result = structured_llm(model, PlannerDecision, include_raw=True).invoke('Hello')
        self.assertEqual(result['parsed'], PlannerDecision(**DIRECT['parsed']))
        config = client.models.generate_content.call_args.kwargs['config']
        self.assertEqual(config.response_mime_type, 'application/json')
        self.assertTrue(config.response_json_schema)
