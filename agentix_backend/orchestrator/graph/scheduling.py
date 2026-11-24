from langgraph.types import Send

from orchestrator.core.plan_schemas import ExecutionError, TaskResult
from .approvals import new_request
from .nodes import resolve_inputs


def schedule_tasks(state, runtime, registry, *, approvals, approval_ttl):
    statuses = state['task_statuses'].copy()
    results = state.get('results', {})
    for task_id, result in results.items():
        statuses[task_id] = result.status
    ready, blocked, gated = [], {}, []
    if state['order']:
        tasks = {task.task_id: task for task in state['plan'].tasks}
        for task_id in state['order']:
            if statuses[task_id] != 'pending':
                continue
            task = tasks[task_id]
            prerequisites = [statuses[dep] for dep in task.depends_on]
            if any(status in {'failed', 'blocked'} for status in prerequisites):
                agent, _ = registry.lookup(task.capability)
                statuses[task_id] = 'blocked'
                blocked[task_id] = TaskResult(
                    task_id=task_id, capability=task.capability, agent=agent.identifier,
                    status='blocked', error=ExecutionError(
                        code='prerequisite_failed', message='A prerequisite did not complete.',
                    ),
                )
            elif all(status == 'done' for status in prerequisites):
                if approvals:
                    agent, capability = registry.lookup(task.capability)
                    if capability.approval_required and task_id not in state['approval_records']:
                        try:
                            inputs = resolve_inputs(task, capability, results)
                        except (KeyError, TypeError, ValueError):
                            statuses[task_id] = 'failed'
                            blocked[task_id] = TaskResult(
                                task_id=task_id, capability=capability.name,
                                agent=agent.identifier, status='failed',
                                error=ExecutionError(
                                    code='invalid_resolved_inputs',
                                    message='Resolved task inputs failed validation.',
                                ),
                            )
                        else:
                            gated.append((task, inputs))
                        continue
                statuses[task_id] = 'running'
                ready.append(task_id)
    update = {'task_statuses': statuses, 'ready': ready, 'results': blocked}
    if approvals:
        update['pending_approvals'] = (
            [new_request(state, runtime.context, *gated[0], approval_ttl)]
            if gated and not ready else []
        )
    return update


def route_tasks(state):
    if not state['ready']:
        return 'approval_gate' if state['pending_approvals'] else 'finish'
    tasks = {task.task_id: task for task in state['plan'].tasks}
    return [
        Send('execute', {
            'task': tasks[task_id],
            'approval': state.get('approval_records', {}).get(task_id, {}),
            'thread_id': state.get('thread_id'),
            'execution_id': state.get('execution_id'),
            'prerequisites': {
                dependency: state['results'][dependency]
                for dependency in tasks[task_id].depends_on
            },
        })
        for task_id in state['ready']
    ]
