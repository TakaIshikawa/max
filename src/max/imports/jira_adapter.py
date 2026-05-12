"""Jira issue import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class JiraAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        base_url: str | None = None,
        email: str | None = None,
        token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.base_url = (base_url or _optional(self._config.get("base_url")) or os.getenv("JIRA_BASE_URL") or "").rstrip("/")
        self.email = email if email is not None else (os.getenv("JIRA_EMAIL") or os.getenv("JIRA_USERNAME"))
        self.token = token if token is not None else os.getenv("JIRA_API_TOKEN")
        self._client = client

    @property
    def name(self) -> str:
        return "jira_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def jql(self) -> str:
        return _optional(self._config.get("jql")) or "ORDER BY updated DESC"

    @property
    def max_results(self) -> int:
        value = self._config.get("max_results")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return min(value, 100)
        return 50

    @property
    def fields(self) -> list[str]:
        configured = _strings(self._config.get("fields"))
        return configured or ["summary", "description", "reporter", "assignee", "status", "priority", "labels", "components", "created", "updated", "issuetype"]

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.base_url and self.token):
            return []
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            issues: list[dict[str, Any]] = []
            start_at = 0
            while len(issues) < limit:
                body = await self._search(client, start_at=start_at, limit=limit - len(issues))
                page = body.get("issues") if isinstance(body.get("issues"), list) else []
                if not page:
                    break
                issues.extend(page)
                total = _int(body.get("total"))
                start_at = _int(body.get("startAt")) + len(page)
                if start_at >= total or len(page) < _int(body.get("maxResults"), self.max_results):
                    break
        finally:
            if close_client:
                await client.aclose()
        return [_issue_signal(issue, self.name, self.base_url) for issue in issues[:limit] if isinstance(issue, dict)]

    async def _search(self, client: httpx.AsyncClient, *, start_at: int, limit: int) -> dict[str, Any]:
        try:
            response = await client.get(
                f"{self.base_url}/rest/api/3/search",
                auth=(self.email or "", self.token or ""),
                params={"jql": self.jql, "startAt": start_at, "maxResults": min(limit, self.max_results), "fields": ",".join(self.fields)},
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Jira issue fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


JiraIssueAdapter = JiraAdapter


def _issue_signal(issue: dict[str, Any], adapter_name: str, base_url: str) -> Signal:
    fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}
    reporter = fields.get("reporter") if isinstance(fields.get("reporter"), dict) else {}
    assignee = fields.get("assignee") if isinstance(fields.get("assignee"), dict) else {}
    status = fields.get("status") if isinstance(fields.get("status"), dict) else {}
    priority = fields.get("priority") if isinstance(fields.get("priority"), dict) else {}
    issue_type = fields.get("issuetype") if isinstance(fields.get("issuetype"), dict) else {}
    labels = fields.get("labels") if isinstance(fields.get("labels"), list) else []
    components = [_text(component.get("name")) for component in fields.get("components", []) if isinstance(component, dict)]
    components = [component for component in components if component]
    key = _text(issue.get("key"))
    url = f"{base_url}/browse/{key}" if key else base_url
    description = _jira_description(fields.get("description"))
    return Signal(
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=_text(fields.get("summary")) or key or _text(issue.get("id")),
        content=description[:1000],
        url=url,
        author=_text(reporter.get("displayName")) or _text(reporter.get("emailAddress")) or None,
        published_at=_parse_dt(fields.get("created")),
        tags=sorted({"jira", _text(status.get("name")), *[_text(label) for label in labels]} - {""})[:10],
        credibility=0.7,
        metadata={
            "jira_issue_id": issue.get("id"),
            "key": key,
            "reporter": reporter.get("displayName"),
            "reporter_email": reporter.get("emailAddress"),
            "assignee": assignee.get("displayName"),
            "assignee_email": assignee.get("emailAddress"),
            "status": status.get("name"),
            "priority": priority.get("name"),
            "labels": [_text(label) for label in labels if _text(label)],
            "components": components,
            "issue_type": issue_type.get("name"),
            "created": fields.get("created"),
            "updated": fields.get("updated"),
        },
    )


def _jira_description(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return ""
    parts: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text" and isinstance(node.get("text"), str):
                parts.append(node["text"])
            for child in node.get("content", []) if isinstance(node.get("content"), list) else []:
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return " ".join(part.strip() for part in parts if part.strip())


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
