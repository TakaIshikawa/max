"""HubSpot contacts import adapter."""

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
DEFAULT_CONTACT_PROPERTIES = [
    "firstname",
    "lastname",
    "email",
    "company",
    "lifecyclestage",
    "hubspot_owner_id",
    "createdate",
    "hs_lastmodifieddate",
]


class HubSpotContactsAdapter(SourceAdapter):
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
        return "hubspot_contacts_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def properties(self) -> list[str]:
        return _strings(self._config.get("properties")) or DEFAULT_CONTACT_PROPERTIES

    @property
    def archived(self) -> bool | None:
        return _bool(self._config.get("archived"))

    @property
    def after(self) -> str | None:
        return _optional(self._config.get("after"))

    @property
    def page_limit(self) -> int:
        return _positive_int(self._config.get("limit") or self._config.get("per_page"), default=100, maximum=100)

    @property
    def updated_after(self) -> str | None:
        return _optional(self._config.get("updated_after"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            contacts = await self._fetch_search(client, limit=limit) if self.updated_after else await self._fetch_list(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        return [
            _contact_signal(contact, self.name)
            for contact in contacts[:limit]
            if isinstance(contact, dict)
        ]

    async def _fetch_list(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        contacts: list[dict[str, Any]] = []
        after = self.after
        while len(contacts) < limit:
            page_size = min(self.page_limit, limit - len(contacts))
            body = await self._get_contacts(client, limit=page_size, after=after)
            results = body.get("results") if isinstance(body, dict) else []
            if not isinstance(results, list) or not results:
                break
            contacts.extend(item for item in results if isinstance(item, dict))
            next_after = _next_after(body)
            if not next_after:
                break
            after = next_after
        return contacts[:limit]

    async def _fetch_search(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        contacts: list[dict[str, Any]] = []
        after = self.after
        while len(contacts) < limit:
            page_size = min(self.page_limit, limit - len(contacts))
            body = await self._post_search(client, limit=page_size, after=after)
            results = body.get("results") if isinstance(body, dict) else []
            if not isinstance(results, list) or not results:
                break
            contacts.extend(item for item in results if isinstance(item, dict))
            next_after = _next_after(body)
            if not next_after:
                break
            after = next_after
        return contacts[:limit]

    async def _get_contacts(
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
        try:
            response = await client.get(
                f"{self.api_url}/crm/v3/objects/contacts",
                headers=self._headers,
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("HubSpot contacts fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}

    async def _post_search(
        self,
        client: httpx.AsyncClient,
        *,
        limit: int,
        after: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "limit": limit,
            "properties": self.properties,
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "hs_lastmodifieddate",
                            "operator": "GTE",
                            "value": self.updated_after,
                        }
                    ]
                }
            ],
        }
        if after:
            payload["after"] = after
        if self.archived is not None:
            payload["archived"] = self.archived
        try:
            response = await client.post(
                f"{self.api_url}/crm/v3/objects/contacts/search",
                headers={**self._headers, "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("HubSpot contacts search failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "max-hubspot-contacts-import/1",
        }


HubSpotContactAdapter = HubSpotContactsAdapter


def _contact_signal(contact: dict[str, Any], adapter_name: str) -> Signal:
    props = contact.get("properties") if isinstance(contact.get("properties"), dict) else {}
    contact_id = _text(contact.get("id"))
    first_name = _text(props.get("firstname"))
    last_name = _text(props.get("lastname"))
    email = _text(props.get("email"))
    name = " ".join(part for part in (first_name, last_name) if part).strip()
    title = name or email or f"HubSpot contact {contact_id}"
    lifecycle = _text(props.get("lifecyclestage"))
    company = _text(props.get("company"))
    owner = _text(props.get("hubspot_owner_id"))
    created_at = props.get("createdate") or contact.get("createdAt")
    updated_at = props.get("hs_lastmodifieddate") or contact.get("updatedAt")
    return Signal(
        id=f"hubspot-contact:{contact_id}" if contact_id else "",
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=title,
        content=_content(title=title, email=email, company=company, lifecycle=lifecycle),
        url=_contact_url(contact, contact_id=contact_id),
        author=owner or None,
        published_at=_parse_dt(created_at),
        tags=sorted({"hubspot", "contact", lifecycle, company} - {""})[:10],
        credibility=0.68,
        metadata={
            "signal_role": "customer",
            "hubspot_contact_id": contact.get("id"),
            "contact_id": contact.get("id"),
            "name": name or None,
            "email": email or None,
            "lifecycle_stage": lifecycle or None,
            "company": company or None,
            "owner_id": owner or None,
            "created_at": created_at,
            "updated_at": updated_at,
            "archived": contact.get("archived"),
            "url": _contact_url(contact, contact_id=contact_id),
            "properties": props,
            "raw": contact,
        },
    )


def _content(*, title: str, email: str, company: str, lifecycle: str) -> str:
    parts = [f"HubSpot contact {title}"]
    if email and email != title:
        parts.append(email)
    if company:
        parts.append(f"company {company}")
    if lifecycle:
        parts.append(f"lifecycle {lifecycle}")
    return "; ".join(parts)


def _contact_url(contact: dict[str, Any], *, contact_id: str) -> str:
    url = _text(contact.get("url") or contact.get("web_url"))
    if url:
        return url
    return f"https://app.hubspot.com/contacts/contact/{contact_id}" if contact_id else ""


def _next_after(body: dict[str, Any]) -> str | None:
    paging = body.get("paging") if isinstance(body.get("paging"), dict) else {}
    next_page = paging.get("next") if isinstance(paging.get("next"), dict) else {}
    return _optional(next_page.get("after"))


def _bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


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


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",")]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
