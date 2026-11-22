import secrets
from copy import deepcopy
from dataclasses import dataclass


@dataclass(frozen=True)
class PendingApproval:
    approval_id: str
    operation: str
    target: dict
    proposed_changes: dict
    context_company_id: int
    context_user_id: int


class ApprovalRegistry:
    def __init__(self):
        self._pending = {}

    def prepare(self, *, operation, target, proposed_changes, context):
        approval_id = secrets.token_urlsafe(16)
        item = PendingApproval(
            approval_id=approval_id,
            operation=operation,
            target=deepcopy(target),
            proposed_changes=deepcopy(proposed_changes),
            context_company_id=context.company.id,
            context_user_id=context.user.id,
        )
        self._pending[approval_id] = item
        return item

    def get(self, approval_id):
        return self._pending.get(approval_id)

    def resolve(self, approval_id, *, approved, context):
        item = self._pending.get(approval_id)
        if not item:
            return None
        if (
            item.context_company_id != context.company.id
            or item.context_user_id != context.user.id
        ):
            return None
        if approved:
            del self._pending[approval_id]
            return item
        del self._pending[approval_id]
        return item


approval_registry = ApprovalRegistry()
