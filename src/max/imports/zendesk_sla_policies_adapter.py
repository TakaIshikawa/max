"""Zendesk SLA policies import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class ZendeskSlaPoliciesImportAdapter(SourceAdapter):
    """Fetch Zendesk SLA policies and convert them to operational market signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        api_url: str | None = None,
        base_url: str | None = None,
        email: str | None = None,
        token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        configured_base = (
            api_url
            or base_url
            or _optional(self._config.get("api_url"))
            or _optional(self._config.get("base_url"))
            or os.getenv("ZENDESK_API_URL")
            or os.getenv("ZENDESK_BASE_URL")
        )
        subdomain = _optional(self._config.get("subdomain")) or os.getenv("ZENDESK_SUBDOMAIN")
        self.base_url = (configured_base or (f"https://{subdomain}.zendesk.com" if subdomain else "")).rstrip("/")
        self.email = email if email is not None else (_optional(self._config.get("email")) or os.getenv("ZENDESK_EMAIL"))
        self.token = token if token is not None else (_optional(self._config.get("token")) or _optional(self._config.get("api_token")) or os.getenv("ZENDESK_API_TOKEN"))
        self._client = client

    @property
    def name(self) -> str:
        return "zendesk_sla_policies_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=100, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.base_url and self.email and self.token):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            policies = await self._fetch_policies(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        for policy in policies:
            if not isinstance(policy, dict):
                continue
            signal = _policy_signal(policy, self.name, self.base_url, seen)
            if signal:
                signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_policies(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        policies: list[dict[str, Any]] = []
        url: str | None = f"{self.base_url}/api/v2/slas/policies.json"
        params: dict[str, Any] | None = {"per_page": min(self.page_size, limit)}

        while url and len(policies) < limit:
            body = await self._get(client, url=url, params=params)
            page = body.get("sla_policies") if isinstance(body.get("sla_policies"), list) else []
            policies.extend(item for item in page if isinstance(item, dict))
            links = body.get("links") if isinstance(body.get("links"), dict) else {}
            meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
            url = _optional(body.get("next_page")) or _optional(links.get("next"))
            if not url and meta.get("has_more") and _optional(meta.get("after_cursor")):
                url = f"{self.base_url}/api/v2/slas/policies.json"
                params = {"per_page": min(self.page_size, limit - len(policies)), "page[after]": meta["after_cursor"]}
            else:
                params = None
            if not page:
                break
        return policies[:limit]

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
                headers={"Accept": "application/json", "User-Agent": "max-zendesk-sla-policies-import/1"},
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Zendesk SLA policies fetch failed for %s", url, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


ZendeskSlaPoliciesAdapter = ZendeskSlaPoliciesImportAdapter


def _policy_signal(
    policy: dict[str, Any],
    adapter_name: str,
    base_url: str,
    seen: set[str],
) -> Signal | None:
    policy_id = _optional(policy.get("id"))
    if not policy_id:
        return None
    signal_id = f"zendesk-sla-policy:{policy_id}"
    if signal_id in seen:
        return None
    seen.add(signal_id)

    title = _text(policy.get("title") or policy.get("name")) or f"Zendesk SLA policy {policy_id}"
    active = _bool_or_none(policy.get("active"))
    position = policy.get("position")
    filter_summary = _filter_summary(policy.get("filter") or policy.get("conditions"))
    metrics = _metrics(policy.get("policy_metrics") or policy.get("metrics"))
    updated_at = policy.get("updated_at")
    created_at = policy.get("created_at")

    return Signal(
        id=signal_id,
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=title,
        content=_content(title=title, active=active, metrics=metrics, filter_summary=filter_summary, position=position),
        url=_policy_url(policy, base_url=base_url, policy_id=policy_id),
        author=None,
        published_at=_parse_dt(updated_at) or _parse_dt(created_at),
        tags=sorted({"zendesk", "sla-policy", "active" if active else "inactive"} - {""})[:10],
        credibility=0.68,
        metadata={
            "signal_role": "market",
            "policy_id": policy.get("id"),
            "sla_policy_id": policy.get("id"),
            "title": title,
            "active": active,
            "position": position,
            "description": policy.get("description"),
            "filter": policy.get("filter") if isinstance(policy.get("filter"), dict) else policy.get("conditions"),
            "filter_summary": filter_summary,
            "policy_metrics": metrics,
            "raw_policy_metrics": policy.get("policy_metrics") or policy.get("metrics") or [],
            "created_at": created_at,
            "updated_at": updated_at,
            "url": _policy_url(policy, base_url=base_url, policy_id=policy_id),
            "raw": policy,
        },
    )


def _metrics(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    metrics: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        metric = {
            "metric": item.get("metric"),
            "priority": item.get("priority"),
            "target": item.get("target"),
            "business_hours": item.get("business_hours"),
        }
        target = item.get("target")
        if isinstance(target, dict):
            metric["target_minutes"] = target.get("value") or target.get("minutes")
            metric["target_unit"] = target.get("unit")
        elif target is not None:
            metric["target_minutes"] = target
        metrics.append(metric)
    return metrics


def _filter_summary(value: object) -> list[str]:
    if not isinstance(value, dict):
        return []
    summaries: list[str] = []
    for group_name in ("all", "any"):
        conditions = value.get(group_name)
        if not isinstance(conditions, list):
            continue
        for condition in conditions:
            if not isinstance(condition, dict):
                continue
            field = _text(condition.get("field") or condition.get("field_name"))
            operator = _text(condition.get("operator"))
            condition_value = condition.get("value")
            if field:
                summaries.append(f"{group_name}:{field} {operator} {condition_value}".strip())
    return summaries


def _content(
    *,
    title: str,
    active: bool | None,
    metrics: list[dict[str, Any]],
    filter_summary: list[str],
    position: object,
) -> str:
    parts = [f"Zendesk SLA policy {title}"]
    if active is not None:
        parts.append(f"active {active}")
    if position is not None:
        parts.append(f"position {position}")
    if metrics:
        metric_bits = []
        for metric in metrics:
            name = _text(metric.get("metric"))
            priority = _text(metric.get("priority"))
            target = metric.get("target_minutes")
            metric_bits.append(" ".join(_text(part) for part in (name, priority, target) if _text(part)))
        parts.append("commitments " + "; ".join(bit for bit in metric_bits if bit))
    if filter_summary:
        parts.append("filters " + "; ".join(filter_summary))
    return "; ".join(parts)


def _policy_url(policy: dict[str, Any], *, base_url: str, policy_id: str) -> str:
    url = _optional(policy.get("url") or policy.get("html_url"))
    if url:
        return url
    return f"{base_url}/admin/objects-rules/rules/slas/{policy_id}" if base_url and policy_id else base_url


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
