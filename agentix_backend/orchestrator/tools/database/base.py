from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

class PaginationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ToolResult(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def decimal_value(value):
    return str(value) if isinstance(value, Decimal) else value


def success(operation, message, data=None, pending_approval=None):
    return ToolResult({
        'success': True,
        'operation': operation,
        'message': message,
        'data': data or {},
        'errors': [],
        'pending_approval': pending_approval,
    })


def failure(operation, message, errors=None, data=None):
    return ToolResult({
        'success': False,
        'operation': operation,
        'message': message,
        'data': data or {},
        'errors': errors or [message],
        'pending_approval': None,
    })
