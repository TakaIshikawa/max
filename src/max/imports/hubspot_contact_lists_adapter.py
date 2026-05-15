"""HubSpot contact lists import adapter."""

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
CONTACT_OBJECT_TYPE_ID = "0-1"


class HubSpotContactListsAdapter(SourceAdapter):
    """Fetch HubSpot contact list definitions and convert them to Max signals."""

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
        return "hubspot_contact_lists_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("limit"), default=100, maximum=250)

    @property
    def archived(self) -> bool:
        return _bool(self._config.get("archived"), default=False)

    @property
    def query(self) -> str | None:
        return _optional(self._config.get("query"))

    @property
    def processing_types(self) -> list[str]:
        return _strings(self._config.get("processing_types") or self._config.get("processing_type"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            lists = await self._fetch_lists(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        for contact_list in lists:
            signal = _list_signal(contact_list, adapter_name=self.name, seen=seen)
            if signal:
                signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_lists(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        lists: list[dict[str, Any]] = []
        after: str | None = None
        while len(lists) < limit:
            page_size = min(self.page_size, limit - len(lists))
            body = await self._post_search(client, limit=page_size, after=after)
            results = body.get("lists") or body.get("results")
            if not isinstance(results, list) or not results:
                break

            for item in results:
                if not isinstance(item, dict) or _text(item.get("objectTypeId")) != CONTACT_OBJECT_TYPE_ID:
                    continue
                lists.append(item)
                if len(lists) >= limit:
                    break

            next_after = _next_after(body)
            if not next_after:
                break
            after = next_after
        return lists[:limit]

    async def _post_search(
        self,
        client: httpx.AsyncClient,
        *,
        limit: int,
        after: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "objectTypeId": CONTACT_OBJECT_TYPE_ID,
            "limit": limit,
        }
        if after:
            payload["after"] = after
        if self.query:
            payload["query"] = self.query
        if self.processing_types:
            payload["processingTypes"] = self.processing_types

        try:
            response = await client.post(
                f"{self.api_url}/crm/v3/lists/search",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": "max-hubspot-contact-lists-import/1",
                },
                params={
                    "includeFilters": "true",
                    "archived": str(self.archived).lower(),
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("HubSpot contact lists fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


HubSpotContactListAdapter = HubSpotContactListsAdapter


def _list_signal(contact_list: dict[str, Any], *, adapter_name: str, seen: set[str]) -> Signal | None:
    list_id = _optional(contact_list.get("listId") or contact_list.get("id"))
    if not list_id:
        return None
    signal_id = f"hubspot-contact-list:{list_id}"
    if signal_id in seen:
        return None
    seen.add(signal_id)

    name = _text(contact_list.get("name"))
    processing_type = _text(contact_list.get("processingType") or contact_list.get("processing_type"))
    object_type = _text(contact_list.get("objectTypeId") or contact_list.get("object_type_id"))
    size = contact_list.get("size", contact_list.get("count"))
    archived = _bool_or_none(contact_list.get("archived"))
    if archived is None:
        archived = contact_list.get("deletedAt") is not None
    created_at = contact_list.get("createdAt") or contact_list.get("created_at")
    updated_at = contact_list.get("updatedAt") or contact_list.get("updated_at")
    filters = contact_list.get("filterBranch") or contact_list.get("filters")

    return Signal(
        id=signal_id,
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=f"HubSpot contact list {name or list_id}",
        content=_content(name=name, processing_type=processing_type, object_type=object_type, size=size, archived=archived),
        url=_list_url(contact_list, list_id=list_id),
        author=None,
        published_at=_parse_dt(created_at),
        tags=sorted({"hubspot", "contact-list", processing_type.lower(), "archived" if archived else "active"} - {""})[:10],
        credibility=0.66,
        metadata={
            "signal_role": "market",
            "list_id": list_id,
            "name": name or None,
            "processing_type": processing_type or None,
            "object_type": object_type or None,
            "object_type_id": object_type or None,
            "size": size,
            "count": contact_list.get("count", size),
            "created_at": created_at,
            "updated_at": updated_at,
            "archived": archived,
            "filters": filters,
            "filter_branch": contact_list.get("filterBranch"),
            "processing_status": contact_list.get("processingStatus"),
            "raw": contact_list,
        },
    )


def _content(*, name: str, processing_type: str, object_type: str, size: object, archived: bool | None) -> str:
    parts = ["HubSpot contact list"]
    if name:
        parts.append(name)
    if processing_type:
        parts.append(processing_type)
    if object_type:
        parts.append(f"object {object_type}")
    if size is not None:
        parts.append(f"size {size}")
    if archived is not None:
        parts.append(f"archived {archived}")
    return "; ".join(parts)


def _list_url(contact_list: dict[str, Any], *, list_id: str) -> str:
    return _text(contact_list.get("url") or contact_list.get("listUrl") or contact_list.get("webUrl")) or (
        f"https://app.hubspot.com/lists/{list_id}" if list_id else ""
    )


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


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
