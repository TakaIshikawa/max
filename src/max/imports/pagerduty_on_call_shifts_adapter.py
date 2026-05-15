"""PagerDuty on-call shifts import adapter."""

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


class PagerDutyOnCallShiftsAdapter(SourceAdapter):
    """Fetch PagerDuty on-call entries as operational staffing signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_token: str | None = None,
        api_url: str = DEFAULT_PAGERDUTY_API_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.api_token = api_token if api_token is not None else (
            token
            or _optional(self._config.get("api_token"))
            or _optional(self._config.get("token"))
            or os.getenv("PAGERDUTY_API_TOKEN")
        )
        self.api_url = (_optional(self._config.get("api_url")) or api_url).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "pagerduty_on_call_shifts_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("per_page") or self._config.get("limit") or self._config.get("page_size"), default=100, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.api_token:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            shifts = await self._fetch_shifts(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        for shift in shifts:
            signal = _shift_signal(shift, self.name, seen=seen)
            if signal:
                signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_shifts(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        shifts: list[dict[str, Any]] = []
        offset = _positive_int(self._config.get("offset"), default=0, maximum=1000000)
        while len(shifts) < limit:
            page_limit = min(self.page_size, limit - len(shifts))
            body = await self._get(client, params={**self._params(), "limit": page_limit, "offset": offset})
            if body is None:
                return []
            page = body.get("oncalls") if isinstance(body.get("oncalls"), list) else []
            if not page:
                break
            shifts.extend(item for item in page if isinstance(item, dict))
            if not bool(body.get("more")):
                break
            offset = _next_offset(body, offset, page_limit)
        return shifts[:limit]

    async def _get(self, client: httpx.AsyncClient, *, params: dict[str, Any]) -> dict[str, Any] | None:
        try:
            response = await client.get(f"{self.api_url}/oncalls", params=params, headers=self._headers())
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("PagerDuty on-call shifts fetch failed", exc_info=True)
            return None
        return body if isinstance(body, dict) else {}

    def _params(self) -> dict[str, Any]:
        params: dict[str, Any] = {}
        for config_key, param_key in (
            ("schedule_ids", "schedule_ids[]"),
            ("escalation_policy_ids", "escalation_policy_ids[]"),
        ):
            values = _strings(self._config.get(config_key) or self._config.get(config_key[:-1]))
            if values:
                params[param_key] = values
        for key in ("since", "until"):
            value = _optional(self._config.get(key))
            if value:
                params[key] = value
        return params

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.pagerduty+json;version=2",
            "Authorization": f"Token token={self.api_token}",
            "User-Agent": "max-pagerduty-on-call-shifts-import/1",
        }


PagerDutyOnCallShiftAdapter = PagerDutyOnCallShiftsAdapter


def _shift_signal(shift: dict[str, Any], adapter_name: str, *, seen: set[str]) -> Signal | None:
    user = shift.get("user") if isinstance(shift.get("user"), dict) else {}
    schedule = shift.get("schedule") if isinstance(shift.get("schedule"), dict) else {}
    policy = shift.get("escalation_policy") if isinstance(shift.get("escalation_policy"), dict) else {}
    user_id = _text(user.get("id"))
    schedule_id = _text(schedule.get("id"))
    policy_id = _text(policy.get("id"))
    start = _text(shift.get("start"))
    end = _text(shift.get("end"))
    level = shift.get("escalation_level")
    signal_id = f"pagerduty-on-call-shift:{user_id}:{schedule_id}:{policy_id}:{level}:{start}:{end}"
    if signal_id in seen:
        return None
    seen.add(signal_id)

    user_label = _text(user.get("summary") or user.get("name") or user_id) or "PagerDuty user"
    schedule_label = _text(schedule.get("summary") or schedule.get("name") or schedule_id)
    policy_label = _text(policy.get("summary") or policy.get("name") or policy_id)
    return Signal(
        id=signal_id,
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{user_label} PagerDuty on-call shift",
        content=_content(user_label=user_label, schedule_label=schedule_label, policy_label=policy_label, level=level),
        url=_text(shift.get("html_url") or shift.get("self") or schedule.get("html_url") or user.get("html_url")),
        author=user_label,
        published_at=_parse_dt(start),
        tags=sorted({"pagerduty", "on-call", "shift", "schedule", schedule_label, policy_label} - {""})[:10],
        credibility=0.72,
        metadata={
            "pagerduty_user": _entity(user),
            "pagerduty_schedule": _entity(schedule),
            "pagerduty_escalation_policy": _entity(policy),
            "escalation_level": level,
            "start": shift.get("start"),
            "end": shift.get("end"),
            "raw": shift,
        },
    )


def _content(*, user_label: str, schedule_label: str, policy_label: str, level: object) -> str:
    parts = [f"PagerDuty on-call shift for {user_label}"]
    if schedule_label:
        parts.append(f"schedule {schedule_label}")
    if policy_label:
        parts.append(f"escalation policy {policy_label}")
    if level is not None:
        parts.append(f"level {level}")
    return "; ".join(parts)


def _entity(value: dict[str, Any]) -> dict[str, Any]:
    if not value:
        return {}
    return {
        "id": value.get("id"),
        "summary": value.get("summary"),
        "name": value.get("name"),
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
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list | tuple | set):
        return [_text(item) for item in value if _text(item)]
    return []


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
