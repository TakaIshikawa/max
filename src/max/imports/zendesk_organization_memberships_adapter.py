"""Zendesk organization memberships import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class ZendeskOrganizationMembershipsImportAdapter(SourceAdapter):
    """Fetch Zendesk organization memberships and convert them to Max signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        base_url: str | None = None,
        email: str | None = None,
        token: str | None = None,
        access_token: str | None = None,
        bearer_token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        configured_base = base_url or _optional(self._config.get("base_url")) or os.getenv("ZENDESK_BASE_URL")
        subdomain = _optional(self._config.get("subdomain")) or os.getenv("ZENDESK_SUBDOMAIN")
        self.base_url = (configured_base or (f"https://{subdomain}.zendesk.com" if subdomain else "")).rstrip("/")
        self.email = email if email is not None else (_optional(self._config.get("email")) or os.getenv("ZENDESK_EMAIL"))
        self.token = (
            token
            if token is not None
            else (
                _optional(self._config.get("token"))
                or _optional(self._config.get("api_token"))
                or os.getenv("ZENDESK_API_TOKEN")
            )
        )
        self.bearer_token = (
            access_token
            or bearer_token
            or _optional(self._config.get("access_token"))
            or _optional(self._config.get("bearer_token"))
            or os.getenv("ZENDESK_ACCESS_TOKEN")
            or os.getenv("ZENDESK_BEARER_TOKEN")
        )
        self._client = client

    @property
    def name(self) -> str:
        return "zendesk_organization_memberships_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def user_id(self) -> str | None:
        return _optional(self._config.get("user_id"))

    @property
    def organization_id(self) -> str | None:
        return _optional(self._config.get("organization_id"))

    @property
    def next_page(self) -> str | None:
        return _optional(self._config.get("next_page"))

    @property
    def page_size(self) -> int:
        return _positive_int(
            self._config.get("page_size") or self._config.get("per_page"),
            default=100,
            maximum=100,
        )

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.base_url or not self._has_auth:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            memberships = await self._fetch_memberships(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        for membership in memberships:
            signal = _membership_signal(membership, adapter_name=self.name, seen=seen)
            if signal:
                signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    @property
    def _has_auth(self) -> bool:
        return bool((self.email and self.token) or self.bearer_token or self.token)

    async def _fetch_memberships(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        memberships: list[dict[str, Any]] = []
        url: str | None = self.next_page or f"{self.base_url}/api/v2/organization_memberships.json"
        params: dict[str, Any] | None = self._initial_params(limit=limit) if not self.next_page else None

        while url and len(memberships) < limit:
            body = await self._get(client, url=url, params=params)
            page = body.get("organization_memberships")
            if not isinstance(page, list) or not page:
                break
            memberships.extend(item for item in page if isinstance(item, dict))
            url = _optional(body.get("next_page")) or _optional(((body.get("links") or {}) if isinstance(body.get("links"), dict) else {}).get("next"))
            params = None
        return memberships[:limit]

    def _initial_params(self, *, limit: int) -> dict[str, Any]:
        params: dict[str, Any] = {"per_page": min(self.page_size, limit)}
        if self.user_id:
            params["user_id"] = self.user_id
        if self.organization_id:
            params["organization_id"] = self.organization_id
        return params

    async def _get(
        self,
        client: httpx.AsyncClient,
        *,
        url: str,
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "max-zendesk-organization-memberships-import/1",
        }
        auth: tuple[str, str] | None = None
        if self.email and self.token:
            auth = (f"{self.email}/token", self.token)
        else:
            headers["Authorization"] = f"Bearer {self.bearer_token or self.token}"

        try:
            response = await client.get(url, auth=auth, headers=headers, params=params)
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Zendesk organization memberships fetch failed for %s", url, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


ZendeskOrganizationMembershipsAdapter = ZendeskOrganizationMembershipsImportAdapter


def _membership_signal(
    membership: dict[str, Any],
    *,
    adapter_name: str,
    seen: set[str],
) -> Signal | None:
    membership_id = _optional(membership.get("id"))
    if not membership_id:
        return None
    signal_id = f"zendesk-organization-membership:{membership_id}"
    if signal_id in seen:
        return None
    seen.add(signal_id)

    user_id = membership.get("user_id")
    organization_id = membership.get("organization_id")
    default = _bool_or_none(membership.get("default"))
    created_at = membership.get("created_at")
    updated_at = membership.get("updated_at")
    tags = [_text(tag) for tag in membership.get("tags", []) if _text(tag)] if isinstance(membership.get("tags"), list) else []

    return Signal(
        id=signal_id,
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=f"Zendesk organization membership {membership_id}",
        content=_content(user_id=user_id, organization_id=organization_id, default=default),
        url=_text(membership.get("url")),
        author=_text(user_id) or None,
        published_at=_parse_dt(created_at),
        tags=sorted({"zendesk", "organization-membership", "default" if default else "", *tags} - {""})[:10],
        credibility=0.66,
        metadata={
            "signal_role": "market",
            "membership_id": membership.get("id"),
            "user_id": user_id,
            "organization_id": organization_id,
            "default": default,
            "created_at": created_at,
            "updated_at": updated_at,
            "tags": tags,
            "raw": membership,
        },
    )


def _content(*, user_id: object, organization_id: object, default: bool | None) -> str:
    parts = ["Zendesk organization membership"]
    if user_id is not None:
        parts.append(f"user {user_id}")
    if organization_id is not None:
        parts.append(f"organization {organization_id}")
    if default is not None:
        parts.append(f"default {default}")
    return "; ".join(parts)


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


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
