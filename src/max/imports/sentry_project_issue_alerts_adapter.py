"""Sentry project issue alerts import adapter."""

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


class SentryProjectIssueAlertsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        auth_token: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            auth_token
            if auth_token is not None
            else (
                token
                if token is not None
                else (
                    _optional(self._config.get("auth_token"))
                    or _optional(self._config.get("token"))
                    or os.getenv("SENTRY_AUTH_TOKEN")
                )
            )
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or SENTRY_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "sentry_project_issue_alerts_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def organization_slug(self) -> str | None:
        return _optional(self._config.get("organization_slug") or self._config.get("org"))

    @property
    def project_slug(self) -> str | None:
        return _optional(self._config.get("project_slug") or self._config.get("project"))

    @property
    def cursor(self) -> str | None:
        return _optional(self._config.get("cursor"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=25, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.organization_slug or not self.project_slug:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            rules = await self._fetch_rules(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        return [
            _alert_signal(rule, project_slug=self.project_slug, adapter_name=self.name)
            for rule in rules[:limit]
            if isinstance(rule, dict)
        ]

    async def _fetch_rules(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        rules: list[dict[str, Any]] = []
        cursor = self.cursor
        while len(rules) < limit:
            page_size = min(self.page_size, limit - len(rules))
            page_rules, cursor = await self._fetch_page(client, cursor=cursor, page_size=page_size)
            if not page_rules:
                break
            rules.extend(page_rules[: limit - len(rules)])
            if not cursor:
                break
        return rules[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        cursor: str | None,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        params: dict[str, Any] = {"per_page": page_size}
        if cursor:
            params["cursor"] = cursor
        url = f"{self.api_url}/projects/{self.organization_slug}/{self.project_slug}/rules/"
        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-sentry-project-issue-alerts-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Sentry project issue alerts fetch failed", exc_info=True)
            return [], None
        rules = [item for item in body if isinstance(item, dict)] if isinstance(body, list) else []
        return rules, _next_cursor(response)


SentryProjectIssueAlertAdapter = SentryProjectIssueAlertsAdapter


def _alert_signal(rule: dict[str, Any], *, project_slug: str | None, adapter_name: str) -> Signal:
    rule_id = _text(rule.get("id"))
    name = _text(rule.get("name")) or f"Sentry issue alert {rule_id}"
    action_match = _text(rule.get("actionMatch") or rule.get("action_match"))
    filter_match = _text(rule.get("filterMatch") or rule.get("filter_match"))
    frequency = _int(rule.get("frequency"))
    environment = _text(rule.get("environment"))
    actions = _list_of_dicts(rule.get("actions"))
    conditions = _list_of_dicts(rule.get("conditions"))
    filters = _list_of_dicts(rule.get("filters"))
    return Signal(
        id=f"sentry-issue-alert:{project_slug}:{rule_id}" if rule_id else f"sentry-issue-alert:{project_slug}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=name,
        content=_content(
            name=name,
            action_match=action_match,
            filter_match=filter_match,
            frequency=frequency,
            environment=environment,
            action_count=len(actions),
            condition_count=len(conditions),
            filter_count=len(filters),
        ),
        url=_alert_url(rule, project_slug=project_slug),
        author=None,
        published_at=_parse_dt(rule.get("dateCreated") or rule.get("date_created") or rule.get("createdAt")),
        tags=sorted({"sentry", "alert", "issue-alert", project_slug or "", environment} - {""})[:10],
        credibility=0.68,
        metadata={
            "signal_role": "problem",
            "sentry_project_slug": project_slug,
            "sentry_alert_rule_id": rule.get("id"),
            "rule_id": rule.get("id"),
            "name": name,
            "action_match": action_match or None,
            "filter_match": filter_match or None,
            "frequency": frequency,
            "environment": environment or None,
            "actions": actions,
            "conditions": conditions,
            "filters": filters,
            "date_created": rule.get("dateCreated") or rule.get("date_created") or rule.get("createdAt"),
            "date_modified": rule.get("dateModified") or rule.get("date_modified") or rule.get("updatedAt"),
            "raw": rule,
        },
    )


def _content(
    *,
    name: str,
    action_match: str,
    filter_match: str,
    frequency: int,
    environment: str,
    action_count: int,
    condition_count: int,
    filter_count: int,
) -> str:
    parts = [f"Sentry issue alert {name}"]
    if action_match:
        parts.append(f"action match {action_match}")
    if filter_match:
        parts.append(f"filter match {filter_match}")
    if frequency:
        parts.append(f"frequency {frequency} minutes")
    if environment:
        parts.append(f"environment {environment}")
    if action_count:
        parts.append(f"{action_count} actions")
    if condition_count:
        parts.append(f"{condition_count} conditions")
    if filter_count:
        parts.append(f"{filter_count} filters")
    return "; ".join(parts)


def _alert_url(rule: dict[str, Any], *, project_slug: str | None) -> str:
    for key in ("url", "permalink"):
        value = _text(rule.get(key))
        if value:
            return value
    rule_id = _text(rule.get("id"))
    if not rule_id or not project_slug:
        return ""
    return f"https://sentry.io/alerts/rules/{project_slug}/{rule_id}/details/"


def _next_cursor(response: httpx.Response) -> str | None:
    next_link = response.links.get("next") if response.links else None
    if not next_link:
        return None
    if _text(next_link.get("results")).lower() == "false":
        return None
    cursor = _optional(next_link.get("cursor"))
    if cursor:
        return cursor
    next_url = _optional(next_link.get("url"))
    if not next_url:
        return None
    return _optional(str(httpx.URL(next_url).params.get("cursor")))


def _list_of_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _positive_int(value: object, *, default: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number <= 0:
        return default
    return min(number, maximum)


def _int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
