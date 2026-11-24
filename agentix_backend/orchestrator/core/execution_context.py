from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionContext:
    """Server-owned runtime context. Never deserialize this from a plan."""

    user_id: int
    company_id: int
    allowed_capabilities: frozenset[str]
    permissions: frozenset[str] = frozenset()
    thread_id: str | None = None
    execution_id: str | None = None
    task_id: str | None = None
    project_deadline: str | None = None

    @classmethod
    def from_django(cls, context, *, allowed_capabilities, permissions=()):
        context.require_read()
        return cls(context.user.pk, context.company.pk,
                   frozenset(allowed_capabilities), frozenset(permissions))
