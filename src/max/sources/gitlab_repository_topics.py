"""GitLab repository topics source adapter."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class GitLabRepositoryTopicsAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "gitlab_repository_topics"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def gitlab_url(self) -> str:
        return str(self._config.get("gitlab_url") or "https://gitlab.com/api/v4").strip().rstrip("/")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        headers = {}
        token = self._config.get("private_token") or self._config.get("token") or self._config.get("gitlab_token")
        if token:
            headers["PRIVATE-TOKEN"] = str(token)
        signals: list[Signal] = []
        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for topic in _strings(self._config.get("topics")):
                response = await client.get(
                    f"{self.gitlab_url}/projects",
                    params={"topic": topic, "per_page": int(self._config.get("max_projects_per_topic") or limit), "order_by": "last_activity_at"},
                )
                if response.status_code >= 400:
                    continue
                for project in response.json():
                    signals.append(_signal(project, topic))
                    if len(signals) >= limit:
                        return signals
        return signals


def _signal(project: dict[str, Any], topic: str) -> Signal:
    project_topics = project.get("topics") or project.get("tag_list") or []
    namespace = project.get("namespace") if isinstance(project.get("namespace"), dict) else {}
    url = project.get("web_url") or ""
    path = project.get("path_with_namespace") or project.get("name_with_namespace") or project.get("name") or project.get("id")
    return Signal(
        id=_id("gitlab-topic", project.get("id") or path, topic),
        source_type=SignalSourceType.REGISTRY,
        source_adapter="gitlab_repository_topics",
        title=f"{path} GitLab repository topics",
        content=f"{path} is associated with GitLab topic {topic}.",
        url=str(url),
        published_at=_parse_dt(project.get("last_activity_at")),
        tags=["gitlab", "repository-topics", topic],
        credibility=min(max(float(project.get("star_count") or 0) / 1000, 0.25), 1.0),
        metadata={"project_id": project.get("id"), "repository": path, "stars": project.get("star_count") or 0, "forks": project.get("forks_count") or 0, "last_activity_at": project.get("last_activity_at") or "", "namespace": namespace.get("full_path") or namespace.get("name") or "", "topics": project_topics, "matched_topic": topic, "source_url": url, "signal_role": "market"},
    )


def _strings(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else list(value or [])
    return [str(v).strip() for v in values if str(v).strip()]


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _id(*parts: object) -> str:
    return hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()[:16]
