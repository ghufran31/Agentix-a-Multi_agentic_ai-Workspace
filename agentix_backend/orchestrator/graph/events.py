"""Translate LangGraph runtime updates into a browser-safe event contract."""
from datetime import datetime, timezone

from langgraph.types import Command

from .console_contract import safe_task_error


def stream_execution(graph, data, config, context, execution_id, publish):
    def emit(event_type, status, task_id=None, **details):
        publish({
            'type': event_type, 'execution_id': execution_id, 'task_id': task_id,
            'timestamp': datetime.now(timezone.utc).isoformat(), 'status': status,
            'data': details,
        })

    paused = False
    try:
        for mode, update in graph.stream(
            data, config, context=context, durability='sync', stream_mode=['updates', 'custom'],
        ):
            if mode == 'custom':
                emit(update['type'], update['status'], update['task_id'], **update['data'])
                continue
            for node, change in update.items():
                if node == 'begin_turn' and not isinstance(data, Command):
                    emit('conversation_started', 'running')
                elif node == 'plan_turn':
                    issues = change['errors']
                    emit('planner_decision', change['decision'].outcome,
                         error_code=issues[0].code if issues else None)
                elif node == 'validate' and not change['errors']:
                    emit('plan_validated', 'running', task_count=len(change['order']))
                elif node == 'schedule':
                    for task_id in change['ready']:
                        emit('task_scheduled', 'running', task_id)
                elif node == '__interrupt__':
                    for item in change:
                        emit('approval_requested', 'pending', item.value['task_id'],
                             approval_id=item.value['approval_id'])
                    paused = True
                elif node == 'approval_gate':
                    for record in change['approval_records'].values():
                        if record['approval_id'] == _resumed_approval(data):
                            emit('approval_resolved', record['status'], record['task_id'],
                                 approval_id=record['approval_id'])
                if node in {'schedule', 'execute', 'approval_gate'}:
                    for result in change.get('results', {}).values():
                        kind = {'done': 'agent_completed', 'failed': 'agent_failed',
                                'blocked': 'task_blocked'}[result.status]
                        error = safe_task_error(result)
                        diagnostics = {key: value for key, value in (error or {}).items() if key != 'code'}
                        emit(kind, result.status, result.task_id, agent=result.agent,
                             capability=result.capability,
                             error_code=error['code'] if error else None,
                             **diagnostics)
        snapshot = graph.get_state(config)
        state = snapshot.values
        if not paused and not snapshot.next:
            summary = state.get('execution_summary')
            status = summary.status if summary else state['decision'].outcome
            failed = status in {'failed', 'planning_error'}
            issues = state.get('errors', [])
            emit('execution_failed' if failed else 'execution_completed', status,
                 error_code=issues[0].code if issues else None)
        return state
    except Exception:
        emit('execution_failed', 'failed', error_code='execution_interrupted')
        raise


def _resumed_approval(command):
    if isinstance(command, Command):
        return next(iter(command.resume.values()))['approval_id']
    return None
