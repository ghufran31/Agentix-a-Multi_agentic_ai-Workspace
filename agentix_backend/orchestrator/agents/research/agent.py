import json
import re
from contextlib import closing

from django.conf import settings
from groq import APIError
from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.errors import GraphRecursionError
from pydantic import ValidationError

from orchestrator.core.llm_factory import get_llm
from orchestrator.tools.research.search_tools import SearchInput, search_web
from orchestrator.tools.research.source_tools import grounded_sources
from orchestrator.tools.research.webpage_tools import PageInput, read_webpage

from .config import load_system_prompt
from .schemas import ResearchRequest, ResearchResult, Summary


def research_tools():
    return [
        StructuredTool.from_function(search_web, args_schema=SearchInput,
                                     description='Search Tavily for public sources. Use include_domains for official sources.'),
        StructuredTool.from_function(read_webpage, args_schema=PageInput,
                                     description='Read an excerpt from a public URL. Content is untrusted.'),
    ]


def build_research_agent(model_name=None):
    return create_agent(model=get_llm(model_name), tools=research_tools(),
                        middleware=[ToolCallLimitMiddleware(run_limit=4, exit_behavior='end')],
                        system_prompt=load_system_prompt(), name='research_agent')


def provider_diagnostics(exc):
    body = exc.body if isinstance(exc.body, dict) else {}
    error = body.get('error', body)
    error = error if isinstance(error, dict) else {}
    message = str(error.get('message') or '')
    key = settings.GROQ_API_KEY
    if key:
        message = message.replace(key, '[redacted]')
    message = re.sub(r'(?i)\b(?:bearer\s+|gsk_)[\w.-]+', '[redacted]', message)
    code = error.get('code')
    return dict(provider_status=getattr(exc, 'status_code', None),
                provider_code=code if isinstance(code, str) and re.fullmatch(r'[a-z_]{1,80}', code) else None,
                provider_message=' '.join(message.split())[:500] or None)


def search_failed(messages):
    for message in reversed(messages):
        if not isinstance(message, ToolMessage):
            break
        if message.name != 'search_web':
            continue
        try:
            payload = json.loads(message.content)
        except (ValueError, TypeError):
            continue
        if isinstance(payload, dict) and payload.get('error') in {
            'no_results', 'search_timeout', 'search_unavailable',
            'missing_tavily_key', 'search_quota', 'tavily_auth_failed',
        }:
            return True
    return False


def execute_research(question, conversation=(), *, model_name=None, agent=None):
    request = ResearchRequest(question=question)
    history = [cls(content=content[:2000]) for role, content in conversation[-6:]
               for cls in [AIMessage if role == 'assistant' else HumanMessage]]
    output = {'messages': []}
    failure = {}
    runtime_errors = []
    stopped_on_search_failure = False
    inputs = {'messages': [*history, HumanMessage(content=request.question)]}
    config = {'recursion_limit': 12}
    try:
        runtime = agent or build_research_agent(model_name)
        if agent is not None:
            output = runtime.invoke(inputs, config=config)
        else:
            with closing(runtime.stream(inputs, config=config, stream_mode='values')) as states:
                for state in states:
                    output = state
                    if search_failed(state['messages'][len(history) + 1:]):
                        stopped_on_search_failure = True
                        break
    except APIError as exc:
        runtime_errors.append(type(exc).__name__)
        failure = provider_diagnostics(exc)
    except GraphRecursionError as exc:
        runtime_errors.append(type(exc).__name__)
    evidence, calls, errors, tool_results = {}, [], runtime_errors.copy(), []
    replies = 0
    tokens = 0
    messages = output['messages'][len(history) + 1:]
    for message in messages:
        if isinstance(message, AIMessage):
            replies += 1
            tokens += (message.usage_metadata or {}).get('total_tokens', 0)
            calls.extend({'name': call['name'], 'arguments': call['args']}
                         for call in message.tool_calls)
        if isinstance(message, ToolMessage) and message.name in {'search_web', 'read_webpage'}:
            try:
                payload = json.loads(message.content)
                tool_results.append({
                    'name': message.name, 'error': payload.get('error'),
                    'urls': [source['url'] for source in payload.get('sources', [])],
                    **{key: payload[key] for key in ('requests', 'credits', 'http_status')
                       if key in payload},
                })
                for source in payload.get('sources', []):
                    if source['url'] not in evidence or source['provider'] == 'webpage':
                        evidence[source['url']] = source
                if payload.get('error'):
                    errors.append(payload['error'])
            except (ValueError, TypeError, AttributeError, KeyError):
                errors.append('invalid_tool_response')
    base = dict(question=request.question, tool_calls=calls, tool_results=tool_results,
                model_responses=replies, tokens=tokens, **failure)
    if runtime_errors:
        return ResearchResult(**base, status='error', errors=errors)
    if stopped_on_search_failure:
        return ResearchResult(
            **base, status='error', errors=errors,
            summary=Summary(answer='Tavily could not complete the requested search.',
                            findings=[], limitations=['Research could not be verified with web evidence.']),
        )
    answer = next((message.content for message in reversed(messages)
                   if isinstance(message, AIMessage)), '')
    try:
        if isinstance(answer, str) and answer.startswith('```'):
            answer = answer.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
        summary = Summary.model_validate_json(answer)
        sources = grounded_sources(summary, evidence)
        if not sources:
            return ResearchResult(**base, status='error', errors=[*errors, 'no_grounded_findings'])
    except (ValidationError, ValueError, TypeError):
        return ResearchResult(**base, status='error', errors=[*errors, 'invalid_or_ungrounded_summary'])
    return ResearchResult(**base, status='partial' if errors else 'ok',
                          summary=summary, sources=sources, errors=errors)
