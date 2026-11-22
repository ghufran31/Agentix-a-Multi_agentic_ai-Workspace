import re

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from groq import APIError
from pydantic import ValidationError
from companies.models import CompanyUser
from projects.models import Project

from orchestrator.core.llm_factory import get_llm
from orchestrator.tools.matching.context_tools import context_tools as make_context_tools
from .config import load_system_prompt
from .schemas import MatchingAgentResult, MatchingResponse

def matching_tools(context):
    return make_context_tools(context)

def build_matching_agent(context, model_name=None, checkpointer=None):
    kwargs = {'model': get_llm(model_name), 'tools': matching_tools(context), 'system_prompt': load_system_prompt(), 'name': 'employee_matching_agent'}
    if checkpointer is not None:
        kwargs['checkpointer'] = checkpointer
    return create_agent(**kwargs)

def execute_matching_task(context, task, conversation=None, model_name=None, agent=None,
                          *, last_matching=None):
    compare = last_matching is not None and re.search(
        r'\bwhy\b.*\b(rank\w*|higher|above)\b', task, re.I
    )
    messages = _conversation(conversation)
    if compare:
        messages.append(AIMessage(content=(
            f'Previous verified ranking was for project {last_matching.metadata.project_id}. '
            'This turn asks to explain that saved ranking. No fresh tool call is needed.'
        )))
    try:
        runtime = agent or build_matching_agent(context, model_name)
        result = runtime.invoke({'messages': [*messages, HumanMessage(content=task)]})
    except APIError as exc:
        return MatchingAgentResult(success=False, answer='Model provider request failed.',
                                   validation_errors=[type(exc).__name__], model_requests=1)
    output = result.get('messages', [])
    names = []
    response_count = 0
    tokens = dict(input_tokens=0, output_tokens=0, total_tokens=0)
    for message in output:
        if isinstance(message, AIMessage):
            if message.usage_metadata:
                response_count += 1
                for key in tokens:
                    tokens[key] += message.usage_metadata.get(key, 0)
            for call in getattr(message, 'tool_calls', []):
                names.append(call.get('name', ''))
    ranking = next((message for message in reversed(output)
                    if isinstance(message, ToolMessage) and message.name == 'rank_project_employees'), None)
    lookup = next((message for message in reversed(output)
                   if isinstance(message, ToolMessage) and message.name == 'get_project_matching_context'), None)
    errors = []
    try:
        if compare and context.user.is_authenticated and (
            CompanyUser.objects.filter(user_id=context.user.pk, user__is_active=True,
                                       company_id=context.company.pk).exists()
            and Project.objects.filter(pk=last_matching.metadata.project_id,
                                       company_id=context.company.pk).exists()
        ):
            candidates = last_matching.candidates
            explanation = 'The previous ranking has fewer than two candidates to compare.'
            if len(candidates) >= 2:
                first, second = candidates[:2]
                direction = ('The classifier gave the first employee a higher score.'
                             if first.model_score > second.model_score
                             else 'The scores tied, so the lower employee ID ranked first.')
                explanation = (
                    f'{direction} Employee {first.employee_id}: {first.model_score:.6f}. '
                    f'{first.explanation} Employee {second.employee_id}: {second.model_score:.6f}. '
                    f'{second.explanation} These observed features do not establish what caused the scores.'
                )
            parsed = MatchingResponse.model_validate({
                **last_matching.model_dump(), 'answer': explanation,
            })
        elif ranking is None and lookup is not None and lookup.status != 'error':
            import json
            evidence = json.loads(lookup.content)
            parsed = (MatchingResponse.model_validate(evidence) if not evidence.get('success')
                      else MatchingResponse(success=False, answer='No ranking was run for the project.',
                                            error='ranking_required'))
        elif ranking is None:
            parsed = MatchingResponse(success=False, answer='Provide an authorized project ID to match employees.',
                                      error='No verified ranking was produced.')
        elif ranking.status == 'error':
            parsed = MatchingResponse(success=False, answer='The ranking tool rejected the request.',
                                      error='Ranking tool error.')
        else:
            parsed = MatchingResponse.model_validate_json(ranking.content)
    except (ValidationError, TypeError, ValueError):
        parsed = MatchingResponse(success=False, answer='Invalid ranking tool response.',
                                  error='Ranking response validation failed.')
        errors.append(parsed.error)
    answer = parsed.answer
    for candidate in parsed.candidates:
        answer += (f'\n{candidate.rank}. Employee {candidate.employee_id}: {candidate.model_score:.6f}'
                   f' | matched: {", ".join(candidate.matched_skills)}'
                   f' | missing: {", ".join(candidate.missing_skills) or "none"}')
    return MatchingAgentResult(success=parsed.success, answer=answer, structured_output=parsed,
                               tool_names=names, validation_errors=errors,
                               model_requests=response_count, model_responses=response_count,
                               token_usage=tokens if response_count else {})

def _conversation(conversation):
    messages = []
    for turn in conversation or []:
        messages.append(AIMessage(content=turn.get('content', '')) if turn.get('role') == 'assistant' else HumanMessage(content=turn.get('content', '')))
    return messages
