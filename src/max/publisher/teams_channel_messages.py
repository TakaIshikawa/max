"""Microsoft Graph Teams channel message publisher."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_GRAPH_API_URL = "https://graph.microsoft.com/v1.0"
DEFAULT_TIMEOUT_SECONDS = 10.0


class TeamsChannelMessagePublishError(RuntimeError):
    """Raised when a Teams channel message publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class TeamsChannelMessagePayload:
    team_id: str
    channel_id: str
    graph_payload: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"team_id": self.team_id, "channel_id": self.channel_id, "graph_payload": self.graph_payload, "metadata": self.metadata}


@dataclass(frozen=True)
class TeamsChannelMessagePublishResult:
    status_code: int | None
    team_id: str
    channel_id: str
    message_id: str | None
    web_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class TeamsChannelMessagePublisher:
    """Build and optionally post Microsoft Graph chatMessage payloads."""

    def __init__(
        self,
        *,
        access_token: str | None = None,
        team_id: str | None = None,
        channel_id: str | None = None,
        api_url: str = DEFAULT_GRAPH_API_URL,
        subject: str | None = None,
        importance: str | None = None,
        content_type: str = "html",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.access_token = _optional(access_token)
        self.team_id = _optional(team_id)
        self.channel_id = _optional(channel_id)
        self.api_url = api_url.rstrip("/")
        self.subject = _optional(subject)
        self.importance = _optional(importance)
        self.content_type = content_type if content_type in {"html", "text"} else "html"
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        access_token: str | None = None,
        team_id: str | None = None,
        channel_id: str | None = None,
        api_url: str | None = None,
        subject: str | None = None,
        importance: str | None = None,
        content_type: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> TeamsChannelMessagePublisher:
        return cls(
            access_token=access_token or os.getenv("TEAMS_GRAPH_ACCESS_TOKEN") or os.getenv("MICROSOFT_GRAPH_ACCESS_TOKEN"),
            team_id=team_id or os.getenv("TEAMS_TEAM_ID"),
            channel_id=channel_id or os.getenv("TEAMS_CHANNEL_ID"),
            api_url=api_url or os.getenv("TEAMS_GRAPH_API_URL") or DEFAULT_GRAPH_API_URL,
            subject=subject or os.getenv("TEAMS_MESSAGE_SUBJECT"),
            importance=importance or os.getenv("TEAMS_MESSAGE_IMPORTANCE"),
            content_type=content_type or os.getenv("TEAMS_MESSAGE_CONTENT_TYPE") or "html",
            timeout=timeout,
            client=client,
        )

    def message_endpoint(self, team_id: str | None = None, channel_id: str | None = None) -> str:
        return f"{self.api_url}/teams/{self._resolve_team_id(team_id)}/channels/{self._resolve_channel_id(channel_id)}/messages"

    def build_message_payload(
        self,
        artifact: dict[str, Any] | str,
        *,
        team_id: str | None = None,
        channel_id: str | None = None,
        subject: str | None = None,
        body: str | None = None,
        importance: str | None = None,
        content_type: str | None = None,
    ) -> TeamsChannelMessagePayload:
        resolved_team = self._resolve_team_id(team_id)
        resolved_channel = self._resolve_channel_id(channel_id)
        resolved_content_type = content_type or self.content_type
        graph_payload: dict[str, Any] = {
            "body": {
                "contentType": resolved_content_type,
                "content": body or _render_body(artifact, html=resolved_content_type == "html"),
            }
        }
        resolved_subject = _optional(subject) or self.subject
        resolved_importance = _optional(importance) or self.importance
        if resolved_subject:
            graph_payload["subject"] = resolved_subject
        if resolved_importance:
            graph_payload["importance"] = resolved_importance
        return TeamsChannelMessagePayload(resolved_team, resolved_channel, graph_payload, _metadata(artifact))

    def publish(
        self,
        artifact: dict[str, Any] | str,
        *,
        dry_run: bool = True,
        team_id: str | None = None,
        channel_id: str | None = None,
        subject: str | None = None,
        body: str | None = None,
        importance: str | None = None,
        content_type: str | None = None,
    ) -> TeamsChannelMessagePublishResult:
        payload = self.build_message_payload(artifact, team_id=team_id, channel_id=channel_id, subject=subject, body=body, importance=importance, content_type=content_type)
        if dry_run:
            return TeamsChannelMessagePublishResult(None, payload.team_id, payload.channel_id, None, None, True, payload.to_dict())
        if not self.access_token:
            raise TeamsChannelMessagePublishError("Microsoft Graph access_token is required for live Teams channel message publishing")
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.message_endpoint(payload.team_id, payload.channel_id), headers=self._headers(), json=payload.graph_payload, timeout=self.timeout)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise TeamsChannelMessagePublishError(f"Teams channel message publish failed: {exc}") from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise TeamsChannelMessagePublishError(f"Teams channel message publish failed with HTTP {response.status_code}: {_preview(response)}", status_code=response.status_code)
        body_json = _json_response(response)
        return TeamsChannelMessagePublishResult(response.status_code, payload.team_id, payload.channel_id, _optional(body_json.get("id")), _optional(body_json.get("webUrl")), False, payload.to_dict())

    def _headers(self) -> dict[str, str]:
        assert self.access_token is not None
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "max-teams-channel-messages-publisher/1"}

    def _resolve_team_id(self, team_id: str | None = None) -> str:
        return _required(team_id or self.team_id, "Teams team_id is required; pass team_id or set TEAMS_TEAM_ID")

    def _resolve_channel_id(self, channel_id: str | None = None) -> str:
        return _required(channel_id or self.channel_id, "Teams channel_id is required; pass channel_id or set TEAMS_CHANNEL_ID")


TeamsChannelMessagesPublisher = TeamsChannelMessagePublisher


def _render_body(artifact: dict[str, Any] | str, *, html: bool) -> str:
    if isinstance(artifact, str):
        return artifact
    project = _dict(artifact.get("project"))
    brief = _dict(artifact.get("design_brief"))
    title = _text(project.get("title") or brief.get("title") or artifact.get("title") or "Max update")
    summary = _text(project.get("summary") or brief.get("summary") or artifact.get("summary") or "")
    if html:
        return f"<h2>{_escape(title)}</h2><p>{_escape(summary)}</p>"
    return f"{title}\n\n{summary}".strip()


def _metadata(artifact: dict[str, Any] | str) -> dict[str, Any]:
    source = _dict(artifact.get("source")) if isinstance(artifact, dict) else {}
    return {"publisher": "max.teams_channel_messages", "provider": "microsoft_graph", "source_type": source.get("type", "artifact"), "idea_id": source.get("idea_id")}


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _required(value: object, message: str) -> str:
    text = _text(value)
    if not text:
        raise TeamsChannelMessagePublishError(message)
    return text


def _optional(value: object) -> str | None:
    return _text(value) or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    return text if len(text) <= limit else text[:limit] + "..."


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise TeamsChannelMessagePublishError("Teams channel message publish failed: response was not valid JSON", status_code=response.status_code) from exc
    return body if isinstance(body, dict) else {}
