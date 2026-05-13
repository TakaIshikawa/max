"""HubSpot company activities import adapter."""

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
ACTIVITY_TYPES = ("calls", "emails", "meetings", "tasks")
DEFAULT_PROPERTIES = {
    "calls": [
        "hs_call_title",
        "hs_call_body",
        "hs_timestamp",
        "hubspot_owner_id",
        "hs_call_direction",
        "hs_call_status",
        "hs_call_duration",
        "createdate",
        "hs_lastmodifieddate",
    ],
    "emails": [
        "hs_email_subject",
        "hs_email_text",
        "hs_email_html",
        "hs_timestamp",
        "hubspot_owner_id",
        "hs_email_direction",
        "hs_email_status",
        "createdate",
        "hs_lastmodifieddate",
    ],
    "meetings": [
        "hs_meeting_title",
        "hs_meeting_body",
        "hs_timestamp",
        "hubspot_owner_id",
        "hs_meeting_outcome",
        "hs_meeting_start_time",
        "hs_meeting_end_time",
        "createdate",
        "hs_lastmodifieddate",
    ],
    "tasks": [
        "hs_task_subject",
        "hs_task_body",
        "hs_timestamp",
        "hubspot_owner_id",
        "hs_task_status",
        "hs_task_priority",
        "createdate",
        "hs_lastmodifieddate",
    ],
}


class HubSpotCompanyActivitiesAdapter(SourceAdapter):
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
        return "hubspot_company_activities_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def company_ids(self) -> list[str]:
        return _strings(
            self._config.get("company_ids")
            or self._config.get("companies")
            or self._config.get("company_id")
        )

    @property
    def activity_types(self) -> list[str]:
        configured = _strings(
            self._config.get("activity_types")
            or self._config.get("activity_type")
            or self._config.get("types")
            or self._config.get("type")
        )
        normalized = [_activity_type(value) for value in configured]
        return [value for value in normalized if value in ACTIVITY_TYPES] or list(ACTIVITY_TYPES)

    @property
    def association_type_ids(self) -> set[str]:
        return set(
            _strings(
                self._config.get("association_type_ids")
                or self._config.get("association_type_id")
                or self._config.get("association_types")
                or self._config.get("association_type")
            )
        )

    @property
    def associations(self) -> list[str]:
        return _strings(self._config.get("associations")) or ["companies", "contacts", "deals"]

    @property
    def association_page_limit(self) -> int:
        return _positive_int(self._config.get("association_page_limit"), default=100, maximum=500)

    @property
    def per_company_limit(self) -> int | None:
        value = self._config.get("per_company_limit")
        if value is None:
            return None
        return _positive_int(value, default=0, maximum=10_000) or None

    @property
    def properties(self) -> dict[str, list[str]]:
        configured = self._config.get("properties")
        if isinstance(configured, dict):
            return {
                activity_type: _strings(configured.get(activity_type)) or DEFAULT_PROPERTIES[activity_type]
                for activity_type in ACTIVITY_TYPES
            }
        common = _strings(configured)
        if common:
            return {activity_type: common for activity_type in ACTIVITY_TYPES}
        return {activity_type: list(properties) for activity_type, properties in DEFAULT_PROPERTIES.items()}

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.company_ids:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            seen: set[str] = set()
            for company_id in self.company_ids:
                if len(signals) >= limit:
                    break
                company_limit = min(self.per_company_limit or limit, limit - len(signals))
                for activity_type in self.activity_types:
                    if len(signals) >= limit or company_limit <= 0:
                        break
                    activity_ids = await self._fetch_activity_ids(
                        client,
                        company_id=company_id,
                        activity_type=activity_type,
                        limit=company_limit,
                    )
                    for activity_id in activity_ids:
                        if len(signals) >= limit or company_limit <= 0:
                            break
                        activity = await self._fetch_activity(
                            client,
                            activity_type=activity_type,
                            activity_id=activity_id,
                        )
                        if not activity:
                            continue
                        signal = _activity_signal(
                            activity,
                            company_id=company_id,
                            activity_type=activity_type,
                            adapter_name=self.name,
                            seen=seen,
                        )
                        if signal:
                            signals.append(signal)
                            company_limit -= 1
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_activity_ids(
        self,
        client: httpx.AsyncClient,
        *,
        company_id: str,
        activity_type: str,
        limit: int,
    ) -> list[str]:
        activity_ids: list[str] = []
        after: str | None = None
        while len(activity_ids) < limit:
            body = await self._get(
                client,
                f"{self.api_url}/crm/v4/objects/companies/{company_id}/associations/{activity_type}",
                params={
                    "limit": min(self.association_page_limit, limit - len(activity_ids)),
                    **({"after": after} if after else {}),
                },
            )
            results = body.get("results") if isinstance(body, dict) else []
            if not isinstance(results, list) or not results:
                break
            for item in results:
                activity_id = _association_activity_id(item, self.association_type_ids)
                if activity_id and activity_id not in activity_ids:
                    activity_ids.append(activity_id)
                    if len(activity_ids) >= limit:
                        break
            next_after = _next_after(body)
            if not next_after:
                break
            after = next_after
        return activity_ids[:limit]

    async def _fetch_activity(
        self,
        client: httpx.AsyncClient,
        *,
        activity_type: str,
        activity_id: str,
    ) -> dict[str, Any]:
        body = await self._get(
            client,
            f"{self.api_url}/crm/v3/objects/{activity_type}/{activity_id}",
            params={"properties": self.properties[activity_type], "associations": self.associations},
        )
        return body if isinstance(body, dict) else {}

    async def _get(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, Any],
    ) -> object:
        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-hubspot-company-activities-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.warning("HubSpot company activities fetch failed for %s", url, exc_info=True)
            return {}


HubSpotCompanyActivityAdapter = HubSpotCompanyActivitiesAdapter


def _activity_signal(
    activity: dict[str, Any],
    *,
    company_id: str,
    activity_type: str,
    adapter_name: str,
    seen: set[str],
) -> Signal | None:
    activity_id = _optional(activity.get("id"))
    if not activity_id:
        return None
    singular = activity_type[:-1]
    external_id = f"hubspot-company-activity:{company_id}:{singular}:{activity_id}"
    if external_id in seen:
        return None
    seen.add(external_id)

    props = activity.get("properties") if isinstance(activity.get("properties"), dict) else {}
    title = _title(props, singular, activity_id)
    body = _body(props, singular)
    owner = _text(props.get("hubspot_owner_id"))
    timestamp = _timestamp(props, activity, singular)
    created_at = props.get("createdate") or activity.get("createdAt") or timestamp
    updated_at = props.get("hs_lastmodifieddate") or activity.get("updatedAt")
    associations = activity.get("associations") if isinstance(activity.get("associations"), dict) else {}
    url = _activity_url(activity, company_id, singular, activity_id)

    return Signal(
        id=external_id,
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=title,
        content=body or title,
        url=url,
        author=owner or None,
        published_at=_parse_dt(timestamp),
        tags=sorted({"hubspot", "company", singular, _status(props, singular).lower()} - {""})[:10],
        credibility=0.68,
        metadata={
            "signal_role": "market",
            "hubspot_company_id": company_id,
            "company_id": company_id,
            "hubspot_activity_id": activity.get("id"),
            "activity_id": activity.get("id"),
            "activity_type": singular,
            "owner_id": owner or None,
            "subject": title,
            "body": body or None,
            "timestamp": timestamp,
            "created_at": created_at,
            "updated_at": updated_at,
            "status": _status(props, singular) or None,
            "direction": _direction(props, singular) or None,
            "url": url,
            "archived": activity.get("archived"),
            "associations": associations,
            "properties": props,
            "raw": activity,
        },
    )


def _title(props: dict[str, Any], singular: str, activity_id: str) -> str:
    keys = {
        "call": ("hs_call_title",),
        "email": ("hs_email_subject",),
        "meeting": ("hs_meeting_title",),
        "task": ("hs_task_subject",),
    }.get(singular, ())
    for key in keys:
        value = _optional(props.get(key))
        if value:
            return value
    return f"HubSpot {singular} {activity_id}"


def _body(props: dict[str, Any], singular: str) -> str:
    keys = {
        "call": ("hs_call_body",),
        "email": ("hs_email_text", "hs_email_html"),
        "meeting": ("hs_meeting_body",),
        "task": ("hs_task_body",),
    }.get(singular, ())
    for key in keys:
        value = _text(props.get(key))
        if value:
            return value
    return ""


def _timestamp(props: dict[str, Any], activity: dict[str, Any], singular: str) -> object:
    if singular == "meeting":
        return props.get("hs_meeting_start_time") or props.get("hs_timestamp") or props.get("createdate") or activity.get("createdAt")
    return props.get("hs_timestamp") or props.get("createdate") or activity.get("createdAt")


def _status(props: dict[str, Any], singular: str) -> str:
    key = {
        "call": "hs_call_status",
        "email": "hs_email_status",
        "meeting": "hs_meeting_outcome",
        "task": "hs_task_status",
    }.get(singular)
    return _text(props.get(key)) if key else ""


def _direction(props: dict[str, Any], singular: str) -> str:
    key = {
        "call": "hs_call_direction",
        "email": "hs_email_direction",
    }.get(singular)
    return _text(props.get(key)) if key else ""


def _association_activity_id(item: object, association_type_ids: set[str]) -> str | None:
    if not isinstance(item, dict):
        return None
    if association_type_ids and not _matches_association_type(item, association_type_ids):
        return None
    return _optional(item.get("toObjectId") or item.get("id"))


def _matches_association_type(item: dict[str, Any], association_type_ids: set[str]) -> bool:
    for key in ("typeId", "associationTypeId"):
        if _text(item.get(key)) in association_type_ids:
            return True
    association_types = item.get("associationTypes")
    if not isinstance(association_types, list):
        return False
    for association_type in association_types:
        if not isinstance(association_type, dict):
            continue
        values = {
            _text(association_type.get("typeId")),
            _text(association_type.get("associationTypeId")),
            _text(association_type.get("label")),
            _text(association_type.get("category")),
        }
        if values & association_type_ids:
            return True
    return False


def _next_after(body: dict[str, Any]) -> str | None:
    paging = body.get("paging") if isinstance(body.get("paging"), dict) else {}
    next_page = paging.get("next") if isinstance(paging.get("next"), dict) else {}
    return _optional(next_page.get("after"))


def _activity_url(activity: dict[str, Any], company_id: str, singular: str, activity_id: str) -> str:
    if _text(activity.get("url")):
        return _text(activity.get("url"))
    return f"https://app.hubspot.com/contacts/company/{company_id}?activity={singular}-{activity_id}"


def _activity_type(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    aliases = {
        "call": "calls",
        "calls": "calls",
        "email": "emails",
        "emails": "emails",
        "meeting": "meetings",
        "meetings": "meetings",
        "task": "tasks",
        "tasks": "tasks",
    }
    return aliases.get(normalized, normalized)


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
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        value = [item.strip() for item in str(value).split(",")]
    if not isinstance(value, list):
        return []
    strings: list[str] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, bool):
            continue
        text = _text(item)
        if text and text not in seen:
            seen.add(text)
            strings.append(text)
    return strings


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
