"""HubSpot calls import adapter."""

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
DEFAULT_CALL_PROPERTIES = [
    "hs_call_title",
    "hs_call_body",
    "hs_timestamp",
    "hubspot_owner_id",
    "hs_call_direction",
    "hs_call_status",
    "hs_call_duration",
    "createdate",
    "hs_lastmodifieddate",
]


class HubSpotCallsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            token
            if token is not None
            else (
                _optional(self._config.get("token"))
                or os.getenv("HUBSPOT_ACCESS_TOKEN")
                or os.getenv("HUBSPOT_TOKEN")
            )
        )
        self.api_url = (
            api_url
            or _optional(self._config.get("api_url"))
            or os.getenv("HUBSPOT_API_URL")
            or HUBSPOT_API
        ).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "hubspot_calls_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def properties(self) -> list[str]:
        return _strings(self._config.get("properties")) or DEFAULT_CALL_PROPERTIES

    @property
    def associations(self) -> list[str]:
        return _strings(self._config.get("associations") or self._config.get("association_types"))

    @property
    def archived(self) -> bool | None:
        value = self._config.get("archived")
        if isinstance(value, bool):
            return value
        text = _text(value).lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
        return None

    @property
    def after(self) -> str | None:
        return _optional(self._config.get("after"))

    @property
    def page_size(self) -> int:
        return _positive_int(
            self._config.get("page_size") or self._config.get("per_page") or self._config.get("limit"),
            default=100,
            maximum=100,
        )

    @property
    def updated_after(self) -> datetime | None:
        return _parse_dt(
            self._config.get("updated_after")
            or self._config.get("since")
            or self._config.get("modified_after")
            or self._config.get("created_after")
        )

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            calls = await self._fetch_calls(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        for call in calls:
            if not isinstance(call, dict):
                continue
            signal = _call_signal(call, self.name)
            if self.updated_after and _before(_updated_at(signal), self.updated_after):
                continue
            signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_calls(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []
        after = self.after
        while len(calls) < limit:
            page_size = min(self.page_size, limit - len(calls))
            body = await self._get(client, limit=page_size, after=after)
            results = body.get("results") if isinstance(body, dict) else []
            if not isinstance(results, list) or not results:
                break
            calls.extend(item for item in results if isinstance(item, dict))
            next_after = _next_after(body)
            if not next_after:
                break
            after = next_after
        return calls[:limit]

    async def _get(
        self,
        client: httpx.AsyncClient,
        *,
        limit: int,
        after: str | None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "properties": self.properties}
        if after:
            params["after"] = after
        if self.archived is not None:
            params["archived"] = str(self.archived).lower()
        if self.associations:
            params["associations"] = self.associations
        try:
            response = await client.get(
                f"{self.api_url}/crm/v3/objects/calls",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-hubspot-calls-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("HubSpot calls fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


HubSpotCallAdapter = HubSpotCallsAdapter


def _call_signal(call: dict[str, Any], adapter_name: str) -> Signal:
    props = call.get("properties") if isinstance(call.get("properties"), dict) else {}
    call_id = _text(call.get("id"))
    title = _text(props.get("hs_call_title")) or f"HubSpot call {call_id}"
    body = _text(props.get("hs_call_body"))
    direction = _text(props.get("hs_call_direction"))
    status = _text(props.get("hs_call_status"))
    duration = _int(props.get("hs_call_duration"))
    owner = _text(props.get("hubspot_owner_id"))
    created_at = props.get("createdate") or call.get("createdAt") or props.get("hs_timestamp")
    updated_at = props.get("hs_lastmodifieddate") or call.get("updatedAt")
    timestamp = props.get("hs_timestamp") or created_at
    associations = call.get("associations") if isinstance(call.get("associations"), dict) else {}
    return Signal(
        id=f"hubspot-call:{call_id}" if call_id else "",
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=title,
        content=body or _content(direction=direction, status=status, duration=duration),
        url=_call_url(call),
        author=owner or None,
        published_at=_parse_dt(timestamp),
        tags=sorted({"hubspot", "call", direction.lower(), status.lower()} - {""})[:10],
        credibility=0.68,
        metadata={
            "signal_role": "market",
            "hubspot_call_id": call.get("id"),
            "call_id": call.get("id"),
            "title": title,
            "body": body or None,
            "timestamp": timestamp,
            "owner_id": owner or None,
            "direction": direction or None,
            "status": status or None,
            "duration": duration,
            "created_at": created_at,
            "updated_at": updated_at,
            "archived": call.get("archived"),
            "associations": associations,
            "properties": props,
            "raw": call,
        },
    )


def _content(*, direction: str, status: str, duration: int) -> str:
    parts = ["HubSpot call"]
    if direction:
        parts.append(direction.lower())
    if status:
        parts.append(status.lower())
    if duration:
        parts.append(f"{duration} ms")
    return "; ".join(parts)


def _call_url(call: dict[str, Any]) -> str:
    if _text(call.get("url")):
        return _text(call.get("url"))
    call_id = _text(call.get("id"))
    return f"https://app.hubspot.com/contacts/call/{call_id}" if call_id else ""


def _next_after(body: dict[str, Any]) -> str | None:
    paging = body.get("paging") if isinstance(body.get("paging"), dict) else {}
    next_page = paging.get("next") if isinstance(paging.get("next"), dict) else {}
    return _optional(next_page.get("after"))


def _updated_at(signal: Signal) -> datetime | None:
    value = signal.metadata.get("updated_at") or signal.metadata.get("created_at") or signal.metadata.get("timestamp")
    return _parse_dt(value)


def _before(value: datetime | None, threshold: datetime) -> bool:
    if value is None:
        return False
    compare = value
    target = threshold
    if compare.tzinfo is None and target.tzinfo is not None:
        compare = compare.replace(tzinfo=target.tzinfo)
    if target.tzinfo is None and compare.tzinfo is not None:
        target = target.replace(tzinfo=compare.tzinfo)
    return compare < target


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


def _strings(value: object) -> list[str]:
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        value = [item.strip() for item in str(value).split(",")]
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
