from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ResearchModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class ResearchRequest(ResearchModel):
    question: str = Field(min_length=1, max_length=4000)


class Source(ResearchModel):
    title: str
    url: HttpUrl
    excerpt: str
    provider: str


class Finding(ResearchModel):
    claim: str = Field(min_length=1, max_length=1500)
    urls: list[str] = Field(min_length=1, max_length=5)


class Summary(ResearchModel):
    answer: str = Field(min_length=1, max_length=4000)
    findings: list[Finding] = Field(max_length=12)
    comparisons: list[str] = Field(default_factory=list, max_length=10)
    limitations: list[str] = Field(default_factory=list, max_length=10)


class ResearchResult(ResearchModel):
    question: str
    status: Literal['ok', 'partial', 'error']
    summary: Summary | None = None
    sources: list[Source] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    tool_calls: list[dict] = Field(default_factory=list)
    tool_results: list[dict] = Field(default_factory=list)
    model_responses: int = 0
    tokens: int = 0
    provider_status: int | None = None
    provider_code: str | None = None
    provider_message: str | None = None
