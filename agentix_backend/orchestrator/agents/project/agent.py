import json
import logging

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import ValidationError

from orchestrator.core.llm_factory import get_llm, structured_llm
from orchestrator.tools.project import (
    full_plan_tools, planning_tools, requirements_tools, role_tools,
    technology_tools,
)

from .config import load_system_prompt
from .validation import validation_issues
from .schemas import (
    PlanningToolExecution, ProjectAgentOutput, ProjectAgentResult,
)


logger = logging.getLogger(__name__)
PROVIDER_CODES = {'tool_use_failed', 'json_validate_failed', 'rate_limit_exceeded',
                  'context_length_exceeded', 'invalid_request_error'}


def _failure(exc, stage):
    status = getattr(exc, 'status_code', None)
    body = getattr(exc, 'body', None)
    error = body.get('error', body) if isinstance(body, dict) else {}
    code = error.get('code') if isinstance(error, dict) else None
    code = code if isinstance(code, str) and code in PROVIDER_CODES else None
    logger.warning('Project Agent stage=%s error=%s status=%s code=%s',
                   stage, type(exc).__name__, status, code)
    return {
        'failure_stage': stage,
        'provider_status': status if type(status) is int else None,
        'provider_code': code,
    }


def _validation_codes(exc):
    # LangChain's Pydantic parser can wrap the validation exception.
    cause = exc.__cause__
    error = cause if isinstance(cause, ValidationError) else exc
    if isinstance(cause, json.JSONDecodeError) or isinstance(exc, json.JSONDecodeError):
        return ['invalid_json']
    if isinstance(error, ValidationError):
        return list(dict.fromkeys(item['type'] for item in error.errors(include_input=False)))[:12]
    return [type(exc).__name__]


def _validate_output(value):
    if isinstance(value, ProjectAgentOutput):
        value = value.model_dump()
    return ProjectAgentOutput.model_validate(value)


def project_tools(context=None):
    return [
        *requirements_tools(),
        *technology_tools(),
        *role_tools(context),
        *planning_tools(),
        *full_plan_tools(context),
    ]


def build_project_agent(context=None, model_name=None, checkpointer=None):
    kwargs = {
        'model': get_llm(model_name),
        'tools': project_tools(context),
        'system_prompt': load_system_prompt(),
        'name': 'project_planning_agent',
    }
    if checkpointer is not None:
        kwargs['checkpointer'] = checkpointer
    return create_agent(**kwargs)


def build_project_output_model(model_name=None):
    return structured_llm(get_llm(model_name), ProjectAgentOutput, include_raw=True)


def _messages(conversation):
    messages = []
    for item in conversation or []:
        if hasattr(item, 'type'):
            messages.append(item)
        elif isinstance(item, dict):
            content = item.get('content', '')
            messages.append(
                AIMessage(content=content)
                if item.get('role') == 'assistant'
                else HumanMessage(content=content)
            )
    return messages


def _json_content(content):
    if isinstance(content, dict):
        return content
    try:
        return json.loads(content)
    except (TypeError, ValueError):
        return {'value': str(content)}


def execute_project_task(context, task, conversation=None, model_name=None, agent=None,
                         structured_model=None):
    initial_request_attempted = False
    try:
        runtime = agent or build_project_agent(context, model_name=model_name)
        initial_request_attempted = True
        state = runtime.invoke({
            'messages': [*_messages(conversation), HumanMessage(content=task)]
        })
    except Exception as exc:
        return ProjectAgentResult(
            answer='The Project Agent could not complete this request.',
            success=False,
            validation_errors=[type(exc).__name__],
            **_failure(exc, 'tool_planning'),
            model_requests=1 if initial_request_attempted else 0,
        )
    output_messages = state.get('messages', [])
    tool_names = []
    tool_outputs = {}
    model_calls = 0
    for message in output_messages:
        if isinstance(message, AIMessage):
            if getattr(message, 'usage_metadata', None):
                model_calls += 1
            for call in getattr(message, 'tool_calls', []) or []:
                name = call.get('name', '')
                if name.startswith('ProjectAgentOutput'):
                    continue
                tool_names.append(name)
        if message.__class__.__name__ == 'ToolMessage':
            name = getattr(message, 'name', '') or ''
            if name.startswith('ProjectAgentOutput'):
                continue
            call_id = getattr(message, 'tool_call_id', '')
            if call_id:
                tool_outputs[call_id] = (name, _json_content(getattr(message, 'content', '')))

    executions = []
    tool_calls_by_id = {}
    for message in output_messages:
        if isinstance(message, AIMessage):
            for call in getattr(message, 'tool_calls', []) or []:
                call_id = call.get('id')
                if call_id:
                    tool_calls_by_id[call_id] = (call.get('name', ''), call.get('args', {}))
    for call_id, (name, inputs) in tool_calls_by_id.items():
        output = tool_outputs.get(call_id, ('', {}))[1]
        executions.append(PlanningToolExecution(name=name, input=inputs, output=output))

    raw_structured = state.get('structured_response')
    validation_errors = []
    issues = []
    failure = {}
    structured = None
    try:
        if raw_structured is not None:
            structured = _validate_output(raw_structured)
    except ValidationError as exc:
        validation_errors = _validation_codes(exc)
        issues = validation_issues(exc)
        failure = _failure(exc, 'output_validation')

    ai_messages = [message for message in output_messages if isinstance(message, AIMessage)]
    draft_answer = ''
    if ai_messages:
        content = ai_messages[-1].content
        draft_answer = content if isinstance(content, str) else json.dumps(content)

    model_requests = model_calls
    if raw_structured is None and (structured_model is not None or agent is None):
        evidence = [
            {'name': item.name, 'output': item.output}
            for item in executions
        ]
        validation_messages = [
            SystemMessage(content=(
                'You are the Agentix Project Planning Specialist. Return the final '
                'result in the required ProjectAgentOutput schema. '
                'Use the conversation, latest request, verified tool evidence, and '
                'preserve all explicit requirements and revisions. Clearly label '
                'recommendations and assumptions. Never claim persistence or invent '
                'a project ID. Use a clarification only for essential missing data. '
                'Keep the result compact. Include at most 6 features, 8 functional '
                'requirements, 5 nonfunctional requirements, 6 roles, 12 skills and '
                '5 milestones. Keep descriptions concise and avoid repeating information. '
                'For a specification include name, description, project_type, features, '
                'functional_requirements, technology_stack, required_roles, required_skills '
                'and milestones. Use the schema field names and enumerated values exactly. '
                'Set persistence_performed to false. When the outcome is specification, '
                'leave clarification null. The specification is a JSON object, not a '
                'string or a list. technology_stack is an object with architecture_style '
                'and a choices array of objects. features, functional_requirements, '
                'required_roles, required_skills, and milestones are arrays of objects, '
                'not arrays of names. Use planning tool output as evidence, not as the '
                'output shape. Place the roles_and_skills.roles and roles_and_skills.skills '
                'lists in required_roles and required_skills, and use roadmap.milestones '
                'for milestones. Write numeric fields as JSON numbers. Set deadline to '
                'the exact user-provided YYYY-MM-DD date when one is explicitly supplied; '
                'otherwise set it to null. Never infer or invent a deadline.'
            )),
            *_messages(conversation),
            HumanMessage(content=task),
            HumanMessage(content='Unverified planning draft (review against the request):\n'
                         + draft_answer[:4000]),
            HumanMessage(content=(
                'Verified planning tool evidence:\n'
                + json.dumps(evidence, default=str)
            )),
        ]
        raw_message = None
        try:
            validator = structured_model or build_project_output_model(model_name)
            model_requests += 1
            validated = validator.invoke(validation_messages)
            envelope_keys = {'raw', 'parsed', 'parsing_error'}
            if isinstance(validated, dict) and 0 < len(validated) and validated.keys() <= envelope_keys:
                raw_message = validated.get('raw')
                parsed = validated.get('parsed')
                parsing_error = validated.get('parsing_error')
            else:
                parsed, parsing_error = validated, None
            if raw_message is not None and getattr(raw_message, 'usage_metadata', None):
                model_calls += 1
            if parsing_error:
                validation_errors = _validation_codes(parsing_error)
                issues = validation_issues(parsing_error)
                failure = _failure(parsing_error, 'output_validation')
            elif parsed is None:
                validation_errors.append('missing_structured_output')
                failure['failure_stage'] = 'output_validation'
            else:
                structured = _validate_output(parsed)
        except Exception as exc:
            validation_errors = _validation_codes(exc)
            issues = validation_issues(exc)
            failure = _failure(exc, 'output_validation' if isinstance(exc, ValidationError)
                               else 'structured_synthesis')
        if validation_errors:
            reason = getattr(raw_message, 'response_metadata', {}).get('finish_reason')
            if reason in ('stop', 'length', 'content_filter', 'tool_calls'):
                failure['finish_reason'] = reason

    if failure.get('failure_stage') == 'output_validation':
        logger.warning('Project Agent validation codes=%s fields=%s finish_reason=%s',
                       validation_errors, issues, failure.get('finish_reason'))

    answer = structured.response if structured else ''
    if structured and structured.outcome == 'clarification' and structured.clarification:
        questions = [item.question for item in structured.clarification.questions]
        answer = structured.response.rstrip()
        if questions:
            answer += '\n' + '\n'.join(
                f'{index}. {question}'
                for index, question in enumerate(questions, start=1)
            )
    if not answer:
        answer = draft_answer
    if not answer:
        answer = 'The Project Agent returned no validated response.'
    return ProjectAgentResult(
        answer=answer,
        success=structured is not None and not validation_errors,
        structured_output=structured,
        tool_names=tool_names,
        tool_executions=executions,
        validation_errors=validation_errors,
        validation_issues=issues,
        model_calls=model_calls,
        model_requests=model_requests,
        **failure,
    )
