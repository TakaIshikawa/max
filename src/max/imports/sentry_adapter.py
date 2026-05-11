"""Sentry issue import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
SENTRY_API = "https://sentry.io/api/0"


class SentryIssueAdapter(SourceAdapter):
    def __init__(self, config: dict | None = None, *, token: str | None = None, api_url: str = SENTRY_API, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(config)
        self.token = token if token is not None else os.getenv("SENTRY_AUTH_TOKEN")
        self.api_url = api_url.rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "sentry_issue_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def organization_slug(self) -> str | None:
        value = self._config.get("organization_slug")
        return value if isinstance(value, str) and value else None

    @property
    def project_slugs(self) -> list[str]:
        return _strings(self._config.get("project_slugs"))

    @property
    def environments(self) -> list[str]:
        return _strings(self._config.get("environments"))

    @property
    def statuses(self) -> list[str]:
        return _strings(self._config.get("statuses"))

    @property
    def query(self) -> str | None:
        value = self._config.get("query")
        return value if isinstance(value, str) and value else None

    @property
    def stats_period(self) -> str:
        value = self._config.get("stats_period", "14d")
        return value if isinstance(value, str) and value else "14d"

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.token and self.organization_slug):
            return []
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            issues = await self._get_issues(client, limit)
        finally:
            if close_client:
                await client.aclose()
        seen: set[str] = set()
        signals: list[Signal] = []
        for issue in issues:
            issue_id = _text(issue.get("id"))
            if not issue_id or issue_id in seen:
                continue
            seen.add(issue_id)
            signals.append(_issue_signal(issue, self.name))
            if len(signals) >= limit:
                break
        return signals

    async def _get_issues(self, client: httpx.AsyncClient, limit: int) -> list[dict[str, Any]]:
        params: list[tuple[str, str | int]] = [("limit", min(limit, 100)), ("statsPeriod", self.stats_period)]
        for project in self.project_slugs:
            params.append(("project", project))
        for environment in self.environments:
            params.append(("environment", environment))
        query_parts = []
        if self.query:
            query_parts.append(self.query)
        query_parts.extend(f"status:{status}" for status in self.statuses)
        if query_parts:
            params.append(("query", " ".join(query_parts)))
        try:
            response = await client.get(f"{self.api_url}/organizations/{self.organization_slug}/issues/", headers={"Authorization": f"Bearer {self.token}"}, params=params)
            response.raise_for_status()
            data = response.json()
        except Exception:
            logger.warning("Sentry issue fetch failed", exc_info=True)
            return []
        return data if isinstance(data, list) else []


def _issue_signal(issue: dict[str, Any], adapter_name: str) -> Signal:
    tags = issue.get("tags") if isinstance(issue.get("tags"), list) else []
    tag_names = [_text(tag.get("value") or tag.get("key")) for tag in tags if isinstance(tag, dict)]
    count = _int(issue.get("count"))
    users = _int(issue.get("userCount"))
    return Signal(
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=_text(issue.get("title")) or _text(issue.get("shortId")) or _text(issue.get("id")),
        content=_text(issue.get("culprit"))[:1000],
        url=_text(issue.get("permalink")),
        author=None,
        published_at=_parse_dt(issue.get("firstSeen")),
        tags=sorted({"sentry", _text(issue.get("level")), _text(issue.get("status")), *tag_names} - {""})[:10],
        credibility=min((count + users) / 1000, 1.0),
        metadata={"sentry_issue_id": issue.get("id"), "short_id": issue.get("shortId"), "culprit": issue.get("culprit"), "level": issue.get("level"), "status": issue.get("status"), "count": count, "user_count": users, "first_seen": issue.get("firstSeen"), "last_seen": issue.get("lastSeen"), "tags": tag_names},
    )


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
