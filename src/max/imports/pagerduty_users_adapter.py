"""PagerDuty users import adapter."""

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


class PagerDutyUsersAdapter(SourceAdapter):
    """Fetch PagerDuty users and convert them to Max signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        api_token: str | None = None,
        token: str | None = None,
        from_email: str | None = None,
        api_url: str = DEFAULT_PAGERDUTY_API_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        explicit_token = api_token if api_token is not None else token
        self.api_token = explicit_token if explicit_token is not None else (
            _optional(self._config.get("api_token"))
            or _optional(self._config.get("token"))
            or os.getenv("PAGERDUTY_API_TOKEN")
            or os.getenv("PAGERDUTY_TOKEN")
        )
        self.from_email = from_email if from_email is not None else (
            _optional(self._config.get("from_email")) or os.getenv("PAGERDUTY_FROM_EMAIL")
        )
        self.api_url = (_optional(self._config.get("api_url")) or api_url).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "pagerduty_users_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page") or self._config.get("limit"), default=100, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        effective_limit = min(limit, _positive_int(self._config.get("limit"), default=limit, maximum=100000))
        if effective_limit <= 0 or not self.api_token:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            users = await self._fetch_users(client, limit=effective_limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        for user in users:
            if not isinstance(user, dict):
                continue
            signal = _user_signal(user, adapter_name=self.name, seen=seen)
            if signal:
                signals.append(signal)
            if len(signals) >= effective_limit:
                break
        return signals

    async def _fetch_users(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        users: list[dict[str, Any]] = []
        offset = _positive_int(self._config.get("offset"), default=0, maximum=1000000)
        while len(users) < limit:
            page_limit = min(self.per_page, limit - len(users))
            body = await self._get(client, params={**self._params(), "limit": page_limit, "offset": offset})
            page = body.get("users") if isinstance(body, dict) else []
            if not isinstance(page, list) or not page:
                break
            users.extend(item for item in page if isinstance(item, dict))
            if not bool(body.get("more")):
                break
            offset = _next_offset(body, offset, page_limit)
        return users[:limit]

    async def _get(self, client: httpx.AsyncClient, *, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await client.get(f"{self.api_url}/users", params=params, headers=self._headers())
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("PagerDuty users fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}

    def _params(self) -> dict[str, Any]:
        params: dict[str, Any] = {}
        for config_key, param_key in (
            ("team_ids", "team_ids[]"),
            ("query", "query"),
            ("include", "include[]"),
        ):
            value = self._config.get(config_key) or self._config.get(config_key[:-1])
            values = _strings(value)
            if values:
                params[param_key] = values if param_key.endswith("[]") else values[0]
        return params

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.pagerduty+json;version=2",
            "Authorization": f"Token token={self.api_token}",
            "User-Agent": "max-pagerduty-users-import/1",
        }
        if self.from_email:
            headers["From"] = self.from_email
        return headers


PagerDutyUserAdapter = PagerDutyUsersAdapter


def _user_signal(user: dict[str, Any], *, adapter_name: str, seen: set[str]) -> Signal | None:
    user_id = _text(user.get("id"))
    if not user_id:
        return None
    signal_id = f"pagerduty-user:{user_id}"
    if signal_id in seen:
        return None
    seen.add(signal_id)

    name = _text(user.get("name") or user.get("summary") or user_id)
    email = _text(user.get("email"))
    role = _text(user.get("role"))
    job_title = _text(user.get("job_title"))
    time_zone = _text(user.get("time_zone") or user.get("timezone"))
    contact_methods = _contact_methods(user.get("contact_methods"))
    teams = _teams(user.get("teams"))
    return Signal(
        id=signal_id,
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"PagerDuty user {name}",
        content=_content(name=name, email=email, role=role, job_title=job_title, teams=teams),
        url=_text(user.get("html_url") or user.get("self")),
        author=name or None,
        published_at=_parse_dt(user.get("created_at") or user.get("updated_at")),
        tags=sorted({"pagerduty", "user", "operations", role, time_zone} - {""})[:10],
        credibility=0.72,
        metadata={
            "pagerduty_user_id": user.get("id"),
            "user_id": user.get("id"),
            "name": name or None,
            "email": email or None,
            "role": role or None,
            "job_title": job_title or None,
            "time_zone": time_zone or None,
            "contact_methods": contact_methods,
            "contact_methods_summary": _contact_methods_summary(contact_methods),
            "teams": teams,
            "created_at": user.get("created_at"),
            "updated_at": user.get("updated_at"),
            "raw": user,
        },
    )


def _content(
    *,
    name: str,
    email: str,
    role: str,
    job_title: str,
    teams: list[dict[str, Any]],
) -> str:
    parts = [f"PagerDuty user profile for {name or email or 'unknown user'}"]
    if email:
        parts.append(email)
    if role:
        parts.append(f"role {role}")
    if job_title:
        parts.append(f"title {job_title}")
    team_names = [team["summary"] for team in teams if team.get("summary")]
    if team_names:
        parts.append(f"teams {', '.join(team_names)}")
    return "; ".join(parts)


def _contact_methods(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    methods: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        summary = _summary(item, ("id", "type", "summary", "label", "address", "send_short_email", "self"))
        if summary:
            methods.append(summary)
    return methods


def _contact_methods_summary(contact_methods: list[dict[str, Any]]) -> list[str]:
    summary: list[str] = []
    for method in contact_methods:
        label = _text(method.get("summary") or method.get("label") or method.get("address") or method.get("type"))
        if label:
            summary.append(label)
    return summary


def _teams(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    teams: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        summary = _summary(item, ("id", "summary", "name", "type", "html_url", "self"))
        if "summary" not in summary and summary.get("name"):
            summary["summary"] = summary["name"]
        if summary:
            teams.append(summary)
    return teams


def _summary(value: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: value.get(key) for key in keys if value.get(key) is not None}


def _next_offset(body: dict[str, Any], offset: int, page_limit: int) -> int:
    if isinstance(body.get("offset"), int):
        return int(body["offset"]) + int(body.get("limit") or page_limit)
    return offset + page_limit


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
    if number < 0:
        return default
    return min(number, maximum)


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list | tuple | set):
        return [_text(item) for item in value if _text(item)]
    return []


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
