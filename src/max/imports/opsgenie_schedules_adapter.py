"""Opsgenie schedules import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
DEFAULT_OPSGENIE_API_URL = "https://api.opsgenie.com"


class OpsgenieSchedulesImportAdapter(SourceAdapter):
    """Fetch Opsgenie schedules and convert them to Max signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.api_key = (
            api_key
            if api_key is not None
            else (_optional(self._config.get("api_key")) or os.getenv("OPSGENIE_API_KEY"))
        )
        self.api_url = _api_root(
            api_url or _optional(self._config.get("api_url")) or DEFAULT_OPSGENIE_API_URL
        )
        self._client = client

    @property
    def name(self) -> str:
        return "opsgenie_schedules_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def page_size(self) -> int:
        return _positive_int(
            self._config.get("page_size") or self._config.get("limit"),
            default=100,
            maximum=100,
        )

    @property
    def initial_offset(self) -> int:
        return _non_negative_int(self._config.get("offset"), default=0)

    @property
    def expand(self) -> list[str]:
        return _strings(self._config.get("expand"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.api_key:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            schedules = await self._fetch_schedules(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        for schedule, offset in schedules:
            signal = _schedule_signal(schedule, offset=offset, adapter_name=self.name, seen=seen)
            if signal:
                signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_schedules(
        self,
        client: httpx.AsyncClient,
        *,
        limit: int,
    ) -> list[tuple[dict[str, Any], int]]:
        schedules: list[tuple[dict[str, Any], int]] = []
        offset = self.initial_offset
        while len(schedules) < limit:
            page_limit = min(self.page_size, limit - len(schedules))
            body = await self._get(
                client,
                "/v2/schedules",
                params=self._params(limit=page_limit, offset=offset),
            )
            page = _schedules_from_body(body)
            if not page:
                break
            schedules.extend(
                (schedule, offset + index)
                for index, schedule in enumerate(page)
                if isinstance(schedule, dict)
            )
            if len(page) < page_limit or not _has_more(body, page_limit=page_limit):
                break
            offset = _next_offset(body, offset, page_limit)
        return schedules[:limit]

    def _params(self, *, limit: int, offset: int) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if self.expand:
            params["expand"] = ",".join(self.expand)
        return params

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
                headers=self._headers(),
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Opsgenie schedules fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"GenieKey {self.api_key}",
            "User-Agent": "max-opsgenie-schedules-import/1",
        }


OpsgenieSchedulesAdapter = OpsgenieSchedulesImportAdapter


def _schedule_signal(
    schedule: dict[str, Any],
    *,
    offset: int,
    adapter_name: str,
    seen: set[str],
) -> Signal | None:
    schedule_id = _optional(schedule.get("id") or schedule.get("scheduleId"))
    schedule_name = _optional(schedule.get("name"))
    signal_key = schedule_id or schedule_name
    if not signal_key:
        return None
    signal_id = f"opsgenie-schedule:{signal_key}"
    if signal_id in seen:
        return None
    seen.add(signal_id)

    timezone = _optional(schedule.get("timezone") or schedule.get("timeZone"))
    enabled = _bool_or_none(schedule.get("enabled") if "enabled" in schedule else schedule.get("isEnabled"))
    owner_team = _summary(schedule.get("ownerTeam") or schedule.get("team"))
    rotations = _rotations(schedule.get("rotations"))
    web_url = _optional(schedule.get("webUrl") or schedule.get("url") or schedule.get("html_url"))
    api_identifier = _optional(schedule.get("apiIdentifier") or schedule.get("api_identifier"))

    return Signal(
        id=signal_id,
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"Opsgenie schedule {schedule_name or signal_key}",
        content=_content(
            name=schedule_name or signal_key,
            enabled=enabled,
            timezone=timezone,
            owner_team=owner_team,
            rotations=rotations,
        ),
        url=web_url or _text(schedule.get("links", {}).get("web") if isinstance(schedule.get("links"), dict) else ""),
        author=_optional(owner_team.get("name") or owner_team.get("id")),
        published_at=_parse_dt(schedule.get("createdAt") or schedule.get("created_at")),
        tags=sorted({"opsgenie", "schedule", _text(owner_team.get("name"))} - {""})[:10],
        credibility=0.7,
        metadata={
            "signal_role": "ownership",
            "opsgenie_schedule_id": schedule_id,
            "api_identifier": api_identifier,
            "name": schedule_name,
            "description": schedule.get("description"),
            "timezone": timezone,
            "enabled": enabled,
            "owner_team": owner_team,
            "rotations": rotations,
            "web_url": web_url,
            "createdAt": schedule.get("createdAt") or schedule.get("created_at"),
            "updatedAt": schedule.get("updatedAt") or schedule.get("updated_at"),
            "offset": offset,
            "raw": schedule,
        },
    )


def _content(
    *,
    name: str,
    enabled: bool | None,
    timezone: str | None,
    owner_team: dict[str, Any],
    rotations: list[dict[str, Any]],
) -> str:
    parts = [f"Opsgenie schedule {name}"]
    if enabled is not None:
        parts.append("enabled" if enabled else "disabled")
    if timezone:
        parts.append(f"timezone {timezone}")
    owner = _optional(owner_team.get("name") or owner_team.get("id"))
    if owner:
        parts.append(f"owner team {owner}")
    if rotations:
        parts.append("rotations: " + "; ".join(_rotation_text(rotation) for rotation in rotations[:5]))
    return "; ".join(parts)


def _rotation_text(rotation: dict[str, Any]) -> str:
    pieces = [_optional(rotation.get("name")) or "unnamed rotation"]
    rotation_type = _optional(rotation.get("type") or rotation.get("rotationType"))
    if rotation_type:
        pieces.append(rotation_type)
    participants = rotation.get("participants")
    if isinstance(participants, list):
        pieces.append(f"{len(participants)} participants")
    start = _optional(rotation.get("startDate") or rotation.get("start_date"))
    if start:
        pieces.append(f"starts {start}")
    return " ".join(pieces)


def _schedules_from_body(body: dict[str, Any]) -> list[dict[str, Any]]:
    data = body.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict) and isinstance(data.get("schedules"), list):
        return [item for item in data["schedules"] if isinstance(item, dict)]
    if isinstance(body.get("schedules"), list):
        return [item for item in body["schedules"] if isinstance(item, dict)]
    return []


def _has_more(body: dict[str, Any], *, page_limit: int) -> bool:
    if isinstance(body.get("more"), bool):
        return bool(body["more"])
    paging = body.get("paging")
    if isinstance(paging, dict):
        return bool(paging.get("next"))
    data = body.get("data")
    if isinstance(data, dict) and isinstance(data.get("paging"), dict):
        return bool(data["paging"].get("next"))
    return len(_schedules_from_body(body)) >= page_limit


def _next_offset(body: dict[str, Any], offset: int, page_limit: int) -> int:
    for source in (body, body.get("data") if isinstance(body.get("data"), dict) else {}):
        if isinstance(source, dict) and isinstance(source.get("offset"), int):
            return int(source["offset"]) + int(source.get("limit") or page_limit)
    return offset + page_limit


def _rotations(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rotations: list[dict[str, Any]] = []
    for rotation in value:
        if not isinstance(rotation, dict):
            continue
        rotations.append(
            {
                "id": rotation.get("id"),
                "name": rotation.get("name"),
                "type": rotation.get("type") or rotation.get("rotationType"),
                "startDate": rotation.get("startDate") or rotation.get("start_date"),
                "endDate": rotation.get("endDate") or rotation.get("end_date"),
                "participants": _participants(rotation.get("participants")),
                "timeRestriction": rotation.get("timeRestriction") or rotation.get("time_restriction"),
            }
        )
    return rotations


def _participants(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    participants: list[dict[str, Any]] = []
    for participant in value:
        if isinstance(participant, dict):
            participants.append(
                {
                    "id": participant.get("id"),
                    "name": participant.get("name") or participant.get("username"),
                    "type": participant.get("type"),
                }
            )
        else:
            text = _optional(participant)
            if text:
                participants.append({"name": text})
    return participants


def _summary(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: value.get(key)
        for key in ("id", "name")
        if value.get(key) is not None
    }


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _api_root(value: str) -> str:
    url = value.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    for suffix in ("/v2/schedules", "/v2"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url.rstrip("/")


def _positive_int(value: object, *, default: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number <= 0:
        return default
    return min(number, maximum)


def _non_negative_int(value: object, *, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number >= 0 else default


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "enabled"}:
            return True
        if lowered in {"false", "0", "no", "disabled"}:
            return False
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
