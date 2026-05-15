"""Freshdesk agents import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class FreshdeskAgentsImportAdapter(SourceAdapter):
    """Fetch Freshdesk agents and convert them to Max signals."""

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
        return "freshdesk_agents_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def base_url(self) -> str:
        return f"https://{self.domain}" if self.domain else ""

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.domain and self.api_key):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            agents = await self._fetch_agents(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        for agent in agents:
            signal = _agent_signal(agent, adapter_name=self.name, base_url=self.base_url, seen=seen)
            if signal:
                signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_agents(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        agents: list[dict[str, Any]] = []
        url: str | None = f"{self.base_url}/api/v2/agents"
        params: dict[str, Any] | None = {"page": 1, "per_page": min(self.page_size, limit)}

        while url and len(agents) < limit:
            response = await self._get(client, url=url, params=params)
            if response is None:
                break
            body = response.json()
            page = body if isinstance(body, list) else body.get("agents", [])
            values = [item for item in page if isinstance(item, dict)] if isinstance(page, list) else []
            agents.extend(values)

            next_url = _response_next_url(response)
            if next_url:
                url = next_url
                params = None
            elif values and params and len(values) >= int(params["per_page"]):
                params = {**params, "page": int(params["page"]) + 1}
            else:
                break
        return agents[:limit]

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
                headers={"Accept": "application/json", "User-Agent": "max-freshdesk-agents-import/1"},
                params=params,
            )
            response.raise_for_status()
        except Exception:
            logger.warning("Freshdesk agents fetch failed for %s", url, exc_info=True)
            return None
        return response


FreshdeskAgentsAdapter = FreshdeskAgentsImportAdapter


def _agent_signal(
    agent: dict[str, Any],
    *,
    adapter_name: str,
    base_url: str,
    seen: set[str],
) -> Signal | None:
    agent_id = _optional(agent.get("id"))
    if not agent_id:
        return None
    signal_id = f"freshdesk-agent:{agent_id}"
    if signal_id in seen:
        return None
    seen.add(signal_id)

    contact = agent.get("contact") if isinstance(agent.get("contact"), dict) else {}
    name = _text(contact.get("name") or agent.get("name"))
    email = _text(contact.get("email") or agent.get("email"))
    active = _bool_or_none(agent.get("active"))
    available = _bool_or_none(agent.get("available"))
    ticket_scope = _text(agent.get("ticket_scope"))
    group_ids = _list(agent.get("group_ids"))
    role_ids = _list(agent.get("role_ids"))
    created_at = agent.get("created_at")
    updated_at = agent.get("updated_at")

    return Signal(
        id=signal_id,
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=name or email or f"Freshdesk agent {agent_id}",
        content=_content(name=name, email=email, active=active, available=available, ticket_scope=ticket_scope),
        url=f"{base_url}/a/admin/agents/{agent_id}" if base_url else "",
        author=email or name or None,
        published_at=_parse_dt(created_at),
        tags=sorted({"freshdesk", "agent", ticket_scope, "active" if active is True else "", "available" if available is True else ""} - {""})[:10],
        credibility=0.66,
        metadata={
            "signal_role": "stakeholder",
            "agent_id": agent.get("id"),
            "contact_id": contact.get("id") or agent.get("contact_id"),
            "name": name or None,
            "email": email or None,
            "active": active,
            "available": available,
            "ticket_scope": agent.get("ticket_scope"),
            "group_ids": group_ids,
            "role_ids": role_ids,
            "created_at": created_at,
            "updated_at": updated_at,
            "raw": agent,
        },
    )


def _content(*, name: str, email: str, active: bool | None, available: bool | None, ticket_scope: str) -> str:
    parts = ["Freshdesk agent"]
    if name:
        parts.append(name)
    if email:
        parts.append(email)
    if active is not None:
        parts.append(f"active {active}")
    if available is not None:
        parts.append(f"available {available}")
    if ticket_scope:
        parts.append(f"ticket scope {ticket_scope}")
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


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
