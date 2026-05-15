"""Zendesk ticket forms import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class ZendeskTicketFormsImportAdapter(SourceAdapter):
    """Fetch Zendesk ticket forms and convert them to Max signals."""

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
        return "zendesk_ticket_forms_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=100, maximum=100)

    @property
    def active(self) -> bool | None:
        if "active" not in self._config:
            return None
        return _bool(self._config.get("active"), default=False)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.base_url and self.email and self.token):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            forms = await self._fetch_ticket_forms(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        for form in forms:
            if not isinstance(form, dict):
                continue
            if self.active is not None and _bool_or_none(form.get("active")) is not self.active:
                continue
            signal = _form_signal(form, self.name, seen)
            if signal:
                signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_ticket_forms(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        forms: list[dict[str, Any]] = []
        url: str | None = f"{self.base_url}/api/v2/ticket_forms.json"
        params: dict[str, Any] | None = {"per_page": min(self.page_size, limit)}
        if self.active is not None:
            params["active"] = str(self.active).lower()

        while url and len(forms) < limit:
            body = await self._get(client, url=url, params=params)
            page = body.get("ticket_forms") if isinstance(body.get("ticket_forms"), list) else []
            forms.extend(item for item in page if isinstance(item, dict))
            url = _optional(body.get("next_page")) or _optional(((body.get("links") or {}) if isinstance(body.get("links"), dict) else {}).get("next"))
            params = None
            if not page:
                break
        return forms[:limit]

    async def _get(
        self,
        client: httpx.AsyncClient,
        *,
        url: str,
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        try:
            response = await client.get(
                url,
                auth=(f"{self.email}/token", self.token or ""),
                headers={"Accept": "application/json", "User-Agent": "max-zendesk-ticket-forms-import/1"},
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Zendesk ticket forms fetch failed for %s", url, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


ZendeskTicketFormsAdapter = ZendeskTicketFormsImportAdapter


def _form_signal(form: dict[str, Any], adapter_name: str, seen: set[str]) -> Signal | None:
    form_id = _optional(form.get("id"))
    if not form_id:
        return None
    signal_id = f"zendesk-ticket-form:{form_id}"
    if signal_id in seen:
        return None
    seen.add(signal_id)

    name = _text(form.get("name"))
    display_name = _text(form.get("display_name"))
    active = _bool_or_none(form.get("active"))
    default = _bool_or_none(form.get("default"))
    end_user_visible = _bool_or_none(form.get("end_user_visible"))
    ticket_field_ids = _list(form.get("ticket_field_ids"))
    created_at = form.get("created_at")
    updated_at = form.get("updated_at")

    return Signal(
        id=signal_id,
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=name or display_name or f"Zendesk ticket form {form_id}",
        content=_content(name=name, display_name=display_name, active=active, default=default, visible=end_user_visible),
        url=_text(form.get("url")),
        author=None,
        published_at=_parse_dt(created_at),
        tags=sorted({"zendesk", "ticket-form", "active" if active else "inactive", "default" if default else ""} - {""})[:10],
        credibility=0.66,
        metadata={
            "signal_role": "support_workflow",
            "form_id": form.get("id"),
            "name": name or None,
            "display_name": display_name or None,
            "active": active,
            "default": default,
            "end_user_visible": end_user_visible,
            "ticket_field_ids": ticket_field_ids,
            "created_at": created_at,
            "updated_at": updated_at,
            "url": form.get("url"),
            "raw": form,
        },
    )


def _content(*, name: str, display_name: str, active: bool | None, default: bool | None, visible: bool | None) -> str:
    parts = ["Zendesk ticket form"]
    if name:
        parts.append(name)
    if display_name and display_name != name:
        parts.append(display_name)
    if active is not None:
        parts.append(f"active {active}")
    if default is not None:
        parts.append(f"default {default}")
    if visible is not None:
        parts.append(f"end user visible {visible}")
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


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
