from __future__ import annotations

from pydantic import BaseModel, Field


class KnowledgeFilters(BaseModel):
    source_type: str | None = None
    document_type: str | None = None
    service: str | None = None
    namespace: str | None = None
    severity: str | None = None
    phase: str | None = None
    tags: list[str] = Field(default_factory=list)


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=5, ge=1, le=50)
    filters: KnowledgeFilters = Field(default_factory=KnowledgeFilters)
