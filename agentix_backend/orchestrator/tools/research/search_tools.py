import os
from typing import Literal

import httpx
from pydantic import Field, ValidationError

from orchestrator.agents.research.schemas import ResearchModel, Source


class SearchInput(ResearchModel):
    query: str = Field(min_length=1, max_length=400)
    max_results: int = Field(default=4, ge=3, le=5)
    include_domains: list[str] = Field(default_factory=list, max_length=5)
    time_range: Literal['day', 'week', 'month', 'year'] | None = None


def search_web(**kwargs):
    request = SearchInput(**kwargs)
    key = os.getenv('TAVILY_API_KEY', '').strip()
    if not key:
        return {'sources': [], 'error': 'missing_tavily_key', 'requests': 0}
    outcome = {'sources': [], 'requests': 1}
    try:
        response = httpx.post(
            'https://api.tavily.com/search',
            headers={'Authorization': f'Bearer {key}'},
            json={**request.model_dump(exclude_none=True), 'search_depth': 'basic',
                  'auto_parameters': False, 'include_usage': True},
            timeout=10, follow_redirects=False,
        )
        if response.status_code in {429, 432, 433}:
            return {**outcome, 'error': 'search_quota', 'http_status': response.status_code}
        if response.status_code in {401, 403}:
            return {**outcome, 'error': 'tavily_auth_failed', 'http_status': response.status_code}
        response.raise_for_status()
        payload = response.json()
        rows = payload['results']
        if not isinstance(rows, list):
            raise ValueError('Invalid result list')
    except httpx.TimeoutException:
        return {**outcome, 'error': 'search_timeout'}
    except httpx.HTTPStatusError as exc:
        return {**outcome, 'error': 'search_unavailable', 'http_status': exc.response.status_code}
    except (httpx.RequestError, KeyError, TypeError, ValueError):
        return {**outcome, 'error': 'search_unavailable'}

    sources = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get('title'):
            continue
        try:
            source = Source(title=str(row['title'])[:200], url=row.get('url'),
                            excerpt=str(row.get('content') or '')[:400], provider='tavily')
        except ValidationError:
            continue
        sources.setdefault(str(source.url), source.model_dump(mode='json'))
        if len(sources) == request.max_results:
            break
    usage = payload.get('usage')
    credits = usage.get('credits') if isinstance(usage, dict) else None
    return {**outcome, 'sources': list(sources.values()), 'credits': credits,
            'error': None if sources else 'no_results'}
