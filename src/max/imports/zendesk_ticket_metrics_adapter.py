"""Zendesk ticket metrics import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class ZendeskTicketMetricsImportAdapter(SourceAdapter):
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
        return "zendesk_ticket_metrics_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def ticket_ids(self) -> list[str]:
        return _strings(self._config.get("ticket_ids") or self._config.get("ticket_id"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=100, maximum=100)

    @property
    def breached_only(self) -> bool:
        return bool(self._config.get("breached_only"))

    @property
    def updated_since(self) -> str | None:
        return _optional(self._config.get("updated_since"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.base_url and self.email and self.token):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            metrics = await self._fetch_ticket_metrics(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        updated_since = _parse_dt(self.updated_since)
        for metric in metrics:
            if not isinstance(metric, dict):
                continue
            if updated_since and (metric_updated := _parse_dt(metric.get("updated_at"))) and metric_updated < updated_since:
                continue
            if self.breached_only and not _has_breach(metric):
                continue
            signal = _metric_signal(metric, self.name, self.base_url, seen)
            if signal:
                signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_ticket_metrics(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        if self.ticket_ids:
            metrics: list[dict[str, Any]] = []
            for ticket_id in self.ticket_ids:
                if len(metrics) >= limit:
                    break
                body = await self._get(
                    client,
                    url=f"{self.base_url}/api/v2/tickets/{ticket_id}/metrics.json",
                    params=None,
                )
                metric = body.get("ticket_metric") or body.get("ticket_metrics")
                if isinstance(metric, dict):
                    metrics.append(metric)
                elif isinstance(metric, list):
                    metrics.extend(item for item in metric if isinstance(item, dict))
            return metrics[:limit]

        metrics = []
        url = f"{self.base_url}/api/v2/ticket_metrics.json"
        params: dict[str, Any] | None = {"per_page": min(self.page_size, limit)}
        if self.updated_since:
            params["updated_since"] = self.updated_since
        while url and len(metrics) < limit:
            body = await self._get(client, url=url, params=params)
            page = body.get("ticket_metrics") if isinstance(body.get("ticket_metrics"), list) else []
            metrics.extend(item for item in page if isinstance(item, dict))
            url = _optional(body.get("next_page")) or _optional(((body.get("links") or {}) if isinstance(body.get("links"), dict) else {}).get("next"))
            params = None
            if not page:
                break
        return metrics[:limit]

    async def _get(
        self,
        client: httpx.AsyncClient,
        *,
        url: str,
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        try:
            response = await client.get(url, auth=(f"{self.email}/token", self.token or ""), params=params)
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Zendesk ticket metrics fetch failed for %s", url, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


ZendeskTicketMetricsAdapter = ZendeskTicketMetricsImportAdapter


def _metric_signal(
    metric: dict[str, Any],
    adapter_name: str,
    base_url: str,
    seen: set[str],
) -> Signal | None:
    ticket_id = _optional(metric.get("ticket_id"))
    metric_set_id = _optional(metric.get("id") or metric.get("metric_set_id"))
    signal_id = f"zendesk-ticket-metric:{ticket_id or 'unknown'}:{metric_set_id or 'latest'}"
    if signal_id in seen:
        return None
    seen.add(signal_id)

    timings = {
        "reply_time": _duration(metric.get("reply_time_in_minutes") or metric.get("reply_time_in_seconds")),
        "first_resolution_time": _duration(metric.get("first_resolution_time_in_minutes") or metric.get("first_resolution_time_in_seconds")),
        "full_resolution_time": _duration(metric.get("full_resolution_time_in_minutes") or metric.get("full_resolution_time_in_seconds")),
        "requester_wait_time": _duration(metric.get("requester_wait_time_in_minutes") or metric.get("requester_wait_time_in_seconds")),
        "agent_wait_time": _duration(metric.get("agent_wait_time_in_minutes") or metric.get("agent_wait_time_in_seconds")),
        "on_hold_time": _duration(metric.get("on_hold_time_in_minutes") or metric.get("on_hold_time_in_seconds")),
    }
    breach_flags = _breach_flags(metric)
    breached = any(breach_flags.values())
    ticket_label = ticket_id or "unknown ticket"
    content_bits = [
        f"reply {timings['reply_time'].get('calendar')}",
        f"full resolution {timings['full_resolution_time'].get('calendar')}",
        f"requester wait {timings['requester_wait_time'].get('calendar')}",
    ]

    return Signal(
        id=signal_id,
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"Zendesk ticket {ticket_label} SLA metrics",
        content=", ".join(bit for bit in content_bits if not bit.endswith(" None"))[:1000],
        url=f"{base_url}/agent/tickets/{ticket_id}" if ticket_id else base_url,
        author=None,
        published_at=_parse_dt(metric.get("created_at")),
        tags=sorted({"zendesk", "ticket-metrics", "sla-breach" if breached else "sla-ok"} - {""})[:10],
        credibility=0.7,
        metadata={
            "ticket_id": metric.get("ticket_id"),
            "metric_set_id": metric.get("id") or metric.get("metric_set_id"),
            "reply_time": timings["reply_time"],
            "first_resolution_time": timings["first_resolution_time"],
            "full_resolution_time": timings["full_resolution_time"],
            "requester_wait_time": timings["requester_wait_time"],
            "agent_wait_time": timings["agent_wait_time"],
            "on_hold_time": timings["on_hold_time"],
            "reply_time_in_minutes": metric.get("reply_time_in_minutes"),
            "first_resolution_time_in_minutes": metric.get("first_resolution_time_in_minutes"),
            "full_resolution_time_in_minutes": metric.get("full_resolution_time_in_minutes"),
            "requester_wait_time_in_minutes": metric.get("requester_wait_time_in_minutes"),
            "agent_wait_time_in_minutes": metric.get("agent_wait_time_in_minutes"),
            "on_hold_time_in_minutes": metric.get("on_hold_time_in_minutes"),
            "breached": breached,
            "breach_flags": breach_flags,
            "reopens": metric.get("reopens"),
            "replies": metric.get("replies"),
            "created_at": metric.get("created_at"),
            "updated_at": metric.get("updated_at"),
            "raw": metric,
        },
    )


def _duration(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            key: value.get(key)
            for key in ("calendar", "business")
            if value.get(key) is not None
        }
    if value is None:
        return {}
    return {"calendar": value}


def _has_breach(metric: dict[str, Any]) -> bool:
    return any(_breach_flags(metric).values())


def _breach_flags(metric: dict[str, Any]) -> dict[str, bool]:
    flags: dict[str, bool] = {}
    for key, value in metric.items():
        if "breach" not in str(key).lower():
            continue
        if isinstance(value, bool):
            flags[str(key)] = value
        elif isinstance(value, dict):
            flags.update({f"{key}.{nested_key}": bool(nested_value) for nested_key, nested_value in value.items() if "breach" in str(nested_key).lower()})
    for metric_key in (
        "reply_time_in_minutes",
        "first_resolution_time_in_minutes",
        "full_resolution_time_in_minutes",
        "requester_wait_time_in_minutes",
        "agent_wait_time_in_minutes",
        "on_hold_time_in_minutes",
    ):
        value = metric.get(metric_key)
        if isinstance(value, dict) and "breached" in value:
            flags[f"{metric_key}.breached"] = bool(value.get("breached"))
    return flags


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


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
