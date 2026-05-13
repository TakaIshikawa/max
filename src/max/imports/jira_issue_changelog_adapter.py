"""Jira issue changelog import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class JiraIssueChangelogImportAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.base_url = (base_url or _optional(self._config.get("base_url")) or os.getenv("JIRA_BASE_URL") or "").rstrip("/")
        self.email = email if email is not None else (_optional(self._config.get("email")) or os.getenv("JIRA_EMAIL") or os.getenv("JIRA_USERNAME"))
        self.api_token = api_token if api_token is not None else (token if token is not None else (_optional(self._config.get("api_token")) or _optional(self._config.get("token")) or os.getenv("JIRA_API_TOKEN")))
        self._client = client

    @property
    def name(self) -> str:
        return "jira_issue_changelog_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def issue_keys(self) -> list[str]:
        return _strings(self._config.get("issue_keys") or self._config.get("issue_key"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("max_results"), default=50, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.base_url and self.email and self.api_token and self.issue_keys):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            seen: set[str] = set()
            for issue_key in self.issue_keys:
                if len(signals) >= limit:
                    break
                histories = await self._fetch_issue_changelog(client, issue_key=issue_key, limit=limit - len(signals))
                for history in histories:
                    signal = _history_signal(history, issue_key=issue_key, adapter_name=self.name, base_url=self.base_url, seen=seen)
                    if signal:
                        signals.append(signal)
                    if len(signals) >= limit:
                        break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_issue_changelog(self, client: httpx.AsyncClient, *, issue_key: str, limit: int) -> list[dict[str, Any]]:
        histories: list[dict[str, Any]] = []
        start_at = 0
        while len(histories) < limit:
            max_results = min(self.page_size, limit - len(histories))
            body = await self._fetch_page(client, issue_key=issue_key, start_at=start_at, max_results=max_results)
            values = body.get("values") if isinstance(body.get("values"), list) else []
            page = [item for item in values if isinstance(item, dict)]
            if not page:
                break
            histories.extend(page)
            total = _int(body.get("total"))
            start_at = _int(body.get("startAt"), start_at) + len(values)
            if start_at >= total or len(values) < max_results:
                break
        return histories[:limit]

    async def _fetch_page(self, client: httpx.AsyncClient, *, issue_key: str, start_at: int, max_results: int) -> dict[str, Any]:
        try:
            response = await client.get(
                f"{self.base_url}/rest/api/3/issue/{issue_key}/changelog",
                auth=(self.email or "", self.api_token or ""),
                params={"startAt": start_at, "maxResults": max_results},
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Jira issue changelog fetch failed for %s", issue_key, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


JiraIssueChangelogAdapter = JiraIssueChangelogImportAdapter


def _history_signal(
    history: dict[str, Any],
    *,
    issue_key: str,
    adapter_name: str,
    base_url: str,
    seen: set[str],
) -> Signal | None:
    changelog_id = _optional(history.get("id"))
    if not changelog_id:
        return None
    signal_id = f"jira-issue-changelog:{issue_key}:{changelog_id}"
    if signal_id in seen:
        return None
    seen.add(signal_id)

    author = history.get("author") if isinstance(history.get("author"), dict) else {}
    changed_fields = _changed_fields(history)
    changed_text = ", ".join(changed_fields) if changed_fields else "fields"
    author_name = _optional(author.get("displayName")) or _optional(author.get("emailAddress")) or _optional(author.get("accountId"))
    created = history.get("created")
    return Signal(
        id=signal_id,
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{issue_key} changelog updated {changed_text}",
        content=_content(issue_key=issue_key, changed_fields=changed_fields, history=history, author=author_name),
        url=f"{base_url}/browse/{issue_key}" if issue_key else base_url,
        author=author_name,
        published_at=_parse_dt(created),
        tags=sorted({"jira", "changelog", *changed_fields} - {""})[:10],
        credibility=0.66,
        metadata={
            "issue_key": issue_key,
            "changelog_id": changelog_id,
            "changed_fields": changed_fields,
            "items": history.get("items") if isinstance(history.get("items"), list) else [],
            "author": {
                "account_id": author.get("accountId"),
                "display_name": author.get("displayName"),
                "email": author.get("emailAddress"),
                "active": author.get("active"),
            },
            "created_at": created,
            "raw": history,
        },
    )


def _content(*, issue_key: str, changed_fields: list[str], history: dict[str, Any], author: str | None) -> str:
    parts = [f"Jira issue {issue_key} changelog"]
    if changed_fields:
        parts.append(f"changed {', '.join(changed_fields)}")
    if author:
        parts.append(f"by {author}")
    item_summaries = []
    for item in history.get("items", []) if isinstance(history.get("items"), list) else []:
        if isinstance(item, dict):
            field = _text(item.get("field"))
            before = _text(item.get("fromString"))
            after = _text(item.get("toString"))
            if field:
                item_summaries.append(f"{field}: {before or '-'} -> {after or '-'}")
    if item_summaries:
        parts.append("; ".join(item_summaries[:5]))
    return "; ".join(parts)[:1000]


def _changed_fields(history: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    for item in history.get("items", []) if isinstance(history.get("items"), list) else []:
        if isinstance(item, dict):
            field = _text(item.get("field"))
            if field and field not in fields:
                fields.append(field)
    return fields


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


def _positive_int(value: object, *, default: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number <= 0:
        return default
    return min(number, maximum)


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
