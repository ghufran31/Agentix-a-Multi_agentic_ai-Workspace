from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolExecutionResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    success: bool
    operation: str
    message: str
    data: dict = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    pending_approval: dict | None = None


class DatabaseAgentResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    answer: str
    success: bool = True
    tool_names: list[str] = Field(default_factory=list)
    execution_results: list[ToolExecutionResult] = Field(default_factory=list)
    pending_approval: dict | None = None


class PaginationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
