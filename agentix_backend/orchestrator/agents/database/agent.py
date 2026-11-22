from pathlib import Path

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage

from orchestrator.core.llm_factory import get_llm
from orchestrator.tools.database.company_tools import company_tools
from orchestrator.tools.database.department_tools import department_tools
from orchestrator.tools.database.employee_tools import employee_tools
from orchestrator.tools.database.project_tools import project_tools
from orchestrator.tools.database.recommendation_tools import recommendation_tools
from orchestrator.tools.database.relationship_tools import relationship_tools
from orchestrator.tools.database.skill_tools import skill_tools

from .config import load_system_prompt
from .schemas import DatabaseAgentResult


def database_tools(context):
    tools = []
    tools.extend(department_tools(context))
    tools.extend(employee_tools(context))
    tools.extend(company_tools(context))
    tools.extend(project_tools(context))
    tools.extend(skill_tools(context))
    tools.extend(recommendation_tools(context))
    tools.extend(relationship_tools(context))
    return tools


def build_database_agent(context, model_name=None, checkpointer=None):
    tools = database_tools(context)
    llm = get_llm(model_name)
    kwargs = {
        'model': llm,
        'tools': tools,
        'system_prompt': load_system_prompt(),
    }
    if checkpointer is not None:
        kwargs['checkpointer'] = checkpointer
    return create_agent(**kwargs)


def execute_database_task(context, task, conversation=None, model_name=None,
                          prior_task_data=None, read_only=False):
    if read_only:
        from dataclasses import replace
        context = replace(context, read_only=True)
    agent = build_database_agent(context, model_name=model_name)
    messages = []
    for item in conversation or []:
        if isinstance(item, dict):
            if item.get('role') == 'assistant':
                messages.append(AIMessage(content=item.get('content', '')))
            else:
                messages.append(HumanMessage(content=item.get('content', '')))
        elif hasattr(item, 'type'):
            messages.append(item)
    if prior_task_data:
        messages.append(HumanMessage(content=f'Prior server task data: {prior_task_data}'))
    messages.append(HumanMessage(content=task))
    state = agent.invoke({'messages': messages})
    output_messages = state.get('messages', [])
    tool_names = []
    execution_results = []
    pending_approval = None

    for message in output_messages:
        if hasattr(message, 'tool_calls') and message.tool_calls:
            for call in message.tool_calls:
                tool_names.append(call.get('name', ''))
        if message.__class__.__name__ == 'ToolMessage':
            content = getattr(message, 'content', '')
            if isinstance(content, dict):
                data = content
            else:
                import json
                try:
                    data = json.loads(content)
                except Exception:
                    data = {'message': str(content)}
            if isinstance(data, dict):
                success = data.get('success')
                operation = data.get('operation', '')
                execution_results.append({
                    'success': bool(success),
                    'operation': operation,
                    'message': data.get('message', ''),
                    'data': data.get('data', {}),
                    'errors': data.get('errors', []),
                    'pending_approval': data.get('pending_approval'),
                })
                if data.get('pending_approval'):
                    pending_approval = data['pending_approval']

    ai_messages = [m for m in output_messages if isinstance(m, AIMessage)]
    answer = ai_messages[-1].content if ai_messages else 'The database agent returned no answer.'
    if isinstance(answer, list):
        answer = ' '.join(
            item.get('text', '') if isinstance(item, dict) else str(item)
            for item in answer
        )

    return DatabaseAgentResult(
        answer=answer,
        success=not execution_results or all(item['success'] for item in execution_results),
        tool_names=tool_names,
        execution_results=execution_results,
        pending_approval=pending_approval,
    )
