from pydantic import BaseModel, ConfigDict, Field, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class MatchingRequest(StrictModel):
    project_id: int = Field(gt=0)
    top_n: int = Field(default=5, ge=1, le=25)
    available_only: bool = False
    role_filter: str | None = Field(default=None, max_length=150)
    skill_filter: list[str] = Field(default_factory=list, max_length=30)

class RankedCandidate(StrictModel):
    employee_id: int
    employee_name: str
    rank: int
    model_score: float = Field(ge=0, le=1)
    matched_skills: list[str]
    missing_skills: list[str]
    availability_status: str
    explanation: str

class MatchingExecutionMetadata(StrictModel):
    project_id: int
    candidate_count: int
    eligible_count: int
    ranked_count: int
    complete: bool
    model_artifact: str
    score_semantics: str
    warnings: list[str] = Field(default_factory=list)

class MatchingResponse(StrictModel):
    success: bool
    answer: str
    candidates: list[RankedCandidate] = Field(default_factory=list)
    exclusions: list[dict] = Field(default_factory=list)
    metadata: MatchingExecutionMetadata | None = None
    error: str | None = None

    @model_validator(mode='after')
    def consistent_result(self):
        if not self.success:
            if not self.error or self.candidates or self.metadata:
                raise ValueError('A failed ranking requires an error and no ranking data.')
            return self
        meta = self.metadata
        if self.error or not meta or not meta.complete or not (
            0 <= len(self.candidates) == meta.ranked_count <= meta.eligible_count <= meta.candidate_count
        ):
            raise ValueError('Ranking metadata and candidate counts must agree.')
        if [row.rank for row in self.candidates] != list(range(1, meta.ranked_count + 1)):
            raise ValueError('Candidate ranks must be consecutive.')
        keys = [(-row.model_score, row.employee_id) for row in self.candidates]
        if keys != sorted(keys) or len({row.employee_id for row in self.candidates}) != len(keys):
            raise ValueError('Candidates must be unique and ordered by score and employee ID.')
        return self

class MatchingAgentResult(StrictModel):
    success: bool
    answer: str
    structured_output: MatchingResponse | None = None
    tool_names: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    model_requests: int = 0
    model_responses: int = 0
    token_usage: dict[str, int] = Field(default_factory=dict)
