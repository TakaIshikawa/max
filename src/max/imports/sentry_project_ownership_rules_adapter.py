"""Sentry project ownership rules import adapter."""

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


class SentryProjectOwnershipRulesAdapter(SourceAdapter):
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
        return "sentry_project_ownership_rules_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def organization_slug(self) -> str | None:
        return _optional(self._config.get("organization_slug") or self._config.get("org"))

    @property
    def project_slugs(self) -> list[str]:
        return _strings(
            self._config.get("project_slugs")
            or self._config.get("projects")
            or self._config.get("project_slug")
            or self._config.get("project")
        )

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.organization_slug or not self.project_slugs:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for project_slug in self.project_slugs:
                if len(signals) >= limit:
                    break
                ownership = await self._fetch_project_ownership(client, project_slug=project_slug)
                if ownership:
                    signals.append(
                        _ownership_signal(
                            ownership,
                            organization_slug=self.organization_slug,
                            project_slug=project_slug,
                            adapter_name=self.name,
                        )
                    )
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_project_ownership(
        self,
        client: httpx.AsyncClient,
        *,
        project_slug: str,
    ) -> dict[str, Any]:
        url = f"{self.api_url}/projects/{self.organization_slug}/{project_slug}/ownership/"
        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-sentry-project-ownership-rules-import/1",
                },
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Sentry project ownership rules fetch failed for project %s", project_slug, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


SentryProjectOwnershipRuleAdapter = SentryProjectOwnershipRulesAdapter


def _ownership_signal(
    ownership: dict[str, Any],
    *,
    organization_slug: str | None,
    project_slug: str,
    adapter_name: str,
) -> Signal:
    raw_ownership = _text(
        ownership.get("raw")
        or ownership.get("rawOwnership")
        or ownership.get("raw_ownership")
        or ownership.get("text")
    )
    rule_rows = _rule_rows(raw_ownership)
    fallthrough = _bool_or_none(
        ownership.get("fallthrough")
        if "fallthrough" in ownership
        else ownership.get("fallThrough")
        if "fallThrough" in ownership
        else ownership.get("autoAssignment")
    )
    date_updated = ownership.get("dateUpdated") or ownership.get("date_updated") or ownership.get("updatedAt")
    return Signal(
        id=f"sentry-ownership-rules:{organization_slug}:{project_slug}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{project_slug} Sentry ownership rules",
        content=_content(project_slug=project_slug, rule_count=len(rule_rows), fallthrough=fallthrough),
        url=_text(ownership.get("url") or ownership.get("permalink")),
        author=None,
        published_at=_parse_dt(date_updated),
        tags=sorted({"sentry", "ownership", "ownership-rules", organization_slug or "", project_slug} - {""})[:10],
        credibility=0.68,
        metadata={
            "signal_role": "ownership",
            "sentry_organization_slug": organization_slug,
            "sentry_project_slug": project_slug,
            "raw_ownership": raw_ownership,
            "rule_rows": rule_rows,
            "fallthrough": fallthrough,
            "date_updated": date_updated,
            "raw": ownership,
        },
    )


def _content(*, project_slug: str, rule_count: int, fallthrough: bool | None) -> str:
    parts = [f"Sentry ownership rules for {project_slug}"]
    if rule_count:
        parts.append(f"{rule_count} parsed rules")
    if fallthrough is not None:
        parts.append(f"fallthrough {fallthrough}")
    return "; ".join(parts)


def _rule_rows(raw_ownership: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw_ownership.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tokens = stripped.split()
        owners = [token for token in tokens if token.startswith("@")]
        matchers = [token for token in tokens if not token.startswith("@")]
        rows.append(
            {
                "line_number": line_number,
                "raw": stripped,
                "matchers": matchers,
                "owners": owners,
            }
        )
    return rows


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        value = [value]
    if not isinstance(value, list):
        return []
    strings: list[str] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, bool):
            continue
        text = _text(item)
        if text and text not in seen:
            seen.add(text)
            strings.append(text)
    return strings


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
