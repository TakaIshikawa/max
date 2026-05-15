"""Zendesk ticket macros import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class ZendeskTicketMacrosImportAdapter(SourceAdapter):
    """Fetch Zendesk ticket macros and convert them to Max signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        base_url: str | None = None,
        email: str | None = None,
        token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        configured_base = base_url or _optional(self._config.get("base_url")) or os.getenv("ZENDESK_BASE_URL")
        subdomain = _optional(self._config.get("subdomain")) or os.getenv("ZENDESK_SUBDOMAIN")
        self.base_url = (configured_base or (f"https://{subdomain}.zendesk.com" if subdomain else "")).rstrip("/")
        self.email = email if email is not None else (_optional(self._config.get("email")) or os.getenv("ZENDESK_EMAIL"))
        self.token = token if token is not None else (_optional(self._config.get("token")) or _optional(self._config.get("api_token")) or os.getenv("ZENDESK_API_TOKEN"))
        self._client = client

    @property
    def name(self) -> str:
        return "zendesk_ticket_macros_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=100, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.base_url and self.email and self.token):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            macros = await self._fetch_macros(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        for macro in macros:
            signal = _macro_signal(macro, self.name, seen)
            if signal:
                signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_macros(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        macros: list[dict[str, Any]] = []
        url: str | None = f"{self.base_url}/api/v2/macros.json"
        params: dict[str, Any] | None = {"per_page": min(self.page_size, limit)}

        while url and len(macros) < limit:
            body = await self._get(client, url=url, params=params)
            page = body.get("macros") if isinstance(body.get("macros"), list) else []
            macros.extend(item for item in page if isinstance(item, dict))
            links = body.get("links") if isinstance(body.get("links"), dict) else {}
            meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
            url = _optional(body.get("next_page")) or _optional(links.get("next"))
            if not url and meta.get("has_more") and _optional(meta.get("after_cursor")):
                url = f"{self.base_url}/api/v2/macros.json"
                params = {"per_page": min(self.page_size, limit - len(macros)), "page[after]": meta["after_cursor"]}
            else:
                params = None
            if not page:
                break
        return macros[:limit]

    async def _get(self, client: httpx.AsyncClient, *, url: str, params: dict[str, Any] | None) -> dict[str, Any]:
        try:
            response = await client.get(
                url,
                auth=(f"{self.email}/token", self.token or ""),
                headers={"Accept": "application/json", "User-Agent": "max-zendesk-ticket-macros-import/1"},
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Zendesk ticket macros fetch failed for %s", url, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


ZendeskTicketMacrosAdapter = ZendeskTicketMacrosImportAdapter


def _macro_signal(macro: dict[str, Any], adapter_name: str, seen: set[str]) -> Signal | None:
    macro_id = _optional(macro.get("id"))
    if not macro_id:
        return None
    signal_id = f"zendesk-ticket-macro:{macro_id}"
    if signal_id in seen:
        return None
    seen.add(signal_id)

    title = _text(macro.get("title"))
    active = _bool_or_none(macro.get("active"))
    restriction = macro.get("restriction") if isinstance(macro.get("restriction"), dict) else None
    actions = _actions(macro.get("actions"))
    created_at = macro.get("created_at")
    updated_at = macro.get("updated_at")

    return Signal(
        id=signal_id,
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=title or f"Zendesk ticket macro {macro_id}",
        content=_content(title=title, active=active, restriction=restriction, actions=actions, position=macro.get("position")),
        url=_text(macro.get("url")),
        author=None,
        published_at=_parse_dt(updated_at) or _parse_dt(created_at),
        tags=sorted({"zendesk", "ticket-macro", "active" if active else "inactive", "restricted" if restriction else ""} - {""})[:10],
        credibility=0.66,
        metadata={
            "signal_role": "support_workflow",
            "macro_id": macro.get("id"),
            "title": title or None,
            "active": active,
            "restriction": restriction,
            "actions": macro.get("actions") if isinstance(macro.get("actions"), list) else [],
            "action_summaries": actions,
            "position": macro.get("position"),
            "created_at": created_at,
            "updated_at": updated_at,
            "url": macro.get("url"),
            "raw": macro,
        },
    )


def _actions(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    summaries: list[str] = []
    for action in value:
        if not isinstance(action, dict):
            continue
        field = _text(action.get("field") or action.get("field_name"))
        val = action.get("value")
        summaries.append(f"{field}: {val}" if field else _text(val))
    return [summary for summary in summaries if summary]


def _content(*, title: str, active: bool | None, restriction: dict[str, Any] | None, actions: list[str], position: object) -> str:
    parts = ["Zendesk ticket macro"]
    if title:
        parts.append(title)
    if active is not None:
        parts.append(f"active {active}")
    if restriction:
        parts.append(f"restricted {_restriction_summary(restriction)}")
    if position is not None:
        parts.append(f"position {position}")
    if actions:
        parts.append("actions " + "; ".join(actions))
    return "; ".join(parts)


def _restriction_summary(restriction: dict[str, Any]) -> str:
    kind = _text(restriction.get("type"))
    ids = restriction.get("ids")
    if isinstance(ids, list) and ids:
        return f"{kind} {', '.join(_text(item) for item in ids)}".strip()
    return kind or "true"


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
