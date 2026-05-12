"""ServiceNow change request import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class ServiceNowChangeRequestsAdapter(SourceAdapter):
    """Fetch ServiceNow change_request records and convert them to signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        instance_url: str | None = None,
        api_url: str | None = None,
        token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.instance_url = (
            instance_url
            or _optional(self._config.get("instance_url"))
            or _optional(self._config.get("instance"))
            or os.getenv("SERVICENOW_INSTANCE_URL")
            or ""
        ).rstrip("/")
        configured_api_url = api_url or _optional(self._config.get("api_url"))
        self.api_url = (configured_api_url.rstrip("/") if configured_api_url else self._default_api_url()).rstrip("/")
        self.token = token if token is not None else (_optional(self._config.get("token")) or os.getenv("SERVICENOW_API_TOKEN"))
        self.username = username if username is not None else _optional(self._config.get("username"))
        self.password = password if password is not None else _optional(self._config.get("password"))
        self._client = client

    @property
    def name(self) -> str:
        return "servicenow_change_requests_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def sysparm_query(self) -> str | None:
        return _optional(self._config.get("sysparm_query"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size"), default=100, maximum=1000)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.api_url or not (self.token or (self.username and self.password)):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            records: list[dict[str, Any]] = []
            offset = 0
            while len(records) < limit:
                page_limit = min(self.page_size, limit - len(records))
                page = await self._fetch_page(client, offset=offset, limit=page_limit)
                if not page:
                    break
                records.extend(page)
                if len(page) < page_limit:
                    break
                offset += len(page)
        finally:
            if close_client:
                await client.aclose()

        return [_change_request_signal(record, self.name, self.instance_url) for record in records[:limit] if isinstance(record, dict)]

    async def _fetch_page(self, client: httpx.AsyncClient, *, offset: int, limit: int) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "sysparm_limit": limit,
            "sysparm_offset": offset,
            "sysparm_display_value": "true",
            "sysparm_exclude_reference_link": "true",
            "sysparm_fields": ",".join(
                [
                    "sys_id",
                    "number",
                    "short_description",
                    "description",
                    "state",
                    "risk",
                    "impact",
                    "assignment_group",
                    "start_date",
                    "end_date",
                    "work_start",
                    "work_end",
                    "planned_start_date",
                    "planned_end_date",
                    "sys_created_on",
                    "sys_updated_on",
                    "opened_by",
                    "requested_by",
                ]
            ),
        }
        if self.sysparm_query:
            params["sysparm_query"] = self.sysparm_query

        try:
            response = await client.get(
                self.api_url,
                headers=self._headers(),
                auth=self._auth(),
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("ServiceNow change request fetch failed", exc_info=True)
            return []

        results = body.get("result") if isinstance(body, dict) else None
        return results if isinstance(results, list) else []

    def _default_api_url(self) -> str:
        return f"{self.instance_url}/api/now/table/change_request" if self.instance_url else ""

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _auth(self) -> tuple[str, str] | None:
        if self.token or not (self.username and self.password):
            return None
        return (self.username, self.password)


ServiceNowChangeRequestAdapter = ServiceNowChangeRequestsAdapter


def _change_request_signal(record: dict[str, Any], adapter_name: str, instance_url: str) -> Signal:
    number = _field_text(record.get("number"))
    sys_id = _field_text(record.get("sys_id"))
    state = _field_text(record.get("state"))
    risk = _field_text(record.get("risk"))
    impact = _field_text(record.get("impact"))
    assignment_group = _field_text(record.get("assignment_group"))
    short_description = _field_text(record.get("short_description"))
    title = " ".join(part for part in [number, short_description] if part) or sys_id
    url = f"{instance_url}/nav_to.do?uri=change_request.do?sys_id={sys_id}" if instance_url and sys_id else ""
    opened_by = _field_text(record.get("opened_by"))
    requested_by = _field_text(record.get("requested_by"))
    return Signal(
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=title,
        content=(_field_text(record.get("description")) or short_description)[:1000],
        url=url,
        author=opened_by or requested_by or None,
        published_at=_parse_dt(record.get("sys_created_on")),
        tags=sorted({"servicenow", "change-request", state, risk, impact} - {""})[:10],
        credibility=0.7,
        metadata={
            "sys_id": sys_id,
            "number": number,
            "short_description": short_description,
            "state": state,
            "risk": risk,
            "impact": impact,
            "assignment_group": assignment_group,
            "start_date": _field_text(record.get("start_date") or record.get("planned_start_date")),
            "end_date": _field_text(record.get("end_date") or record.get("planned_end_date")),
            "work_start": _field_text(record.get("work_start")),
            "work_end": _field_text(record.get("work_end")),
            "sys_created_on": _field_text(record.get("sys_created_on")),
            "sys_updated_on": _field_text(record.get("sys_updated_on")),
            "opened_by": opened_by,
            "requested_by": requested_by,
        },
    )


def _field_text(value: object) -> str:
    if isinstance(value, dict):
        return _text(value.get("display_value") or value.get("value"))
    return _text(value)


def _parse_dt(value: object) -> datetime | None:
    text = _field_text(value)
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
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


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
