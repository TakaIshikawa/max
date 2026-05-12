"""GitHub code scanning alerts import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
GITHUB_API = "https://api.github.com"


class GitHubCodeScanningAlertsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = token if token is not None else (_optional(self._config.get("token")) or os.getenv("GITHUB_TOKEN"))
        self.api_url = (api_url or _optional(self._config.get("api_url")) or GITHUB_API).rstrip("/")
        repository = _optional(self._config.get("repository")) or _optional(self._config.get("repo_full_name"))
        repo_owner, repo_name = _split_repository(repository)
        self.owner = owner or _optional(self._config.get("owner")) or repo_owner
        self.repo = repo or _optional(self._config.get("repo")) or repo_name
        self._client = client

    @property
    def name(self) -> str:
        return "github_code_scanning_alerts_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.token and self.owner and self.repo):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            alerts: list[dict[str, Any]] = []
            page = 1
            while len(alerts) < limit:
                page_size = min(self.per_page, limit - len(alerts))
                page_alerts = await self._fetch_page(client, page=page, page_size=page_size)
                if not page_alerts:
                    break
                alerts.extend(page_alerts)
                if len(page_alerts) < page_size:
                    break
                page += 1
        finally:
            if close_client:
                await client.aclose()

        repository = f"{self.owner}/{self.repo}"
        return [_alert_signal(alert, repository, self.name) for alert in alerts[:limit] if isinstance(alert, dict)]

    async def _fetch_page(self, client: httpx.AsyncClient, *, page: int, page_size: int) -> list[dict[str, Any]]:
        try:
            response = await client.get(
                f"{self.api_url}/repos/{self.owner}/{self.repo}/code-scanning/alerts",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                },
                params=self._params(page=page, page_size=page_size),
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("GitHub code scanning alerts fetch failed", exc_info=True)
            return []
        return body if isinstance(body, list) else []

    def _params(self, *, page: int, page_size: int) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "per_page": page_size}
        for key in ("state", "branch", "severity"):
            value = _optional(self._config.get(key))
            if value:
                params[key] = value
        ref = _optional(self._config.get("ref"))
        if ref:
            params["ref"] = ref
        tool_name = _optional(self._config.get("tool_name"))
        if tool_name:
            params["tool_name"] = tool_name
        return params


GitHubCodeScanningAlertAdapter = GitHubCodeScanningAlertsAdapter


def _alert_signal(alert: dict[str, Any], repository: str, adapter_name: str) -> Signal:
    rule = alert.get("rule") if isinstance(alert.get("rule"), dict) else {}
    tool = alert.get("tool") if isinstance(alert.get("tool"), dict) else {}
    instance = alert.get("most_recent_instance") if isinstance(alert.get("most_recent_instance"), dict) else {}
    location = instance.get("location") if isinstance(instance.get("location"), dict) else {}
    message = instance.get("message") if isinstance(instance.get("message"), dict) else {}
    number = _text(alert.get("number"))
    rule_id = _text(rule.get("id") or rule.get("name"))
    severity = _text(rule.get("severity") or rule.get("security_severity_level"))
    state = _text(alert.get("state"))
    return Signal(
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{repository} code scanning alert {number}: {rule_id}".strip(": "),
        content=(_text(message.get("text")) or _text(rule.get("description") or rule.get("full_description")))[:1000],
        url=_text(alert.get("html_url")),
        author=None,
        published_at=_parse_dt(alert.get("created_at")),
        tags=sorted({"github", "code-scanning", state, severity, _text(tool.get("name"))} - {""})[:10],
        credibility=0.75,
        metadata={
            "alert_number": alert.get("number"),
            "repository": repository,
            "state": alert.get("state"),
            "rule_id": rule.get("id"),
            "rule_name": rule.get("name"),
            "severity": severity,
            "security_severity_level": rule.get("security_severity_level"),
            "tool_name": tool.get("name"),
            "created_at": alert.get("created_at"),
            "updated_at": alert.get("updated_at"),
            "fixed_at": alert.get("fixed_at"),
            "dismissed_at": alert.get("dismissed_at"),
            "dismissed_reason": alert.get("dismissed_reason"),
            "ref": instance.get("ref"),
            "analysis_key": instance.get("analysis_key"),
            "category": instance.get("category"),
            "location": {
                "path": location.get("path"),
                "start_line": location.get("start_line"),
                "end_line": location.get("end_line"),
            },
        },
    )


def _split_repository(value: str | None) -> tuple[str | None, str | None]:
    if not value or "/" not in value:
        return None, None
    owner, repo = value.split("/", 1)
    return (_optional(owner), _optional(repo))


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


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
