"""HubSpot companies import adapter."""

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
DEFAULT_COMPANY_PROPERTIES = [
    "name",
    "domain",
    "industry",
    "lifecyclestage",
    "type",
    "city",
    "state",
    "country",
    "hubspot_owner_id",
    "createdate",
    "hs_lastmodifieddate",
]


class HubSpotCompaniesAdapter(SourceAdapter):
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
        return "hubspot_companies_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def properties(self) -> list[str]:
        return _strings(self._config.get("properties")) or DEFAULT_COMPANY_PROPERTIES

    @property
    def archived(self) -> bool | None:
        return _bool(self._config.get("archived"))

    @property
    def after(self) -> str | None:
        return _optional(self._config.get("after"))

    @property
    def page_limit(self) -> int:
        return _positive_int(
            self._config.get("limit") or self._config.get("per_page") or self._config.get("page_size"),
            default=100,
            maximum=100,
        )

    @property
    def updated_after(self) -> str | None:
        return _optional(self._config.get("updated_after"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            companies = await (
                self._fetch_search(client, limit=limit)
                if self.updated_after
                else self._fetch_list(client, limit=limit)
            )
        finally:
            if close_client:
                await client.aclose()

        return [
            _company_signal(company, self.name)
            for company in companies[:limit]
            if isinstance(company, dict)
        ]

    async def _fetch_list(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        companies: list[dict[str, Any]] = []
        after = self.after
        while len(companies) < limit:
            page_size = min(self.page_limit, limit - len(companies))
            body = await self._get_companies(client, limit=page_size, after=after)
            results = body.get("results") if isinstance(body, dict) else []
            if not isinstance(results, list) or not results:
                break
            companies.extend(item for item in results if isinstance(item, dict))
            next_after = _next_after(body)
            if not next_after:
                break
            after = next_after
        return companies[:limit]

    async def _fetch_search(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        companies: list[dict[str, Any]] = []
        after = self.after
        while len(companies) < limit:
            page_size = min(self.page_limit, limit - len(companies))
            body = await self._post_search(client, limit=page_size, after=after)
            results = body.get("results") if isinstance(body, dict) else []
            if not isinstance(results, list) or not results:
                break
            companies.extend(item for item in results if isinstance(item, dict))
            next_after = _next_after(body)
            if not next_after:
                break
            after = next_after
        return companies[:limit]

    async def _get_companies(
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
                f"{self.api_url}/crm/v3/objects/companies",
                headers=self._headers,
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("HubSpot companies fetch failed", exc_info=True)
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
                f"{self.api_url}/crm/v3/objects/companies/search",
                headers={**self._headers, "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("HubSpot companies search failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "max-hubspot-companies-import/1",
        }


HubSpotCompanyAdapter = HubSpotCompaniesAdapter


def _company_signal(company: dict[str, Any], adapter_name: str) -> Signal:
    props = company.get("properties") if isinstance(company.get("properties"), dict) else {}
    company_id = _text(company.get("id")) or _text(props.get("hs_object_id"))
    name = _text(props.get("name"))
    domain = _text(props.get("domain"))
    title = name or domain or f"HubSpot company {company_id}"
    industry = _text(props.get("industry"))
    lifecycle = _text(props.get("lifecyclestage"))
    company_type = _text(props.get("type"))
    owner = _text(props.get("hubspot_owner_id"))
    created_at = props.get("createdate") or company.get("createdAt")
    updated_at = props.get("hs_lastmodifieddate") or company.get("updatedAt")
    return Signal(
        id=f"hubspot-company:{company_id}" if company_id else "",
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=title,
        content=_content(
            title=title,
            domain=domain,
            industry=industry,
            lifecycle=lifecycle,
            company_type=company_type,
        ),
        url=_company_url(company, company_id=company_id, domain=domain),
        author=owner or None,
        published_at=_parse_dt(created_at),
        tags=sorted({"hubspot", "company", industry, lifecycle, company_type} - {""})[:10],
        credibility=0.68,
        metadata={
            "signal_role": "market",
            "hubspot_company_id": company_id,
            "company_id": company_id,
            "name": name or None,
            "domain": domain or None,
            "industry": industry or None,
            "lifecycle_stage": lifecycle or None,
            "type": company_type or None,
            "city": _optional(props.get("city")),
            "state": _optional(props.get("state")),
            "country": _optional(props.get("country")),
            "owner_id": owner or None,
            "created_at": created_at,
            "updated_at": updated_at,
            "archived": company.get("archived"),
            "properties": props,
            "raw": company,
        },
    )


def _content(*, title: str, domain: str, industry: str, lifecycle: str, company_type: str) -> str:
    parts = [f"HubSpot company {title}"]
    if domain:
        parts.append(domain)
    if industry:
        parts.append(f"industry {industry}")
    if lifecycle:
        parts.append(f"lifecycle {lifecycle}")
    if company_type:
        parts.append(f"type {company_type}")
    return "; ".join(parts)


def _company_url(company: dict[str, Any], *, company_id: str, domain: str) -> str:
    url = _text(company.get("url") or company.get("web_url"))
    if url:
        return url
    if company_id:
        return f"https://app.hubspot.com/contacts/company/{company_id}"
    return f"https://{domain}" if domain else ""


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
