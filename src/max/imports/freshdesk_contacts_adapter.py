"""Freshdesk contacts import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class FreshdeskContactsImportAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        domain: str | None = None,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        configured_domain = domain or _optional(self._config.get("domain")) or os.getenv("FRESHDESK_DOMAIN")
        self.domain = _freshdesk_domain(configured_domain)
        self.api_key = (
            api_key
            if api_key is not None
            else (_optional(self._config.get("api_key")) or os.getenv("FRESHDESK_API_KEY"))
        )
        self._client = client

    @property
    def name(self) -> str:
        return "freshdesk_contacts_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def base_url(self) -> str:
        return f"https://{self.domain}" if self.domain else ""

    @property
    def updated_since(self) -> str | None:
        return _optional(self._config.get("updated_since"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.domain and self.api_key):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            contacts = await self._fetch_contacts(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        for contact in contacts:
            signal = _contact_signal(contact, adapter_name=self.name, base_url=self.base_url, seen=seen)
            if signal:
                signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_contacts(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        contacts: list[dict[str, Any]] = []
        url: str | None = f"{self.base_url}/api/v2/contacts"
        params: dict[str, Any] | None = {
            "page": 1,
            "per_page": min(self.page_size, limit),
        }
        if self.updated_since:
            params["updated_since"] = self.updated_since

        while url and len(contacts) < limit:
            response = await self._get(client, url=url, params=params)
            if response is None:
                break
            body = response.json()
            page = body if isinstance(body, list) else body.get("contacts", [])
            values = [item for item in page if isinstance(item, dict)] if isinstance(page, list) else []
            contacts.extend(values)

            next_url = _response_next_url(response)
            if next_url:
                url = next_url
                params = None
            elif values and params and len(values) >= int(params["per_page"]):
                params = {**params, "page": int(params["page"]) + 1}
            else:
                break
        return contacts[:limit]

    async def _get(
        self,
        client: httpx.AsyncClient,
        *,
        url: str,
        params: dict[str, Any] | None,
    ) -> httpx.Response | None:
        try:
            response = await client.get(
                url,
                auth=httpx.BasicAuth(self.api_key or "", "X"),
                headers={"Accept": "application/json"},
                params=params,
            )
            response.raise_for_status()
        except Exception:
            logger.warning("Freshdesk contacts fetch failed for %s", url, exc_info=True)
            return None
        return response


FreshdeskContactsAdapter = FreshdeskContactsImportAdapter


def _contact_signal(
    contact: dict[str, Any],
    *,
    adapter_name: str,
    base_url: str,
    seen: set[str],
) -> Signal | None:
    contact_id = _optional(contact.get("id"))
    if not contact_id:
        return None
    external_id = f"freshdesk-contact:{contact_id}"
    if external_id in seen:
        return None
    seen.add(external_id)

    name = _text(contact.get("name"))
    email = _text(contact.get("email"))
    phone = _text(contact.get("phone")) or _text(contact.get("mobile"))
    company_id = _optional(contact.get("company_id"))
    tags = _strings(contact.get("tags"))
    active = _bool_or_none(contact.get("active"))
    deleted = _bool_or_none(contact.get("deleted"))

    return Signal(
        id=external_id,
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=name or email or f"Freshdesk contact {contact_id}",
        content=_content(name=name, email=email, phone=phone, company_id=company_id, active=active, deleted=deleted),
        url=f"{base_url}/a/contacts/{contact_id}",
        author=email or None,
        published_at=_parse_dt(contact.get("created_at")),
        tags=sorted({"freshdesk", "contact", *tags, "active" if active is True else "", "deleted" if deleted is True else ""} - {""})[:10],
        credibility=0.65,
        metadata={
            "contact_id": contact.get("id"),
            "name": name or None,
            "email": email or None,
            "phone": phone or None,
            "company_id": contact.get("company_id"),
            "active": active,
            "deleted": deleted,
            "tags": tags,
            "created_at": contact.get("created_at"),
            "updated_at": contact.get("updated_at"),
            "raw": contact,
        },
    )


def _content(
    *,
    name: str,
    email: str,
    phone: str,
    company_id: str | None,
    active: bool | None,
    deleted: bool | None,
) -> str:
    parts = ["Freshdesk contact"]
    if name:
        parts.append(name)
    if email:
        parts.append(email)
    if phone:
        parts.append(f"phone {phone}")
    if company_id:
        parts.append(f"company {company_id}")
    if active is not None:
        parts.append(f"active {active}")
    if deleted is not None:
        parts.append(f"deleted {deleted}")
    return "; ".join(parts)


def _response_next_url(response: httpx.Response) -> str | None:
    next_link = response.links.get("next")
    if isinstance(next_link, dict):
        return _optional(next_link.get("url"))
    links_header = response.headers.get("Link", "")
    for part in links_header.split(","):
        if 'rel="next"' not in part and "rel=next" not in part:
            continue
        start = part.find("<")
        end = part.find(">", start + 1)
        if start >= 0 and end > start:
            return _optional(part[start + 1 : end])
    return None


def _freshdesk_domain(value: object) -> str:
    domain = _text(value).removeprefix("https://").removeprefix("http://").strip("/")
    if not domain:
        return ""
    if "." not in domain:
        return f"{domain}.freshdesk.com"
    return domain


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


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
