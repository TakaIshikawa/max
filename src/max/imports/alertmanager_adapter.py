"""Prometheus Alertmanager alert import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class AlertmanagerAdapter(SourceAdapter):
    """Fetch Alertmanager alerts and convert them to Max signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        base_url: str | None = None,
        bearer_token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.base_url = (base_url or _optional(self._config.get("base_url")) or os.getenv("ALERTMANAGER_BASE_URL") or "").rstrip("/")
        self.bearer_token = bearer_token if bearer_token is not None else os.getenv("ALERTMANAGER_BEARER_TOKEN")
        self._client = client

    @property
    def name(self) -> str:
        return "alertmanager_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def receivers(self) -> list[str]:
        return _strings(self._config.get("receivers") or self._config.get("receiver"))

    @property
    def label_filters(self) -> list[str]:
        filters = self._config.get("label_filters") or self._config.get("filters")
        if isinstance(filters, dict):
            return [f'{key}="{value}"' for key, value in sorted(filters.items()) if _text(key) and _text(value)]
        return _strings(filters)

    @property
    def include_silenced(self) -> bool:
        return bool(self._config.get("include_silenced", False))

    @property
    def timeout(self) -> float:
        value = self._config.get("timeout", 30)
        try:
            return float(value)
        except (TypeError, ValueError):
            return 30.0

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.base_url:
            return []
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        try:
            alerts = await self._get_alerts(client)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            fingerprint = _text(alert.get("fingerprint")) or _fingerprint_fallback(alert)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            signals.append(_alert_signal(alert, self.name))
            if len(signals) >= limit:
                break
        return signals

    async def _get_alerts(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        params: list[tuple[str, str]] = [
            ("active", "true"),
            ("silenced", "true" if self.include_silenced else "false"),
            ("inhibited", "true"),
        ]
        for receiver in self.receivers:
            params.append(("receiver", receiver))
        for label_filter in self.label_filters:
            params.append(("filter", label_filter))
        headers = {"Authorization": f"Bearer {self.bearer_token}"} if self.bearer_token else None
        try:
            response = await client.get(f"{self.base_url}/api/v2/alerts", headers=headers, params=params)
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Alertmanager alert fetch failed", exc_info=True)
            return []
        return body if isinstance(body, list) else []


PrometheusAlertmanagerAdapter = AlertmanagerAdapter


def _alert_signal(alert: dict[str, Any], adapter_name: str) -> Signal:
    labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
    annotations = alert.get("annotations") if isinstance(alert.get("annotations"), dict) else {}
    status = alert.get("status") if isinstance(alert.get("status"), dict) else {}
    receivers = _receivers(alert.get("receivers"))
    silences = _strings(status.get("silencedBy"))
    title = _text(annotations.get("summary")) or _text(labels.get("alertname")) or _label_summary(labels)
    content = _text(annotations.get("description")) or _text(annotations.get("summary")) or _label_summary(labels)
    severity = _text(labels.get("severity"))
    return Signal(
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=title,
        content=content[:1000],
        url=_text(alert.get("generatorURL")),
        author=None,
        published_at=_parse_dt(alert.get("startsAt")),
        tags=sorted({"alertmanager", severity, _text(status.get("state")), *receivers} - {""})[:10],
        credibility=0.8,
        metadata={
            "alertmanager_fingerprint": alert.get("fingerprint"),
            "fingerprint": alert.get("fingerprint"),
            "severity": severity or None,
            "status": status,
            "state": status.get("state"),
            "receivers": receivers,
            "generator_url": alert.get("generatorURL"),
            "starts_at": alert.get("startsAt"),
            "ends_at": alert.get("endsAt"),
            "labels": labels,
            "annotations": annotations,
            "silence_ids": silences,
            "inhibited_by": _strings(status.get("inhibitedBy")),
        },
    )


def _receivers(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    receivers: list[str] = []
    for item in value:
        if isinstance(item, dict):
            name = _text(item.get("name"))
            if name:
                receivers.append(name)
        elif _text(item):
            receivers.append(_text(item))
    return receivers


def _label_summary(labels: dict[str, Any]) -> str:
    alertname = _text(labels.get("alertname"))
    if alertname:
        return alertname
    return ", ".join(f"{key}={value}" for key, value in sorted(labels.items()) if _text(value))


def _fingerprint_fallback(alert: dict[str, Any]) -> str:
    labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
    starts_at = _text(alert.get("startsAt"))
    return "|".join([_label_summary(labels), starts_at])


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


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
