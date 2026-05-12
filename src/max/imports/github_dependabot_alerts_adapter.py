"""GitHub Dependabot alerts import adapter."""

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


class GitHubDependabotAlertsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str = GITHUB_API,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = token if token is not None else (_optional(self._config.get("token")) or os.getenv("GITHUB_TOKEN"))
        self.api_url = api_url.rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "github_dependabot_alerts_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SECURITY.value

    @property
    def owner(self) -> str | None:
        return _optional(self._config.get("owner"))

    @property
    def repo(self) -> str | None:
        return _optional(self._config.get("repo")) or _optional(self._config.get("repository"))

    @property
    def state(self) -> str | None:
        return _optional(self._config.get("state"))

    @property
    def severity(self) -> str | None:
        return _optional(self._config.get("severity"))

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page"), default=100, maximum=100)

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
                body = await self._get(client, page=page, per_page=page_size)
                if not isinstance(body, list) or not body:
                    break
                alerts.extend([item for item in body if isinstance(item, dict)])
                if len(body) < page_size:
                    break
                page += 1
        finally:
            if close_client:
                await client.aclose()
        repository = f"{self.owner}/{self.repo}"
        return [_alert_signal(alert, repository, self.name) for alert in alerts[:limit]]

    async def _get(self, client: httpx.AsyncClient, *, page: int, per_page: int) -> object:
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        if self.state:
            params["state"] = self.state
        if self.severity:
            params["severity"] = self.severity
        try:
            response = await client.get(
                f"{self.api_url}/repos/{self.owner}/{self.repo}/dependabot/alerts",
                params=params,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "max-github-dependabot-alerts-import/1",
                },
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.warning("GitHub Dependabot alert fetch failed", exc_info=True)
            return []


GitHubDependabotAlertAdapter = GitHubDependabotAlertsAdapter


def _alert_signal(alert: dict[str, Any], repository: str, adapter_name: str) -> Signal:
    dependency = alert.get("dependency") if isinstance(alert.get("dependency"), dict) else {}
    package = dependency.get("package") if isinstance(dependency.get("package"), dict) else {}
    security_advisory = alert.get("security_advisory") if isinstance(alert.get("security_advisory"), dict) else {}
    security_vulnerability = alert.get("security_vulnerability") if isinstance(alert.get("security_vulnerability"), dict) else {}
    first_vulnerable = security_vulnerability.get("first_patched_version") if isinstance(security_vulnerability.get("first_patched_version"), dict) else {}
    advisory_id = _text(security_advisory.get("ghsa_id")) or _text(security_advisory.get("cve_id"))
    number = _text(alert.get("number"))
    severity = _text(security_advisory.get("severity")) or _text(security_vulnerability.get("severity"))
    package_name = _text(package.get("name"))
    return Signal(
        id=f"github-dependabot:{repository}:{number}",
        source_type=SignalSourceType.SECURITY,
        source_adapter=adapter_name,
        title=f"{severity.title() or 'Security'} Dependabot alert for {package_name or repository}",
        content=_text(security_advisory.get("summary"))[:1000],
        url=_text(alert.get("html_url")) or _text(security_advisory.get("permalink")),
        author=None,
        published_at=_parse_dt(alert.get("created_at")),
        tags=sorted({"github", "dependabot", severity, _text(alert.get("state")), _text(package.get("ecosystem"))} - {""})[:10],
        credibility=0.75,
        metadata={
            "github_dependabot_alert_number": alert.get("number"),
            "repository": repository,
            "state": alert.get("state"),
            "severity": severity,
            "package": package_name,
            "ecosystem": package.get("ecosystem"),
            "manifest_path": dependency.get("manifest_path"),
            "scope": dependency.get("scope"),
            "ghsa_id": security_advisory.get("ghsa_id"),
            "cve_id": security_advisory.get("cve_id"),
            "identifiers": security_advisory.get("identifiers"),
            "affected_range": security_vulnerability.get("vulnerable_version_range"),
            "fixed_version": first_vulnerable.get("identifier"),
            "dismissed_reason": alert.get("dismissed_reason"),
            "created_at": alert.get("created_at"),
            "updated_at": alert.get("updated_at"),
            "advisory_url": security_advisory.get("permalink"),
            "advisory_id": advisory_id,
            "raw": alert,
        },
    )


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _positive_int(value: object, *, default: int, maximum: int) -> int:
    return min(value, maximum) if isinstance(value, int) and not isinstance(value, bool) and value > 0 else default


def _optional(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
