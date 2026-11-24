from copy import deepcopy
from dataclasses import replace
from time import perf_counter

from langchain_core.messages import AIMessage
from langgraph.config import get_stream_writer
from langgraph.types import Overwrite
from pydantic import ValidationError

from orchestrator.core.plan_schemas import (
    ExecutionError, ExecutionPlan, ExecutionSummary, TaskResult,
)
from orchestrator.core.execution_context import ExecutionContext
from orchestrator.core.plan_validator import (
    PlanValidationFailure,
    log_pydantic_validation_failure,
    validate_plan,
)
from orchestrator.core.specialist_dispatch import (
    DispatchFailure, dispatch_real, validate_real_plan,
)


def resolve_inputs(task, capability, prerequisites):
    inputs = deepcopy(task.inputs)
    for name, reference in task.references.items():
        inputs[name] = deepcopy(prerequisites[reference.task_id].output[reference.field])
    return capability.input_schema.model_validate(inputs, strict=True)


def begin_turn(state):
    history = {**state.get('previous_results', {}), **state.get('results', {})}
    return {
        'messages': Overwrite(state.get('messages', [])[-22:]),
        'previous_results': dict(list(history.items())[-20:]),
        'results': Overwrite({}), 'pending_approvals': [], 'approval_records': {},
        'execution_summary': None, 'task_statuses': {}, 'order': (), 'ready': [],
    }


def initialize_turn(state, runtime, registry, limits, *, integrated, real, persistent, approvals):
    if not isinstance(runtime.context, ExecutionContext):
        raise ValueError('Trusted execution context required.')
    context = runtime.context
    initialized = dict(
        messages=state.get('messages', []), request=state.get('request', ''),
        user_id=context.user_id, company_id=context.company_id,
        project_id=state.get('project_id'),
        project_requirements=state.get('project_requirements', {}),
        pending_approvals=[], errors=[], final_response='', task_statuses={},
        metadata={**(state.get('metadata', {}) if integrated else {}),
                  'phase': 5 if persistent else 4 if real else 3 if integrated else 1,
                  'mode': f'integrated_{real and "real" or "mock"}' if integrated else 'mock',
                  'status': 'running'},
        order=(), ready=[],
    )
    if integrated:
        initialized['execution_summary'] = None
    try:
        raw_plan = state.get('plan')
        if isinstance(raw_plan, ExecutionPlan):
            raw_plan = raw_plan.model_dump()
        plan = ExecutionPlan.model_validate(raw_plan)
        if real:
            order = validate_real_plan(plan, registry, context, limits)
        else:
            order = validate_plan(plan, registry, context, limits, allow_approvals=approvals)
    except ValidationError as exc:
        initialized['metadata']['plan_validation'] = log_pydantic_validation_failure(
            'execution_plan_schema',
            exc,
            error_code='invalid_plan_schema',
        )
        initialized['errors'] = [ExecutionError(code='invalid_plan', message='Invalid plan schema.')]
    except PlanValidationFailure as exc:
        initialized['metadata']['plan_validation'] = exc.diagnostic
        initialized['errors'] = [ExecutionError(
            code='invalid_plan', message='The proposed plan did not pass validation.',
        )]
    except ValueError:
        initialized['errors'] = [ExecutionError(
            code='invalid_plan', message='The proposed plan did not pass validation.',
        )]
    else:
        initialized.update(plan=plan, order=order,
                           task_statuses={task_id: 'pending' for task_id in order})
    if integrated and initialized['errors']:
        initialized['plan'] = None
    return initialized


def execute_task(state, runtime, registry, *, persistent, real, approvals):
    task = state['task']
    agent, capability = registry.lookup(task.capability)
    if persistent:
        get_stream_writer()({
            'type': 'agent_started', 'task_id': task.task_id, 'status': 'running',
            'data': {'agent': agent.identifier, 'capability': capability.name},
        })
    started = perf_counter()
    fields = dict(task_id=task.task_id, capability=capability.name, agent=agent.identifier)
    try:
        validated = resolve_inputs(task, capability, state['prerequisites'])
    except (KeyError, TypeError, ValidationError):
        result = TaskResult(**fields, status='failed', error=ExecutionError(
            code='invalid_resolved_inputs', message='Resolved task inputs failed validation.',
        ))
    else:
        try:
            if persistent and capability.name not in registry.visible(
                runtime.context, allow_approvals=approvals,
            ):
                raise DispatchFailure(
                    'unauthorized_capability', 'The capability is no longer authorized.',
                )
            if approvals and capability.approval_required:
                record = state['approval']
                context = runtime.context
                if (record.get('status') != 'approved'
                        or record.get('inputs') != validated.model_dump(mode='json')
                        or (record.get('user_id'), record.get('company_id'))
                        != (context.user_id, context.company_id)):
                    raise DispatchFailure(
                        'approval_invalid', 'Approval does not match the operation.',
                    )
            if real:
                dispatch_context = replace(
                    runtime.context,
                    thread_id=state.get('thread_id'),
                    execution_id=state.get('execution_id'),
                    task_id=task.task_id,
                )
                output, metadata = dispatch_real(
                    registry,
                    capability.name,
                    validated,
                    dispatch_context,
                    approval=state.get('approval') if approvals else None,
                )
            else:
                output = capability.mock_executor(
                    validated, deepcopy(state['prerequisites']), runtime.context,
                )
                metadata = {}
            if isinstance(output, capability.output_schema):
                output = output.model_dump()
            checked = capability.output_schema.model_validate(output, strict=True)
            result = TaskResult(
                **fields, status='done', output=checked.model_dump(mode='json'),
                metadata=metadata,
            )
        except DispatchFailure as exc:
            result = TaskResult(**fields, status='failed', error=exc.error, metadata=exc.metadata)
        except ValidationError:
            result = TaskResult(**fields, status='failed', error=ExecutionError(
                code='invalid_task_output', message='Task output failed validation.',
            ))
        except Exception:
            result = TaskResult(**fields, status='failed', error=ExecutionError(
                code='specialist_failed' if real else 'mock_execution_failed',
                message='Specialist execution failed.' if real else 'Mock executor raised an error.',
            ))
    result.metadata['duration_ms'] = round((perf_counter() - started) * 1000, 3)
    return {'results': {task.task_id: result}}


def observe_execution(state, errors, *, mode='mock'):
    plan = state['plan']
    results = [state['results'][task.task_id] for task in plan.tasks]
    completed = [result for result in results if result.status == 'done']
    failed = [result for result in results if result.status == 'failed']
    blocked = [result for result in results if result.status == 'blocked']
    status = 'done' if not errors else 'partial' if completed else 'failed'
    summary = ExecutionSummary(
        request=state['request'], goal=plan.goal, plan=plan, status=status,
        completed=completed, failed=failed, blocked=blocked, errors=errors,
    )
    lines = [
        f'{"Specialist" if mode == "real" else "Mock"} run {status}: '
        f'{len(completed)} completed, {len(failed)} failed, {len(blocked)} blocked.',
        f'Goal: {plan.goal}',
    ]
    if mode == 'real':
        lines = [f'Specialist run {status}: {len(completed)} completed, '
                 f'{len(failed)} failed, {len(blocked)} blocked.',
                 f'Goal: {plan.goal}']
        create_outputs = [
            result.output for result in completed
            if result.capability == 'database.create_project' and result.output
        ]
        if create_outputs:
            created = create_outputs[0]
            lines.append(
                f"Project saved: {created.get('name', 'Unknown')} "
                f"(ID {created.get('project_id')})."
            )
            if created.get('deadline'):
                lines.append(f"Deadline: {created['deadline']}.")
            if created.get('requirements_created') is not None:
                lines.append(
                    f"Requirements saved: {created['requirements_created']}."
                )
            if created.get('warnings'):
                lines.append('Warnings: ' + '; '.join(created['warnings'])[:1000])
        ranking_outputs = [
            result.output for result in completed
            if result.capability == 'matching.rank' and result.output
        ]
        if ranking_outputs:
            ranking = ranking_outputs[0]
            structured = ranking.get('structured_output') if isinstance(ranking, dict) else None
            candidates = structured.get('candidates', []) if structured else []
            if candidates:
                lines.append('Recommendations:')
                for candidate in candidates[:5]:
                    lines.append(
                        f"- Employee {candidate['employee_id']}: "
                        f"rank {candidate['rank']}, score {candidate['model_score']:.6f}"
                    )
            else:
                lines.append('Recommendations: no eligible employees found.')
    for result in results:
        import json
        detail = (json.dumps(result.output, ensure_ascii=True, sort_keys=True)
                  if result.error is None else f'{result.error.code}: {result.error.message}')
        if len(detail) > 300:
            detail = detail[:297] + '...'
        lines.append(f'- {result.task_id} ({result.status}): {detail}')
    return summary, '\n'.join(lines)


def finish_turn(state, *, integrated, mode):
    statuses = state['task_statuses']
    errors = [*state['errors'], *(result.error for result in state.get('results', {}).values()
                                  if result.error is not None)]
    done = sum(status == 'done' for status in statuses.values())
    update = {
        'errors': errors,
        'final_response': ('Plan rejected.' if not state['order']
                           else f'{done} of {len(statuses)} mock tasks completed.'),
        'metadata': {**state['metadata'], 'status': 'failed' if errors else 'done',
                     'task_count': len(statuses)},
    }
    if integrated:
        if state['order']:
            summary, response = observe_execution(state, errors, mode=mode)
            update.update(execution_summary=summary, final_response=response)
            update['metadata']['status'] = summary.status
        else:
            update['final_response'] = state['decision'].response
        update['messages'] = [AIMessage(content=update['final_response'])]
    return update
