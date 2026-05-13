"""HubSpot owners import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
HUBSPOT_API = "https://api.hubapi.com"


class HubSpotOwnersAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        access_token: str | None = None,
        private_app_token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            token
            or access_token
            or private_app_token
            or _optional(self._config.get("token"))
            or _optional(self._config.get("access_token"))
            or _optional(self._config.get("private_app_token"))
            or os.getenv("HUBSPOT_ACCESS_TOKEN")
            or os.getenv("HUBSPOT_PRIVATE_APP_TOKEN")
        )
        self.api_url = (
            api_url or _optional(self._config.get("api_url")) or os.getenv("HUBSPOT_API_URL") or HUBSPOT_API
        ).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "hubspot_owners_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size"), default=100, maximum=500)

    @property
    def archived(self) -> bool:
        return _bool(self._config.get("archived"), default=False)

    @property
    def email(self) -> str | None:
        return _optional(self._config.get("email"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            owners = await self._fetch_owners(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        for owner in owners:
            signal = _owner_signal(owner, adapter_name=self.name, seen=seen)
            if signal:
                signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_owners(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        owners: list[dict[str, Any]] = []
        after: str | None = None
        while len(owners) < limit:
            page_size = min(self.page_size, limit - len(owners))
            body = await self._get(client, limit=page_size, after=after)
            results = body.get("results") if isinstance(body, dict) else []
            if not isinstance(results, list) or not results:
                break

            for item in results:
                if not isinstance(item, dict) or not self._matches_email(item):
                    continue
                owners.append(item)
                if len(owners) >= limit:
                    break

            next_after = _next_after(body)
            if not next_after:
                break
            after = next_after
        return owners[:limit]

    async def _get(
        self,
        client: httpx.AsyncClient,
        *,
        limit: int,
        after: str | None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "limit": limit,
            "archived": str(self.archived).lower(),
        }
        if after:
            params["after"] = after
        try:
            response = await client.get(
                f"{self.api_url}/crm/v3/owners",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-hubspot-owners-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("HubSpot owners fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}

    def _matches_email(self, owner: dict[str, Any]) -> bool:
        email = self.email
        if not email:
            return True
        return _text(owner.get("email")).casefold() == email.casefold()


HubSpotOwnerAdapter = HubSpotOwnersAdapter


def _owner_signal(owner: dict[str, Any], *, adapter_name: str, seen: set[str]) -> Signal | None:
    owner_id = _optional(owner.get("id"))
    if not owner_id:
        return None
    signal_id = f"hubspot-owner:{owner_id}"
    if signal_id in seen:
        return None
    seen.add(signal_id)

    email = _text(owner.get("email"))
    first_name = _text(owner.get("firstName") or owner.get("first_name"))
    last_name = _text(owner.get("lastName") or owner.get("last_name"))
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    user_id = _optional(owner.get("userId") or owner.get("user_id"))
    teams = _teams(owner.get("teams"))
    team_summaries = [_team_summary(team) for team in teams]
    archived = owner.get("archived") if isinstance(owner.get("archived"), bool) else False
    created_at = owner.get("createdAt") or owner.get("created_at")
    updated_at = owner.get("updatedAt") or owner.get("updated_at")
    archived_at = owner.get("archivedAt") or owner.get("archived_at")

    return Signal(
        id=signal_id,
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=f"HubSpot owner {full_name or email or owner_id}",
        content=_content(full_name=full_name, email=email, user_id=user_id, team_summaries=team_summaries),
        url=_owner_url(owner, owner_id=owner_id),
        author=email or full_name or None,
        published_at=_parse_dt(created_at),
        tags=sorted({"hubspot", "owner", "archived" if archived else "active", *team_summaries} - {""})[:10],
        credibility=0.68,
        metadata={
            "signal_role": "market",
            "hubspot_owner_id": owner_id,
            "owner_id": owner_id,
            "user_id": user_id,
            "email": email or None,
            "first_name": first_name or None,
            "last_name": last_name or None,
            "name": full_name or None,
            "teams": teams,
            "team_summaries": team_summaries,
            "archived": archived,
            "created_at": created_at,
            "updated_at": updated_at,
            "archived_at": archived_at,
            "raw": owner,
        },
    )


def _content(
    *,
    full_name: str,
    email: str,
    user_id: str | None,
    team_summaries: list[str],
) -> str:
    parts = ["HubSpot owner"]
    if full_name:
        parts.append(full_name)
    if email:
        parts.append(email)
    if user_id:
        parts.append(f"user {user_id}")
    if team_summaries:
        parts.append(f"teams {', '.join(team_summaries)}")
    return "; ".join(parts)


def _teams(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _team_summary(team: dict[str, Any]) -> str:
    return _text(team.get("name") or team.get("id") or team.get("teamId") or team.get("team_id"))


def _owner_url(owner: dict[str, Any], *, owner_id: str) -> str:
    if _text(owner.get("url")):
        return _text(owner.get("url"))
    return f"https://app.hubspot.com/settings/users/{owner_id}" if owner_id else ""


def _next_after(body: dict[str, Any]) -> str | None:
    paging = body.get("paging") if isinstance(body.get("paging"), dict) else {}
    next_page = paging.get("next") if isinstance(paging.get("next"), dict) else {}
    return _optional(next_page.get("after"))


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


def _bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return default


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
