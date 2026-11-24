from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test.signals import setting_changed
from httpx import NetworkError, RemoteProtocolError, TimeoutException
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_openrouter import ChatOpenRouter
from openrouter.errors import OpenRouterError


class LLMProviderError(RuntimeError):
    def __init__(self, status_code=None, *, headers=None, temporary=False):
        self.status_code = status_code
        self.retry_after = (headers or {}).get('retry-after')
        self.temporary = temporary
        detail = {
            401: 'authentication failed',
            402: 'insufficient credits',
            403: 'request forbidden',
            404: 'model or compatible endpoint unavailable',
            429: 'rate limit reached',
        }.get(status_code, 'request failed' if status_code else 'connection failed')
        super().__init__(f'OpenRouter {detail}' + (f' (HTTP {status_code})' if status_code else ''))


class AgentixOpenRouter(ChatOpenRouter):
    """Expose safe errors without provider response bodies or headers."""

    def _generate(self, *args, **kwargs):
        kwargs['retries'] = None
        try:
            return super()._generate(*args, **kwargs)
        except (OpenRouterError, NetworkError, RemoteProtocolError, TimeoutException) as exc:
            raise LLMProviderError(
                getattr(exc, 'status_code', None), headers=getattr(exc, 'headers', None),
                temporary=not isinstance(exc, OpenRouterError),
            ) from None

    async def _agenerate(self, *args, **kwargs):
        kwargs['retries'] = None
        try:
            return await super()._agenerate(*args, **kwargs)
        except (OpenRouterError, NetworkError, RemoteProtocolError, TimeoutException) as exc:
            raise LLMProviderError(
                getattr(exc, 'status_code', None), headers=getattr(exc, 'headers', None),
                temporary=not isinstance(exc, OpenRouterError),
            ) from None

    def _stream(self, *args, **kwargs):
        kwargs['retries'] = None
        try:
            yield from super()._stream(*args, **kwargs)
        except (OpenRouterError, NetworkError, RemoteProtocolError, TimeoutException) as exc:
            raise LLMProviderError(
                getattr(exc, 'status_code', None), headers=getattr(exc, 'headers', None),
                temporary=not isinstance(exc, OpenRouterError),
            ) from None

    async def _astream(self, *args, **kwargs):
        kwargs['retries'] = None
        try:
            async for chunk in super()._astream(*args, **kwargs):
                yield chunk
        except (OpenRouterError, NetworkError, RemoteProtocolError, TimeoutException) as exc:
            raise LLMProviderError(
                getattr(exc, 'status_code', None), headers=getattr(exc, 'headers', None),
                temporary=not isinstance(exc, OpenRouterError),
            ) from None


def resolve_llm_selection(model_name=None, *, provider=None, role='specialist'):
    if role not in {'specialist', 'supervisor'}:
        raise ImproperlyConfigured('Unknown LLM role.')
    role_provider = getattr(settings, f'{role.upper()}_LLM_PROVIDER', 'groq')
    selected = (provider if provider is not None else role_provider).strip().lower()
    if selected not in {'groq', 'openrouter', 'gemini'}:
        raise ImproperlyConfigured('LLM provider must be groq, gemini, or openrouter.')
    role_model = getattr(settings, f'{role.upper()}_LLM_MODEL', '')
    if provider is not None and selected != role_provider.strip().lower():
        role_model = ''
    model = (model_name or role_model or getattr(settings, f'{selected.upper()}_MODEL_NAME', '')).strip()
    if not model:
        raise ImproperlyConfigured(f'Configure a model for the {selected} provider.')
    return selected, model


@lru_cache(maxsize=8)
def get_llm(model_name=None, *, provider=None, role='specialist'):
    selected, model = resolve_llm_selection(model_name, provider=provider, role=role)
    if selected == 'gemini':
        key = settings.GOOGLE_API_KEY.strip()
        if not key:
            raise ImproperlyConfigured('Set GOOGLE_API_KEY in the repository-root .env file or environment.')
        return ChatGoogleGenerativeAI(
            model=model, google_api_key=key, vertexai=False, temperature=0,
            timeout=settings.GEMINI_REQUEST_TIMEOUT, max_retries=0,
        )
    if selected == 'openrouter':
        key = settings.OPENROUTER_API_KEY.strip()
        if not key:
            raise ImproperlyConfigured('Set OPENROUTER_API_KEY in the repository-root .env file or environment.')
        if not (model == 'openrouter/free' or model.endswith(':free')):
            raise ImproperlyConfigured('OpenRouter requires an explicit :free model or openrouter/free.')
        return AgentixOpenRouter(
            api_key=key,
            base_url='https://openrouter.ai/api/v1',
            model=model,
            temperature=0,
            timeout=settings.OPENROUTER_TIMEOUT_MS,
            max_tokens=settings.OPENROUTER_MAX_TOKENS,
            max_retries=0,
            openrouter_provider={'require_parameters': True, 'allow_fallbacks': False},
            streaming=False,
        )
    api_key = getattr(settings, 'GROQ_API_KEY', '')
    if not api_key:
        raise ImproperlyConfigured(
            'Set GROQ_API_KEY in the repository-root .env file or environment.'
        )
    return ChatGroq(
        api_key=api_key,
        model=model,
        temperature=settings.GROQ_TEMPERATURE,
        timeout=settings.GROQ_REQUEST_TIMEOUT,
        max_retries=0 if role == 'supervisor' else settings.GROQ_MAX_RETRIES,
        max_tokens=getattr(settings, 'GROQ_MAX_TOKENS', 16384),
    )


def supervisor_structured_method(provider):
    return 'function_calling' if provider in {'groq', 'openrouter'} else 'json_schema'


def structured_llm(model, schema, *, include_raw=False):
    if isinstance(model, ChatGoogleGenerativeAI):
        return model.with_structured_output(schema, method='json_schema', include_raw=include_raw)
    from .plan_schemas import PlannerDecision

    if schema is PlannerDecision and isinstance(model, ChatGroq):
        return model.with_structured_output(
            schema, method=supervisor_structured_method('groq'), include_raw=include_raw,
            parallel_tool_calls=False,
        )
    method = 'function_calling' if isinstance(model, ChatOpenRouter) else 'json_schema'
    return model.with_structured_output(schema, method=method, strict=False, include_raw=include_raw)


def _clear_factory_cache(setting, **kwargs):
    if setting.startswith(('GROQ_', 'OPENROUTER_', 'GEMINI_', 'GOOGLE_API_KEY', 'SPECIALIST_LLM_', 'SUPERVISOR_LLM_')):
        get_llm.cache_clear()


setting_changed.connect(_clear_factory_cache)
