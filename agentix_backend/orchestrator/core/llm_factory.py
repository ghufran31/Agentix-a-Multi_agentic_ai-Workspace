from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from langchain_groq import ChatGroq


@lru_cache(maxsize=8)
def get_llm(model_name=None):
    api_key = getattr(settings, 'GROQ_API_KEY', '')
    if not api_key:
        raise ImproperlyConfigured(
            'Set GROQ_API_KEY in the repository-root .env file or environment.'
        )
    return ChatGroq(
        api_key=api_key,
        model=model_name or settings.GROQ_MODEL_NAME,
        temperature=settings.GROQ_TEMPERATURE,
        timeout=settings.GROQ_REQUEST_TIMEOUT,
        max_retries=settings.GROQ_MAX_RETRIES,
        max_tokens=getattr(settings, 'GROQ_MAX_TOKENS', 16384),
    )
