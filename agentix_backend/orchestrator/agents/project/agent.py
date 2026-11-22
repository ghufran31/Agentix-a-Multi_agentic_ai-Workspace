import json

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import ValidationError

from orchestrator.core.llm_factory import get_llm
from orchestrator.tools.project import (
    full_plan_tools, planning_tools, requirements_tools, role_tools,
    technology_tools,
)

from .config import load_system_prompt
from .schemas import (
    PlanningToolExecution, ProjectAgentOutput, ProjectAgentResult,
)


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
    return get_llm(model_name).with_structured_output(
        ProjectAgentOutput,
        method='json_schema',
        strict=False,
        include_raw=True,
    )


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
            validation_errors=[f'{type(exc).__name__}: {exc}'],
            model_requests=1 if initial_request_attempted else 0,
        )
    output_messages = state.get('messages', [])
    tool_names = []
    tool_inputs = []
    tool_outputs = []
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
                tool_inputs.append((name, call.get('args', {})))
        if message.__class__.__name__ == 'ToolMessage':
            name = getattr(message, 'name', '') or ''
            if name.startswith('ProjectAgentOutput'):
                continue
            tool_outputs.append((name, _json_content(getattr(message, 'content', ''))))

    executions = []
    for index, (name, inputs) in enumerate(tool_inputs):
        output = tool_outputs[index][1] if index < len(tool_outputs) else {}
        executions.append(PlanningToolExecution(name=name, input=inputs, output=output))

    raw_structured = state.get('structured_response')
    validation_errors = []
    structured = None
    try:
        if raw_structured is not None:
            structured = (
                raw_structured if isinstance(raw_structured, ProjectAgentOutput)
                else ProjectAgentOutput.model_validate(raw_structured)
            )
    except ValidationError as exc:
        validation_errors = [error['msg'] for error in exc.errors()]

    ai_messages = [message for message in output_messages if isinstance(message, AIMessage)]
    draft_answer = ''
    if ai_messages:
        content = ai_messages[-1].content
        draft_answer = content if isinstance(content, str) else json.dumps(content)

    model_requests = model_calls
    if raw_structured is None and (structured_model is not None or agent is None):
        validator = structured_model or build_project_output_model(model_name)
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
                'a project ID. Use a clarification only for essential missing data.'
            )),
            *_messages(conversation),
            HumanMessage(content=task),
            HumanMessage(content=(
                'Verified planning tool evidence:\n'
                + json.dumps(evidence, default=str)
            )),
        ]
        try:
            model_requests += 1
            validated = validator.invoke(validation_messages)
            raw_message = validated.get('raw') if isinstance(validated, dict) else None
            parsed = validated.get('parsed') if isinstance(validated, dict) else validated
            parsing_error = (
                validated.get('parsing_error') if isinstance(validated, dict) else None
            )
            if raw_message is not None and getattr(raw_message, 'usage_metadata', None):
                model_calls += 1
            if parsing_error:
                validation_errors.append(
                    f'{type(parsing_error).__name__}: {parsing_error}'
                )
            elif parsed is not None:
                structured = (
                    parsed if isinstance(parsed, ProjectAgentOutput)
                    else ProjectAgentOutput.model_validate(parsed)
                )
        except Exception as exc:
            validation_errors.append(f'{type(exc).__name__}: {exc}')

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
        model_calls=model_calls,
        model_requests=model_requests,
    )
