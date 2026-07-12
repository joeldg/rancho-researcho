"""Stable HTTP models for the Phase 1 search compatibility API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


# @spec[RANCHO_API_SECURITY.md#http-contract]
class SearchRequest(BaseModel):
    """A bounded Parkour-compatible search request."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2_000)
    max_results: int = Field(default=5, ge=1, le=20)


# @spec[RANCHO_API_SECURITY.md#http-contract]
class SearchResult(BaseModel):
    """One normalized and evidence-bearing search result."""

    url: HttpUrl
    title: str = Field(min_length=1, max_length=500)
    snippet: str = Field(min_length=1, max_length=2_000)
    source_id: str
    published_at: datetime | None = None
    retrieved_at: datetime


# @spec[RANCHO_API_SECURITY.md#http-contract]
class SearchResponse(BaseModel):
    """Successful response accepted by Parkour's search integration."""

    results: list[SearchResult]
    provider: str = "rancho-agent"
    request_id: str
    warnings: list[str] = Field(default_factory=list)


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
class ResearchRequest(BaseModel):
    """A bounded deep-research task request."""

    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1, max_length=2_000)
    max_sources: int = Field(default=10, ge=1, le=50)


# @spec[RANCHO_FINDALL_AND_MONITORS.md#requirements]
class FindAllRequest(BaseModel):
    """A bounded candidate-discovery task with a simple declared schema."""

    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1, max_length=2_000)
    output_schema: dict[str, str]
    max_sources: int = Field(default=10, ge=1, le=50)

    @field_validator("output_schema")
    @classmethod
    def validate_output_schema(cls, value: dict[str, str]) -> dict[str, str]:
        if not 1 <= len(value) <= 20:
            raise ValueError("output_schema must contain 1 to 20 fields")
        for name, kind in value.items():
            if not name or len(name) > 64 or not name.replace("_", "a").isalnum():
                raise ValueError("invalid output_schema field name")
            if kind not in {"string", "number", "boolean"}:
                raise ValueError("unsupported output_schema field type")
        return value


class CandidateResult(BaseModel):
    id: str
    fields: dict
    evidence_ids: list[str]


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
class ResearchTaskAccepted(BaseModel):
    """The 202 acceptance payload for a created or replayed research task."""

    task_id: str
    status: str
    status_url: str


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
class ResearchTaskState(BaseModel):
    """The current durable state of a research task."""

    task_id: str
    task_type: str
    status: str
    attempt: int
    evidence_count: int
    claim_count: int
    result: str | None
    candidates: list[CandidateResult] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# @spec[RANCHO_API_SECURITY.md#http-contract]
class ErrorDetail(BaseModel):
    """Machine-readable error payload."""

    code: str
    message: str


# @spec[RANCHO_API_SECURITY.md#http-contract]
class ErrorResponse(BaseModel):
    """Response returned when a provider cannot serve a request."""

    error: ErrorDetail
    request_id: str
