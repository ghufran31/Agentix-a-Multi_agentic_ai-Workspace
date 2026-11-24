from hashlib import sha256
import json
from time import time
from typing import Literal
from uuid import uuid4

from langgraph.types import interrupt
from pydantic import Field, JsonValue, ValidationError

from orchestrator.core.plan_schemas import Contract, ExecutionError, TaskResult


class ApprovalRequest(Contract):
    approval_id: str
    thread_id: str
    execution_id: str
    task_id: str
    capability: str
    summary: str
    inputs: dict[str, JsonValue]
    user_id: int
    company_id: int
    operation_key: str
    expires_at: float
    status: Literal['pending', 'approved', 'rejected', 'expired', 'invalid'] = 'pending'
    review: dict[str, JsonValue] = Field(default_factory=dict)


class ApprovalDecision(Contract):
    approval_id: str = Field(min_length=1, max_length=64)
    approved: bool


def operation_key(thread_id, execution_id, task_id, capability, inputs):
    """Bind a future durable write receipt to one validated operation."""
    encoded = json.dumps(
        [thread_id, execution_id, task_id, capability, inputs],
        sort_keys=True, separators=(',', ':'), allow_nan=False,
    ).encode()
    return sha256(encoded).hexdigest()


def new_request(state, context, task, inputs, ttl):
    payload = inputs.model_dump(mode='json')
    review = {}
    if task.capability == 'database.create_project':
        specification = payload.get('specification', {})
        if isinstance(specification, dict):
            if specification.get('outcome') == 'specification':
                specification = specification.get('specification', {})
            review = {
                'project_name': specification.get('name'),
                'description': specification.get('description'),
                'project_type': specification.get('project_type'),
                'roles': [
                    role.get('name') for role in specification.get('required_roles', [])
                    if isinstance(role, dict) and role.get('name')
                ],
                'skills': [
                    skill.get('name') for skill in specification.get('required_skills', [])
                    if isinstance(skill, dict) and skill.get('name')
                ],
                'deadline': specification.get('deadline'),
                'fields_saved': [
                    'name', 'description', 'deadline', 'status', 'priority', 'requirements',
                ],
                'requirements_not_persisted': [
                    item.get('description')
                    for item in specification.get('nonfunctional_requirements', [])
                    if isinstance(item, dict) and item.get('description')
                ],
                'additional_fields_not_persisted': [
                    field for field in (
                        'technology_stack', 'milestones', 'constraints',
                        'assumptions', 'risks', 'limitations',
                    ) if specification.get(field)
                ],
                'persistence_performed': False,
            }
    return ApprovalRequest(
        approval_id=uuid4().hex, thread_id=state['thread_id'], execution_id=state['execution_id'],
        task_id=task.task_id, capability=task.capability, summary=task.description,
        inputs=payload, user_id=context.user_id, company_id=context.company_id,
        operation_key=operation_key(state['thread_id'], state['execution_id'], task.task_id,
                                    task.capability, payload),
        expires_at=time() + ttl,
        review=review,
    ).model_dump(mode='json')


def approval_node(registry):
    def decide(state, runtime):
        request = ApprovalRequest.model_validate(state['pending_approvals'][0])
        raw = interrupt(request.model_dump(mode='json'))
        context = runtime.context
        try:
            decision = ApprovalDecision.model_validate(raw)
            valid = (
                decision.approval_id == request.approval_id
                and (context.user_id, context.company_id) == (request.user_id, request.company_id)
                and request.capability in registry.visible(context, allow_approvals=True)
                and 'approvals.decide' in context.permissions
            )
        except ValidationError:
            valid = False
        if not valid:
            status = 'invalid'
        elif time() >= request.expires_at:
            status = 'expired'
        else:
            status = 'approved' if decision.approved else 'rejected'
        terminal = request.model_copy(update={'status': status})
        changes = {
            'pending_approvals': [],
            'approval_records': {**state['approval_records'],
                                 request.task_id: terminal.model_dump(mode='json')},
        }
        if status != 'approved':
            agent, _ = registry.lookup(request.capability)
            changes['results'] = {request.task_id: TaskResult(
                task_id=request.task_id, agent=agent.identifier, capability=request.capability,
                status='blocked', error=ExecutionError(
                    code=f'approval_{status}', message=f'The approval was {status}.',
                ),
            )}
        return changes

    return decide
