"""Bounded provider routing for Supervisor planning."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from google.genai.errors import APIError as GoogleAPIError
from groq import APIConnectionError, APIError
from httpx import NetworkError, RemoteProtocolError, TimeoutException
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError

from .llm_factory import LLMProviderError, resolve_llm_selection


PROVIDER_EXCEPTIONS = (
    APIError, GoogleAPIError, ChatGoogleGenerativeAIError, LLMProviderError,
    NetworkError, RemoteProtocolError, TimeoutException, TimeoutError, ConnectionError,
)
TEMPORARY_STATUS = {408, 429, 500, 502, 503, 504}
KEY_SETTINGS = {'groq': 'GROQ_API_KEY', 'gemini': 'GOOGLE_API_KEY',
                'openrouter': 'OPENROUTER_API_KEY'}


def provider_failure(exc):
    if isinstance(exc, ChatGoogleGenerativeAIError) and isinstance(exc.__cause__, GoogleAPIError):
        exc = exc.__cause__
    status = getattr(exc, 'status_code', None)
    if isinstance(exc, GoogleAPIError):
        status = exc.code
    status = status if type(status) is int else None
    temporary = status in TEMPORARY_STATUS or (
        status is None and (
            isinstance(exc, (APIConnectionError, NetworkError, RemoteProtocolError,
                             TimeoutException, TimeoutError, ConnectionError))
            or getattr(exc, 'temporary', False)
        )
    )
    code = 'rate_limited' if status == 429 else 'provider_unavailable' if temporary else 'provider_error'
    return status, code, temporary


def _retry_after(exc):
    if isinstance(exc, ChatGoogleGenerativeAIError) and isinstance(exc.__cause__, GoogleAPIError):
        exc = exc.__cause__
    headers = getattr(exc, 'headers', None)
    if headers is None:
        headers = getattr(getattr(exc, 'response', None), 'headers', {})
    value = getattr(exc, 'retry_after', None) or (headers or {}).get('retry-after')
    if not value:
        return 0
    try:
        if value.isdecimal():
            return int(value)
        return max(0, int((parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()) + 1)
    except (TypeError, ValueError, OverflowError):
        return 0


def _free_fallback(provider, model):
    if provider == 'openrouter':
        return model == 'openrouter/free' or model.endswith(':free')
    if provider == 'gemini':
        return settings.GEMINI_FREE_TIER_CONFIRMED and model in {'gemini-2.5-flash', 'gemini-2.5-flash-lite'}
    return settings.GROQ_FREE_TIER_CONFIRMED and model == 'openai/gpt-oss-120b'


def invoke_with_fallback(invoke, metadata):
    primary = resolve_llm_selection(role='supervisor')
    attempts = []
    metadata['provider_attempts'] = attempts
    seen = set()
    failure = None
    cooldown_failure = None
    for index, (provider, model) in enumerate((primary, *settings.SUPERVISOR_FALLBACK_PROVIDERS)):
        provider = provider.strip().lower()
        if not provider or provider in seen:
            continue
        seen.add(provider)
        provider, model = resolve_llm_selection(model, provider=provider, role='supervisor')
        attempt = {'provider': provider, 'requested_model': model}
        attempts.append(attempt)
        if not getattr(settings, KEY_SETTINGS[provider], '').strip():
            attempt['status'] = 'missing_credentials'
            continue
        if index and not _free_fallback(provider, model):
            attempt['status'] = 'free_tier_not_confirmed'
            continue
        cache_key = f'agentix:supervisor:retry-after:{provider}'
        cooldown = cache.get(cache_key)
        if cooldown is not None:
            attempt.update(status='retry_after', provider_status=cooldown)
            cooldown_failure = LLMProviderError(cooldown)
            continue
        try:
            metadata['invocations'] += 1
            result = invoke(provider, model)
        except PROVIDER_EXCEPTIONS as exc:
            status, code, temporary = provider_failure(exc)
            attempt.update(status=code, provider_status=status)
            if not temporary:
                raise
            retry_after = _retry_after(exc)
            if retry_after:
                cache.set(cache_key, status or 503, timeout=retry_after)
                attempt['retry_after_seconds'] = retry_after
            failure = exc
        else:
            attempt['status'] = 'response_received'
            metadata.update(provider=provider, requested_model=model)
            return result
    if failure is not None:
        raise failure
    if cooldown_failure is not None:
        raise cooldown_failure
    raise ImproperlyConfigured('No eligible Supervisor provider has credentials.')
