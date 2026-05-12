"""PagerDuty incident alerts import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
DEFAULT_PAGERDUTY_API_URL = "https://api.pagerduty.com"


class PagerDutyIncidentAlertsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        api_token: str | None = None,
        api_url: str = DEFAULT_PAGERDUTY_API_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.api_token = api_token if api_token is not None else (
            _optional(self._config.get("api_token")) or os.getenv("PAGERDUTY_API_TOKEN")
        )
        self.api_url = (_optional(self._config.get("api_url")) or api_url).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "pagerduty_incident_alerts_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def incident_ids(self) -> list[str]:
        return _strings(self._config.get("incident_ids") or self._config.get("incident_id"))

    @property
    def statuses(self) -> list[str]:
        return _strings(self._config.get("statuses") or self._config.get("status"))

    @property
    def services(self) -> list[str]:
        return _strings(self._config.get("services") or self._config.get("service_ids") or self._config.get("service_id"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size"), default=100, maximum=100)

    @property
    def limit_per_incident(self) -> int | None:
        value = self._config.get("limit_per_incident")
        if value is None:
            return None
        return _positive_int(value, default=0, maximum=10_000) or None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.api_token and self.incident_ids):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            rows: list[tuple[str, dict[str, Any]]] = []
            for incident_id in self.incident_ids:
                if len(rows) >= limit:
                    break
                incident_limit = min(limit - len(rows), self.limit_per_incident or limit)
                rows.extend(
                    (incident_id, alert)
                    for alert in await self._fetch_alerts(
                        client,
                        incident_id=incident_id,
                        limit=incident_limit,
                    )
                )
            return [_alert_signal(incident_id, alert, self.name) for incident_id, alert in rows[:limit]]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_alerts(
        self,
        client: httpx.AsyncClient,
        *,
        incident_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        offset = 0
        while len(alerts) < limit:
            page_limit = min(self.page_size, limit - len(alerts))
            body = await self._get(
                client,
                f"/incidents/{incident_id}/alerts",
                params={**self._filter_params(), "limit": page_limit, "offset": offset},
            )
            page = body.get("alerts") if isinstance(body.get("alerts"), list) else []
            if not page:
                break
            alerts.extend(item for item in page if isinstance(item, dict))
            if not bool(body.get("more")):
                break
            offset = _next_offset(body, offset, page_limit)
        return alerts[:limit]

    async def _get(
        self,
        client: httpx.AsyncClient,
        path: str,
        *,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            response = await client.get(
                f"{self.api_url}{path}",
                params=params,
                headers={
                    "Accept": "application/vnd.pagerduty+json;version=2",
                    "Authorization": f"Token token={self.api_token}",
                    "User-Agent": "max-pagerduty-incident-alerts-import/1",
                },
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("PagerDuty incident alerts fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}

    def _filter_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if self.statuses:
            params["statuses[]"] = self.statuses
        if self.services:
            params["service_ids[]"] = self.services
        return params


PagerDutyIncidentAlertAdapter = PagerDutyIncidentAlertsAdapter


def _alert_signal(incident_id: str, alert: dict[str, Any], adapter_name: str) -> Signal:
    alert_id = _text(alert.get("id")) or _text(alert.get("alert_key")) or _text(alert.get("created_at"))
    service = alert.get("service") if isinstance(alert.get("service"), dict) else {}
    incident = alert.get("incident") if isinstance(alert.get("incident"), dict) else {}
    status = _text(alert.get("status"))
    summary = _text(alert.get("summary") or alert.get("description")) or f"PagerDuty alert {alert_id}"
    return Signal(
        id=f"pagerduty-alert:{incident_id}:{alert_id}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=summary,
        content=_content(alert, summary)[:1000],
        url=_text(alert.get("html_url") or incident.get("html_url")),
        author=None,
        published_at=_parse_dt(alert.get("created_at")),
        tags=sorted({"pagerduty", "incident", "alert", status.lower()} - {""})[:10],
        credibility=0.7,
        metadata={
            "pagerduty_alert_id": alert.get("id"),
            "pagerduty_incident_id": incident_id,
            "alert_key": alert.get("alert_key"),
            "status": alert.get("status"),
            "severity": alert.get("severity"),
            "service": _entity_summary(service),
            "incident": _entity_summary(incident) or {"id": incident_id},
            "created_at": alert.get("created_at"),
            "updated_at": alert.get("updated_at"),
            "body": alert.get("body"),
            "raw": alert,
        },
    )


def _content(alert: dict[str, Any], summary: str) -> str:
    body = alert.get("body") if isinstance(alert.get("body"), dict) else {}
    details = body.get("details") if isinstance(body.get("details"), dict) else {}
    detail_text = _optional(details.get("message") or details.get("description") or details.get("error"))
    return f"{summary}. {detail_text}" if detail_text else summary


def _entity_summary(value: dict[str, Any]) -> dict[str, Any]:
    if not value:
        return {}
    return {
        "id": value.get("id"),
        "summary": value.get("summary"),
        "type": value.get("type"),
        "self": value.get("self"),
        "html_url": value.get("html_url"),
    }


def _next_offset(body: dict[str, Any], offset: int, limit: int) -> int:
    try:
        return int(body.get("offset", offset)) + int(body.get("limit", limit))
    except (TypeError, ValueError):
        return offset + limit


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
        value = [item.strip() for item in value.split(",") if item.strip()]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
