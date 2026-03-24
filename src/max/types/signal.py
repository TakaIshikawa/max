"""Signal — normalized data from any external source."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class SignalSourceType(StrEnum):
    REGISTRY = "registry"
    FORUM = "forum"
    SECURITY = "security"
    SURVEY = "survey"
    ROADMAP = "roadmap"
    FAILURE_DATA = "failure_data"
    FUNDING = "funding"
    TRENDING = "trending"


class Signal(BaseModel):
    id: str = Field(default="")
    source_type: SignalSourceType
    source_adapter: str
    title: str
    content: str
    url: str
    author: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tags: list[str] = Field(default_factory=list)
    credibility: float = 0.5
    metadata: dict = Field(default_factory=dict)
