import json
import logging
import re
from datetime import date, datetime
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import ValidationError

from orchestrator.core.execution_context import ExecutionContext
from orchestrator.core.llm_factory import (
    get_llm, resolve_llm_selection, structured_llm, supervisor_structured_method,
)
from orchestrator.core.plan_schemas import ExecutionError, ExecutionPlan, PlannerDecision
from orchestrator.core.plan_validator import (
    PlanValidationFailure, log_pydantic_validation_failure,
    validate_plan,
)
from orchestrator.core.supervisor_routing import (
    PROVIDER_EXCEPTIONS, invoke_with_fallback, provider_failure,
)

PROMPT = Path(__file__).resolve().parents[1] / 'prompts' / 'supervisor.md'
logger = logging.getLogger(__name__)
PROJECT_CAPABILITIES = {
    'database.get_project',
    'database.create_project',
    'matching.rank',
}
EXPLICIT_DEADLINE = re.compile(
    r'\b(?:deadline|due\s+date|due\s+by)\s*(?:(?:is|of)\s+|:\s*)?'
    r'(\d{4}-\d{2}-\d{2}|[A-Za-z]+\s+\d{1,2},?\s+\d{4})\b',
    re.IGNORECASE,
)
MATCHING_TERMS = re.compile(
    r'\b(?:recommend|match(?:ing)?|rank(?:ing)?)\b',
    re.IGNORECASE,
)
EMPLOYEE_TERMS = re.compile(r'\b(?:employees?|candidates?|team\s+members?)\b', re.IGNORECASE)
NEGATED_MATCHING = re.compile(
    r"\b(?:do\s+not|don't|never|avoid)\s+(?:recommend|match(?:ing)?|rank(?:ing)?)\b",
    re.IGNORECASE,
)


def _requested_deadline(request):
    matches = EXPLICIT_DEADLINE.findall(request)
    if not matches:
        return None, False
    dates = set()
    for value in matches:
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            parsed = None
            for format_string in ('%B %d, %Y', '%B %d %Y', '%b %d, %Y', '%b %d %Y'):
                try:
                    parsed = datetime.strptime(value, format_string).date()
                    break
                except ValueError:
                    continue
        if parsed is None:
            return None, True
        dates.add(parsed)
    if len(dates) != 1:
        return None, True
    return dates.pop(), False


def _requests_employee_matching(request):
    return (
        MATCHING_TERMS.search(request) is not None
        and EMPLOYEE_TERMS.search(request) is not None
        and NEGATED_MATCHING.search(request) is None
    )


CREATE_AND_MATCH = {'project.plan', 'database.create_project', 'matching.rank'}
SAVE_INTENT = re.compile(r'\b(?:save|persist)\b|\bcreate\b[^.!?\n]{0,120}\bproject\b', re.IGNORECASE)
NO_SAVE = re.compile(r"\b(?:do\s+not|don't|never|without|avoid|no)\b[^.!?\n]{0,60}\b(?:save|saving|persist|write|creat\w*)\b", re.IGNORECASE)
DATE_REPLY = re.compile(r'\d{4}-\d{2}-\d{2}')
RESET_REQUESTS = {'cancel', 'cancel request', 'never mind', 'nevermind', 'start over'}


def _create_and_match(request, visible):
    return (CREATE_AND_MATCH <= visible.keys() and SAVE_INTENT.search(request)
            and not NO_SAVE.search(request) and _requests_employee_matching(request))


def _workflow_plan(brief):
    instruction = (
        'Draft the specification only. Saving and employee matching are separate workflow tasks. '
        'Use this user brief for requirements:\n'
    )
    draft_task = instruction + brief if len(instruction) + len(brief) <= 4000 else brief
    return ExecutionPlan.model_validate({
        'goal': 'Prepare the project specification, review creation, then rank employees.',
        'tasks': [
            {'task_id': 'draft', 'capability': 'project.plan', 'description': 'Draft the specification.',
             'inputs': {'task': draft_task}},
            {'task_id': 'save', 'capability': 'database.create_project', 'description': 'Save the approved project.',
             'depends_on': ['draft'], 'references': {'specification': {
                 'task_id': 'draft', 'field': 'structured_output',
             }}},
            {'task_id': 'rank', 'capability': 'matching.rank', 'description': 'Rank employees for the new project.',
             'depends_on': ['save'], 'references': {'project_id': {
                 'task_id': 'save', 'field': 'project_id',
             }}},
        ],
    })


def _pending_context(state, request, visible):
    """Read only checkpoint-owned context, never assistant text or model deadlines."""
    pending = state.get('pending_request')
    if not pending or _create_and_match(request, visible):
        deadline, invalid = _requested_deadline(request)
        return request, request, deadline, invalid
    original = pending['request']
    saved = date.fromisoformat(pending['deadline']) if pending.get('deadline') else None
    supplied, invalid = _requested_deadline(request)
    if DATE_REPLY.fullmatch(request):
        supplied, invalid = _requested_deadline(f'deadline: {request}')
    if saved and supplied and saved != supplied:
        return original, original, saved, True
    effective = original if DATE_REPLY.fullmatch(request) else f'{original}\nClarification reply: {request}'
    return original, effective, saved or supplied, invalid


def _bind_deadline_inputs(plan, deadline):
    value = deadline.isoformat() if deadline is not None else None
    tasks = []
    for task in plan.tasks:
        inputs = dict(task.inputs)
        references = dict(task.references)
        if task.capability == 'project.plan':
            inputs['explicit_deadline'] = value
            references.pop('explicit_deadline', None)
        elif task.capability == 'database.create_project':
            inputs['trusted_deadline'] = value
            references.pop('trusted_deadline', None)
        tasks.append(task.model_copy(update={'inputs': inputs, 'references': references}))
    return plan.model_copy(update={'tasks': tasks})


def planning_node(registry, limits, planner, *, execute_mock=False, capability_filter=None,
                  allow_approvals=False, use_previous_results=False, remember_request=False):
    def plan_turn(state, runtime):
        context = runtime.context
        if not isinstance(context, ExecutionContext):
            raise ValueError('Trusted execution context required.')
        request = state.get('request', '').strip()
        user_message = HumanMessage(content=request)
        error = None
        pending_update = None
        stage = 'request'
        metadata = {'phase': 2, 'mode': 'planning_only', 'model_responses': 0, 'invocations': 0}

        def failure(code, response):
            return (PlannerDecision(outcome='planning_error', response=response),
                    ExecutionError(code=code, message=response))

        def record_failure(code, category, exc=None):
            detail = {'stage': stage, 'code': code, 'category': category}
            if exc is not None:
                detail['exception_type'] = type(exc).__name__
            for key in ('provider', 'requested_model', 'model', 'structured_output_method',
                        'finish_reason', 'provider_status', 'input_tokens', 'output_tokens', 'total_tokens',
                        'plan_validation'):
                if key in metadata:
                    detail[key] = metadata[key]
            metadata['planner_diagnostic'] = detail
            logger.warning('Supervisor decision rejected: %s', json.dumps(detail, sort_keys=True))

        def configure_attempt(provider, model):
            metadata.update(provider=provider, requested_model=model,
                            structured_output_method=supervisor_structured_method(provider))

        if not request or len(request) > 4000:
            decision, error = failure('invalid_request', 'Provide a request of 1 to 4,000 characters.')
        else:
            visible = registry.visible(context, allow_approvals=allow_approvals)
            if capability_filter is not None:
                allowed = capability_filter(registry, context)
                visible = {name: item for name, item in visible.items() if name in allowed}
            original, effective, requested_deadline, invalid_deadline = (
                _pending_context(state, request, visible) if remember_request
                else (request, request, *_requested_deadline(request))
            )
            workflow = remember_request and _create_and_match(effective, visible)
            project_id = state.get('project_id')
            evidence = {
                'capabilities': [
                    {'name': name, 'agent': agent.name, 'description': agent.description,
                     'inputs': cap.input_schema.model_json_schema(),
                     'output_fields': list(cap.output_schema.model_fields)}
                    for name, (agent, cap) in visible.items()
                ],
                'limits': {'max_tasks': limits.max_tasks, 'max_depth': limits.max_depth},
                'project_id': project_id,
                'trusted_project_deadline': context.project_deadline,
                'explicit_request_deadline': requested_deadline.isoformat() if requested_deadline else None,
                'project_requirements': json.dumps(state.get('project_requirements', {}))[:3000],
                'previous_results': [
                    {'task_id': item.task_id, 'capability': item.capability, 'status': item.status}
                    for item in list(state.get(
                        'previous_results' if execute_mock or use_previous_results else 'results', {}
                    ).values())[-20:]
                ],
            }
            history = [
                type(message)(content=message.content[:1500])
                for message in state.get('messages', [])[-12:]
                if type(message) in (HumanMessage, AIMessage) and isinstance(message.content, str)
            ]
            messages = [
                SystemMessage(content=PROMPT.read_text(encoding='utf-8')),
                *history,
                HumanMessage(content='Server-provided planning context as JSON:\n' + json.dumps(evidence)),
                HumanMessage(content=effective),
            ]
            try:
                if remember_request and request.casefold().rstrip('.!') in RESET_REQUESTS:
                    decision = PlannerDecision(outcome='direct_response', response='Pending request cleared.')
                elif workflow and (requested_deadline is None or invalid_deadline):
                    decision = PlannerDecision(
                        outcome='clarification',
                        response='Please provide one valid project deadline in YYYY-MM-DD format before saving and matching.',
                    )
                else:
                    stage = 'provider_request'
                    if planner is None and settings.SUPERVISOR_FALLBACK_ENABLED:
                        def invoke(provider, model):
                            configure_attempt(provider, model)
                            return structured_llm(
                                get_llm(model, provider=provider, role='supervisor'),
                                PlannerDecision, include_raw=True,
                            ).invoke(messages)

                        result = invoke_with_fallback(invoke, metadata)
                    else:
                        if planner is None:
                            configure_attempt(*resolve_llm_selection(role='supervisor'))
                            runnable = structured_llm(get_llm(role='supervisor'), PlannerDecision, include_raw=True)
                        else:
                            runnable = planner
                        metadata['invocations'] = 1
                        result = runnable.invoke(messages)
                    stage = 'response_envelope'
                    if not isinstance(result, dict):
                        raise TypeError('Expected a structured response envelope.')
                    raw = result.get('raw')
                    if isinstance(raw, AIMessage):
                        metadata['model_responses'] = 1
                        usage = raw.usage_metadata or {}
                        metadata.update({key: usage[key] for key in
                                         ('input_tokens', 'output_tokens', 'total_tokens') if type(usage.get(key)) is int and usage[key] >= 0})
                        model = raw.response_metadata.get('model_name') or raw.response_metadata.get('model')
                        if isinstance(model, str) and re.fullmatch(r'[A-Za-z0-9/_.:-]{1,120}', model):
                            metadata['model'] = model
                        finish_reason = raw.response_metadata.get('finish_reason')
                        if finish_reason in ('stop', 'length', 'content_filter', 'tool_calls', 'function_call'):
                            metadata['finish_reason'] = finish_reason
                    stage = 'structured_parse'
                    parsing_error = result.get('parsing_error')
                    validation = (parsing_error if isinstance(parsing_error, ValidationError)
                                  else getattr(parsing_error, '__cause__', None))
                    if isinstance(validation, ValidationError):
                        metadata['plan_validation'] = log_pydantic_validation_failure(
                            'planner_decision_schema', validation, error_code='invalid_model_output',
                        )
                    invalid_calls = isinstance(raw, AIMessage) and bool(raw.invalid_tool_calls)
                    multiple_calls = isinstance(raw, AIMessage) and len(raw.tool_calls) > 1
                    if invalid_calls or multiple_calls or parsing_error is not None or result.get('parsed') is None:
                        cause = getattr(parsing_error, '__cause__', None)
                        category = ('pydantic_validation' if isinstance(validation, ValidationError)
                                    else 'malformed_json' if isinstance(cause or parsing_error, json.JSONDecodeError)
                                    else 'malformed_tool_arguments' if invalid_calls
                                    else 'multiple_decisions' if multiple_calls
                                    else 'parser_error' if parsing_error is not None else 'missing_decision')
                        record_failure('invalid_model_output', category, parsing_error)
                        decision, error = failure('invalid_model_output', 'The planner returned an invalid decision.')
                    else:
                        stage = 'decision_validation'
                        parsed = result['parsed']
                        decision = PlannerDecision.model_validate(
                            parsed.model_dump() if isinstance(parsed, PlannerDecision) else parsed
                        )
                    if (workflow and decision.outcome == 'clarification'
                            and re.search(r'\b(?:approv\w*|confirm\w*|deadline)\b',
                                          decision.response, re.IGNORECASE)):
                        decision = PlannerDecision(
                            outcome='plan', response='Prepared a workflow with approval before saving.',
                            plan=_workflow_plan(effective if len(effective) <= 4000 else original),
                        )
                if decision.plan is not None:
                    stage = 'plan_validation'
                    plan = _bind_deadline_inputs(decision.plan, requested_deadline)
                    decision = decision.model_copy(update={'plan': plan})
                    validate_plan(decision.plan, registry, context, limits, require_mock=False,
                                  allow_approvals=allow_approvals)
                    for task in decision.plan.tasks:
                        if task.capability in {'database.get_project', 'matching.rank'} and (
                            'project_id' not in task.references
                            and (
                                type(project_id) is not int or project_id <= 0
                                or task.inputs.get('project_id') != project_id
                            )
                        ):
                            decision = PlannerDecision(
                                outcome='clarification',
                                response='Which authorized project should I use?',
                            )
                            break
                    if decision.outcome == 'plan':
                        capabilities = {task.capability for task in decision.plan.tasks}
                        creates_project = 'database.create_project' in capabilities
                        ranks_employees = 'matching.rank' in capabilities
                        requests_matching = (
                            ranks_employees or (
                                creates_project and _requests_employee_matching(effective)
                            )
                        )
                        if invalid_deadline and (creates_project or ranks_employees):
                            decision = PlannerDecision(
                                outcome='clarification',
                                response=(
                                    'Please provide one valid project deadline in YYYY-MM-DD '
                                    'format before I save the project or rank employees.'
                                ),
                            )
                        elif creates_project and requests_matching and requested_deadline is None:
                            decision = PlannerDecision(
                                outcome='clarification',
                                response=(
                                    'What is the project deadline? Please provide it as '
                                    'YYYY-MM-DD before I save the project or rank employees.'
                                ),
                            )
                        elif ranks_employees and not creates_project:
                            trusted_deadline = context.project_deadline
                            requested_text = (
                                requested_deadline.isoformat()
                                if requested_deadline is not None else None
                            )
                            if trusted_deadline is None:
                                decision = PlannerDecision(
                                    outcome='clarification',
                                    response=(
                                        'The selected project has no saved deadline. Update '
                                        'its deadline before requesting employee matching.'
                                    ),
                                )
                            elif requested_text and requested_text != trusted_deadline:
                                decision = PlannerDecision(
                                    outcome='clarification',
                                    response=(
                                        'The requested deadline differs from the selected '
                                        "project's saved deadline. Update the project before "
                                        'requesting employee matching.'
                                    ),
                                )
                elif decision.outcome == 'planning_error' and error is None:
                    decision, error = failure('model_planning_error', 'The planner could not produce a decision.')
            except PROVIDER_EXCEPTIONS as exc:
                status, category, _ = provider_failure(exc)
                metadata['provider_status'] = status
                code = 'rate_limited' if status == 429 else 'provider_error'
                response = ('The planner is rate limited. Try again later.' if status == 429
                            else 'The planning provider is unavailable.')
                record_failure(code, category, exc)
                decision, error = failure(code, response)
            except ImproperlyConfigured as exc:
                record_failure('provider_configuration', 'configuration_error', exc)
                decision, error = failure('provider_configuration', 'The planning provider is not configured.')
            except ValidationError as exc:
                metadata['plan_validation'] = log_pydantic_validation_failure(
                    'planner_decision_schema', exc, error_code='invalid_model_output',
                )
                record_failure('invalid_model_output', 'pydantic_validation', exc)
                decision, error = failure('invalid_model_output', 'The planner returned an invalid decision.')
            except OutputParserException as exc:
                stage = 'structured_parse'
                record_failure('invalid_model_output', 'parser_error', exc)
                decision, error = failure('invalid_model_output', 'The planner returned an invalid decision.')
            except (TypeError, AttributeError) as exc:
                category = 'invalid_envelope' if stage == 'response_envelope' else 'planner_internal_error'
                record_failure('invalid_model_output', category, exc)
                decision, error = failure('invalid_model_output', 'The planner returned an invalid decision.')
            except PlanValidationFailure as exc:
                metadata['plan_validation'] = exc.diagnostic
                record_failure('invalid_plan', 'plan_validation', exc)
                decision, error = failure('invalid_plan', 'The proposed plan did not pass validation.')
            except ValueError:
                decision, error = failure('invalid_plan', 'The proposed plan did not pass validation.')

            if remember_request and decision.outcome == 'clarification':
                pending_update = {'request': original, 'deadline': (
                    requested_deadline.isoformat() if requested_deadline else None
                )}

        return {
            **({'pending_request': pending_update} if remember_request else {}),
            'decision': decision, 'plan': decision.plan, 'errors': [error] if error else [],
            'final_response': decision.response, 'metadata': metadata,
            'user_id': context.user_id, 'company_id': context.company_id,
            'messages': ([user_message] if execute_mock and decision.outcome == 'plan'
                         else [user_message, AIMessage(content=decision.response)]),
        }

    return plan_turn
