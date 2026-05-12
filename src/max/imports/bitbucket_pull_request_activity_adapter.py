"""Bitbucket pull request activity import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
BITBUCKET_API = "https://api.bitbucket.org/2.0"


class BitbucketPullRequestActivityAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        username: str | None = None,
        app_password: str | None = None,
        bearer_token: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.username = username if username is not None else (
            _optional(self._config.get("username")) or os.getenv("BITBUCKET_USERNAME")
        )
        self.app_password = app_password if app_password is not None else (
            _optional(self._config.get("app_password")) or os.getenv("BITBUCKET_APP_PASSWORD")
        )
        self.bearer_token = bearer_token if bearer_token is not None else (
            token
            or _optional(self._config.get("bearer_token"))
            or _optional(self._config.get("token"))
            or os.getenv("BITBUCKET_BEARER_TOKEN")
            or os.getenv("BITBUCKET_TOKEN")
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or BITBUCKET_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "bitbucket_pull_request_activity_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def workspace(self) -> str | None:
        return _optional(self._config.get("workspace"))

    @property
    def repo_slug(self) -> str | None:
        repository = _optional(self._config.get("repo_slug") or self._config.get("repository"))
        if repository and "/" in repository:
            return repository.rsplit("/", 1)[1]
        return repository

    @property
    def pull_request_ids(self) -> list[str]:
        return _strings(
            self._config.get("pull_request_ids")
            or self._config.get("pull_request_id")
            or self._config.get("pr_ids")
            or self._config.get("pr_id")
        )

    @property
    def pull_requests(self) -> list[dict[str, str]]:
        explicit = self._config.get("pull_requests")
        if isinstance(explicit, list):
            targets = [_pull_request_target(item, self.workspace, self.repo_slug) for item in explicit]
            return [target for target in targets if target]
        if self.workspace and self.repo_slug and self.pull_request_ids:
            return [
                {"workspace": self.workspace, "repo_slug": self.repo_slug, "pull_request_id": pull_request_id}
                for pull_request_id in self.pull_request_ids
            ]
        return []

    @property
    def page_size(self) -> int:
        return _positive_int(
            self._config.get("page_size") or self._config.get("page_len") or self._config.get("pagelen"),
            default=30,
            maximum=100,
        )

    @property
    def _has_auth(self) -> bool:
        return bool(self.bearer_token or (self.username and self.app_password))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.pull_requests and self._has_auth):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            activities: list[tuple[dict[str, str], dict[str, Any]]] = []
            for pull_request in self.pull_requests:
                if len(activities) >= limit:
                    break
                pull_request_activity = await self._fetch_activity(
                    client,
                    pull_request=pull_request,
                    limit=limit - len(activities),
                )
                if pull_request_activity is None:
                    return []
                activities.extend((pull_request, item) for item in pull_request_activity)
            return [
                _activity_signal(activity, pull_request, self.name)
                for pull_request, activity in activities[:limit]
            ]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_activity(
        self,
        client: httpx.AsyncClient,
        *,
        pull_request: dict[str, str],
        limit: int,
    ) -> list[dict[str, Any]] | None:
        activity: list[dict[str, Any]] = []
        url: str | None = (
            f"{self.api_url}/repositories/{pull_request['workspace']}/{pull_request['repo_slug']}"
            f"/pullrequests/{pull_request['pull_request_id']}/activity"
        )
        params: dict[str, Any] | None = {"pagelen": min(self.page_size, limit)}
        while url and len(activity) < limit:
            body = await self._get(client, url, params=params)
            if body is None:
                return None
            values = body.get("values") if isinstance(body.get("values"), list) else []
            if not values:
                break
            activity.extend(item for item in values if isinstance(item, dict))
            url = _optional(body.get("next"))
            params = None
        return activity[:limit]

    async def _get(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        headers = {"Accept": "application/json", "User-Agent": "max-bitbucket-pull-request-activity-import/1"}
        auth = None
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        else:
            auth = httpx.BasicAuth(self.username or "", self.app_password or "")
        try:
            response = await client.get(url, headers=headers, auth=auth, params=params)
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Bitbucket pull request activity fetch failed for %s", url, exc_info=True)
            return None
        return body if isinstance(body, dict) else {}


BitbucketPullRequestActivitiesAdapter = BitbucketPullRequestActivityAdapter


def _activity_signal(
    activity: dict[str, Any],
    pull_request: dict[str, str],
    adapter_name: str,
) -> Signal:
    activity_type, payload = _activity_payload(activity)
    actor = _actor(activity, payload)
    timestamp = _timestamp(activity, payload)
    event_id = _activity_id(activity, payload, activity_type, timestamp, actor)
    workspace = pull_request["workspace"]
    repo_slug = pull_request["repo_slug"]
    pull_request_id = pull_request["pull_request_id"]
    return Signal(
        id=f"bitbucket-pr-activity:{workspace}:{repo_slug}:{pull_request_id}:{event_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{workspace}/{repo_slug} PR #{pull_request_id} {activity_type.replace('_', ' ')}",
        content=_activity_content(activity_type, payload)[:1000],
        url=_activity_url(activity, payload),
        author=_optional(actor.get("display_name") or actor.get("nickname") or actor.get("username")),
        published_at=_parse_dt(timestamp),
        tags=sorted({"bitbucket", "pull-request", "activity", activity_type} - {""})[:10],
        credibility=0.65,
        metadata={
            "activity_type": activity_type,
            "workspace": workspace,
            "repository": repo_slug,
            "pull_request_id": pull_request_id,
            "actor": _summary(actor),
            "created_on": timestamp,
            "links": _links(activity, payload),
            "comment": _summary_payload(activity.get("comment")),
            "approval": _summary_payload(activity.get("approval")),
            "update": _summary_payload(activity.get("update")),
            "changes_requested": _summary_payload(activity.get("changes_requested")),
            "raw": activity,
        },
    )


def _activity_payload(activity: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    for activity_type in ("comment", "approval", "update", "changes_requested"):
        payload = activity.get(activity_type)
        if isinstance(payload, dict):
            if activity_type == "update" and _optional(payload.get("state")):
                return "status_change", payload
            return activity_type, payload
    for key, value in activity.items():
        if isinstance(value, dict):
            return _text(key) or "other", value
    return "other", {}


def _actor(activity: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    for value in (
        payload.get("user"),
        payload.get("author"),
        payload.get("actor"),
        activity.get("actor"),
        activity.get("user"),
    ):
        if isinstance(value, dict):
            return value
    return {}


def _timestamp(activity: dict[str, Any], payload: dict[str, Any]) -> str:
    for key in ("created_on", "date", "updated_on"):
        value = _optional(payload.get(key))
        if value:
            return value
    for key in ("created_on", "date", "updated_on"):
        value = _optional(activity.get(key))
        if value:
            return value
    return ""


def _activity_id(
    activity: dict[str, Any],
    payload: dict[str, Any],
    activity_type: str,
    timestamp: str,
    actor: dict[str, Any],
) -> str:
    explicit = _text(payload.get("id") or activity.get("id") or payload.get("uuid") or activity.get("uuid"))
    if explicit:
        return explicit
    actor_id = _text(actor.get("uuid") or actor.get("nickname") or actor.get("username") or actor.get("display_name"))
    return ":".join([activity_type, timestamp, actor_id, _activity_url(activity, payload)])


def _activity_content(activity_type: str, payload: dict[str, Any]) -> str:
    content = payload.get("content") if isinstance(payload.get("content"), dict) else {}
    text = _optional(content.get("raw") or content.get("html") or content.get("markup"))
    if text:
        return text
    if activity_type == "approval":
        return "approved pull request"
    if activity_type == "changes_requested":
        return "requested changes"
    if activity_type == "status_change":
        state = _optional(payload.get("state"))
        title = _optional(payload.get("title"))
        if state and title:
            return f"changed status to {state}: {title}"
        if state:
            return f"changed status to {state}"
    for key in ("description", "title", "summary", "state"):
        value = _optional(payload.get(key))
        if value:
            return value
    return activity_type.replace("_", " ")


def _activity_url(activity: dict[str, Any], payload: dict[str, Any]) -> str:
    links = _links(activity, payload)
    for key in ("html", "self"):
        href = _link_href(links.get(key))
        if href:
            return href
    return ""


def _links(activity: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    payload_links = payload.get("links") if isinstance(payload.get("links"), dict) else {}
    if payload_links:
        return payload_links
    return activity.get("links") if isinstance(activity.get("links"), dict) else {}


def _link_href(value: object) -> str:
    if isinstance(value, dict):
        return _text(value.get("href"))
    return ""


def _summary_payload(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "id": value.get("id"),
        "uuid": value.get("uuid"),
        "state": value.get("state"),
        "title": value.get("title"),
        "created_on": value.get("created_on"),
        "updated_on": value.get("updated_on"),
        "date": value.get("date"),
        "links": value.get("links"),
    }


def _summary(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "id": value.get("id"),
        "uuid": value.get("uuid"),
        "display_name": value.get("display_name"),
        "nickname": value.get("nickname"),
        "username": value.get("username"),
        "links": value.get("links"),
    }


def _pull_request_target(
    value: object,
    default_workspace: str | None,
    default_repo_slug: str | None,
) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    repository = _optional(value.get("repo_slug") or value.get("repository"))
    repo_slug = repository.rsplit("/", 1)[1] if repository and "/" in repository else repository
    target = {
        "workspace": _optional(value.get("workspace")) or default_workspace or "",
        "repo_slug": repo_slug or default_repo_slug or "",
        "pull_request_id": _optional(
            value.get("pull_request_id")
            or value.get("id")
            or value.get("pr_id")
            or value.get("number")
        )
        or "",
    }
    return target if all(target.values()) else {}


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
