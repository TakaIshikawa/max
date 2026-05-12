"""Jira Service Management requests import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
ATLASSIAN_API = "https://api.atlassian.com"


class JiraServiceManagementRequestsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        cloud_id: str | None = None,
        site_url: str | None = None,
        email: str | None = None,
        token: str | None = None,
        bearer_token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.cloud_id = cloud_id or _optional(self._config.get("cloud_id"))
        self.site_url = (site_url or _optional(self._config.get("site_url")) or _optional(self._config.get("base_url")) or "").rstrip("/")
        self.email = email if email is not None else (_optional(self._config.get("email")) or os.getenv("JIRA_EMAIL") or os.getenv("JIRA_USERNAME"))
        self.token = token if token is not None else (_optional(self._config.get("token")) or _optional(self._config.get("api_token")))
        self.bearer_token = (
            bearer_token
            if bearer_token is not None
            else (_optional(self._config.get("bearer_token")) or os.getenv("JIRA_SERVICE_MANAGEMENT_TOKEN"))
        )
        self._client = client

    @property
    def name(self) -> str:
        return "jira_service_management_requests_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def base_url(self) -> str:
        if self.cloud_id:
            return f"{ATLASSIAN_API}/ex/jira/{self.cloud_id}/rest/servicedeskapi"
        return f"{self.site_url}/rest/servicedeskapi" if self.site_url else ""

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size"), default=50, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.base_url or not (self.bearer_token or (self.email and self.token)):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            requests: list[dict[str, Any]] = []
            start = 0
            while len(requests) < limit:
                page_limit = min(self.page_size, limit - len(requests))
                body = await self._fetch_page(client, start=start, limit=page_limit)
                values = body.get("values") if isinstance(body.get("values"), list) else []
                if not values:
                    break
                requests.extend(values)
                if body.get("isLastPage") is True or len(values) < page_limit:
                    break
                start = _int(body.get("start"), start) + len(values)
        finally:
            if close_client:
                await client.aclose()

        return [_request_signal(request, self.name, self.site_url) for request in requests[:limit] if isinstance(request, dict)]

    async def _fetch_page(self, client: httpx.AsyncClient, *, start: int, limit: int) -> dict[str, Any]:
        try:
            response = await client.get(
                f"{self.base_url}/request",
                headers=self._headers(),
                auth=self._auth(),
                params=self._params(start=start, limit=limit),
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Jira Service Management request fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}

    def _params(self, *, start: int, limit: int) -> dict[str, Any]:
        params: dict[str, Any] = {"start": start, "limit": limit}
        mapping = {
            "service_desk_id": "serviceDeskId",
            "request_type_id": "requestTypeId",
            "status": "requestStatus",
        }
        for config_key, param_key in mapping.items():
            value = _optional(self._config.get(config_key))
            if value:
                params[param_key] = value
        return params

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers

    def _auth(self) -> tuple[str, str] | None:
        if self.bearer_token or not (self.email and self.token):
            return None
        return (self.email, self.token)


JiraServiceManagementRequestAdapter = JiraServiceManagementRequestsAdapter


def _request_signal(request: dict[str, Any], adapter_name: str, site_url: str) -> Signal:
    key = _text(request.get("issueKey") or request.get("requestKey"))
    status = request.get("currentStatus") if isinstance(request.get("currentStatus"), dict) else {}
    request_type = request.get("requestType") if isinstance(request.get("requestType"), dict) else {}
    service_desk = request.get("serviceDesk") if isinstance(request.get("serviceDesk"), dict) else {}
    reporter = request.get("reporter") if isinstance(request.get("reporter"), dict) else {}
    links = request.get("_links") if isinstance(request.get("_links"), dict) else {}
    issue_url = _text(request.get("issueUrl") or request.get("webUrl") or links.get("web"))
    if not issue_url and site_url and key:
        issue_url = f"{site_url}/browse/{key}"
    created = _date_field(request.get("createdDate"))
    updated = _date_field(request.get("updatedDate"))
    summary = _text(request.get("summary") or request.get("requestFieldValues") or key)
    return Signal(
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=summary or key or _text(request.get("issueId")),
        content=summary[:1000],
        url=issue_url,
        author=_text(reporter.get("displayName") or reporter.get("emailAddress") or reporter.get("name")) or None,
        published_at=_parse_dt(created),
        tags=sorted({"jira-service-management", "service-request", _text(status.get("status")), _text(request_type.get("name"))} - {""})[:10],
        credibility=0.7,
        metadata={
            "issue_id": request.get("issueId"),
            "request_id": request.get("requestId"),
            "request_key": key,
            "summary": summary,
            "status": status.get("status"),
            "status_category": status.get("statusCategory"),
            "request_type_id": request_type.get("id") or request.get("requestTypeId"),
            "request_type": request_type.get("name"),
            "service_desk_id": service_desk.get("id") or request.get("serviceDeskId"),
            "service_desk": service_desk.get("name"),
            "reporter": reporter.get("displayName") or reporter.get("name"),
            "reporter_email": reporter.get("emailAddress"),
            "created_at": created,
            "updated_at": updated,
            "issue_url": issue_url,
        },
    )


def _date_field(value: object) -> str:
    if isinstance(value, dict):
        return _text(value.get("iso8601") or value.get("jira") or value.get("friendly"))
    return _text(value)


def _parse_dt(value: object) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    return None


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
