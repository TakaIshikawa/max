"""GitHub secret scanning alerts import adapter."""

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


class GitHubSecretScanningAlertsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
        repository: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = token if token is not None else (_optional(self._config.get("token")) or os.getenv("GITHUB_TOKEN"))
        self.api_url = (api_url or _optional(self._config.get("api_url")) or GITHUB_API).rstrip("/")
        configured_repository = repository or _optional(self._config.get("repository")) or _optional(self._config.get("repo_full_name"))
        repo_owner, repo_name = _split_repository(configured_repository)
        self.owner = owner or _optional(self._config.get("owner")) or repo_owner
        self.repo = repo or _optional(self._config.get("repo")) or repo_name
        self._client = client

    @property
    def name(self) -> str:
        return "github_secret_scanning_alerts_import"

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
                f"{self.api_url}/repos/{self.owner}/{self.repo}/secret-scanning/alerts",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "max-github-secret-scanning-alerts-import/1",
                },
                params=self._params(page=page, page_size=page_size),
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("GitHub secret scanning alerts fetch failed", exc_info=True)
            return []
        return [item for item in body if isinstance(item, dict)] if isinstance(body, list) else []

    def _params(self, *, page: int, page_size: int) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "per_page": page_size}
        for key in ("state", "secret_type", "resolution", "before", "after", "validity"):
            value = _optional(self._config.get(key))
            if value:
                params[key] = value
        return params


GitHubSecretScanningAlertAdapter = GitHubSecretScanningAlertsAdapter


def _alert_signal(alert: dict[str, Any], repository: str, adapter_name: str) -> Signal:
    number = _text(alert.get("number"))
    secret_type = _text(alert.get("secret_type"))
    state = _text(alert.get("state"))
    resolution = _text(alert.get("resolution"))
    validity = _text(alert.get("validity"))
    location = _location_metadata(alert)
    title_suffix = secret_type or "secret"
    content_bits = [f"{state.title() or 'GitHub'} secret scanning alert {number}"]
    if resolution:
        content_bits.append(f"resolution {resolution}")
    if validity:
        content_bits.append(f"validity {validity}")
    if location.get("path"):
        content_bits.append(f"location {location['path']}")

    return Signal(
        id=f"github-secret-scanning:{repository}:{number}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{repository} secret scanning alert {number}: {title_suffix}".strip(": "),
        content="; ".join(content_bits)[:1000],
        url=_text(alert.get("html_url")),
        author=None,
        published_at=_parse_dt(alert.get("created_at")),
        tags=sorted({"github", "secret-scanning", state, secret_type, resolution, validity} - {""})[:10],
        credibility=0.78,
        metadata={
            "repository": repository,
            "alert_number": alert.get("number"),
            "secret_type": alert.get("secret_type"),
            "secret_type_display_name": alert.get("secret_type_display_name"),
            "state": alert.get("state"),
            "resolution": alert.get("resolution"),
            "validity": alert.get("validity"),
            "html_url": alert.get("html_url"),
            "created_at": alert.get("created_at"),
            "updated_at": alert.get("updated_at"),
            "resolved_at": alert.get("resolved_at"),
            "resolution_comment": alert.get("resolution_comment"),
            "locations_url": alert.get("locations_url"),
            "location": location,
            "raw": alert,
        },
    )


def _location_metadata(alert: dict[str, Any]) -> dict[str, Any]:
    location = alert.get("location") if isinstance(alert.get("location"), dict) else {}
    details = location.get("details") if isinstance(location.get("details"), dict) else {}
    return {
        "type": location.get("type"),
        "path": details.get("path") or alert.get("path"),
        "start_line": details.get("start_line") or alert.get("start_line"),
        "end_line": details.get("end_line") or alert.get("end_line"),
        "start_column": details.get("start_column"),
        "end_column": details.get("end_column"),
        "blob_sha": details.get("blob_sha"),
        "commit_sha": details.get("commit_sha") or alert.get("commit_sha"),
    }


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
