"""Slack scheduled-message publisher for generated TactSpec previews."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import (
    DEFAULT_TIMEOUT_SECONDS,
    markdown_summary,
    metadata,
    optional_text,
    redact_text,
    required_text,
    required_url,
    response_json,
    response_preview,
    title,
    validate_tact_spec,
)

DEFAULT_API_URL = "https://slack.com/api"


class SlackScheduledMessagePublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class SlackScheduledMessagePublishResult:
    status_code: int | None
    scheduled_message_id: str | None
    channel: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class SlackScheduledMessagePublisher:
    def __init__(
        self,
        *,
        token: str | None = None,
        channel: str | None = None,
        post_at: int | str | None = None,
        api_url: str = DEFAULT_API_URL,
        username: str | None = None,
        icon_emoji: str | None = None,
        blocks: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.token = optional_text(token)
        self.channel = optional_text(channel)
        self.post_at = _post_at_value(post_at)
        self.api_url = required_url(api_url, "Slack api_url must be an absolute http(s) URL")
        self.username = optional_text(username)
        self.icon_emoji = optional_text(icon_emoji)
        self.blocks = list(blocks) if blocks is not None else None
        self.extra_metadata = dict(metadata or {})
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> SlackScheduledMessagePublisher:
        return cls(
            token=kwargs.pop("token", None) or os.getenv("SLACK_BOT_TOKEN"),
            channel=kwargs.pop("channel", None) or os.getenv("SLACK_CHANNEL"),
            post_at=kwargs.pop("post_at", None) or os.getenv("SLACK_SCHEDULED_POST_AT"),
            api_url=kwargs.pop("api_url", None) or os.getenv("SLACK_API_URL", DEFAULT_API_URL),
            **kwargs,
        )

    @property
    def endpoint(self) -> str:
        return f"{self.api_url}/chat.scheduleMessage"

    def build_payload(
        self,
        tact_spec: dict[str, Any],
        *,
        channel: str | None = None,
        post_at: int | str | None = None,
        blocks: list[dict[str, Any]] | None = None,
        metadata_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            validate_tact_spec(tact_spec, label="Slack scheduled message")
            resolved_channel = required_text(
                optional_text(channel) or self.channel,
                "SLACK_CHANNEL is required for Slack scheduled message publishing",
            )
            resolved_post_at = _required_post_at(post_at if post_at is not None else self.post_at)
        except ValueError as exc:
            raise SlackScheduledMessagePublishError(str(exc), token=self.token) from exc

        meta = {
            **metadata(tact_spec, publisher="max.slack_scheduled_messages"),
            **self.extra_metadata,
            **dict(metadata_override or {}),
        }
        text = markdown_summary(tact_spec, meta)
        payload: dict[str, Any] = {
            "channel": resolved_channel,
            "post_at": resolved_post_at,
            "text": text,
            "mrkdwn": True,
            "blocks": blocks
            or self.blocks
            or [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*{title(tact_spec)}*\n{text[:2500]}"},
                }
            ],
            "metadata": {"event_type": "max_scheduled_message", "event_payload": meta},
        }
        if self.username:
            payload["username"] = self.username
        if self.icon_emoji:
            payload["icon_emoji"] = self.icon_emoji
        return payload

    def publish(
        self,
        tact_spec: dict[str, Any],
        *,
        dry_run: bool = True,
        channel: str | None = None,
        post_at: int | str | None = None,
        blocks: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SlackScheduledMessagePublishResult:
        payload = self.build_payload(tact_spec, channel=channel, post_at=post_at, blocks=blocks, metadata_override=metadata)
        if dry_run:
            return SlackScheduledMessagePublishResult(None, None, payload["channel"], True, self.endpoint, payload)
        if not self.token:
            raise SlackScheduledMessagePublishError("SLACK_BOT_TOKEN is required for live Slack scheduled message publishing; use dry_run to preview")
        response = self._post(payload)
        body = response_json(response, SlackScheduledMessagePublishError, "Slack scheduled message publish failed: response was not valid JSON")
        if body.get("ok") is False:
            raise SlackScheduledMessagePublishError(f"Slack scheduled message publish failed: {response_preview(response, secrets=[self.token])}", status_code=response.status_code, token=self.token)
        return SlackScheduledMessagePublishResult(
            response.status_code,
            optional_text(body.get("scheduled_message_id")),
            optional_text(body.get("channel")) or payload["channel"],
            False,
            self.endpoint,
            payload,
            body,
        )

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.endpoint, json=payload, headers=self._headers(), timeout=self.timeout)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise SlackScheduledMessagePublishError(f"Slack scheduled message publish failed for {self.endpoint}: {exc}", token=self.token) from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise SlackScheduledMessagePublishError(f"Slack scheduled message publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.token])}", status_code=response.status_code, token=self.token)
        return response

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "User-Agent": "max-slack-scheduled-messages-publisher/1"}


SlackScheduledMessagesPublisher = SlackScheduledMessagePublisher


def publish_slack_scheduled_message(tact_spec: dict[str, Any], **kwargs: Any) -> SlackScheduledMessagePublishResult:
    dry_run = bool(kwargs.pop("dry_run", True))
    return SlackScheduledMessagePublisher.from_env(**kwargs).publish(tact_spec, dry_run=dry_run)


def _post_at_value(value: object) -> int | None:
    if value is None:
        return None
    try:
        post_at = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise SlackScheduledMessagePublishError("Slack scheduled message post_at must be a Unix timestamp") from exc
    if post_at <= 0:
        raise SlackScheduledMessagePublishError("Slack scheduled message post_at must be greater than zero")
    return post_at


def _required_post_at(value: object) -> int:
    post_at = _post_at_value(value)
    if post_at is None:
        raise ValueError("post_at is required for Slack scheduled message publishing")
    return post_at
