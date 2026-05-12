"""Slack API message publisher for generated TactSpec previews."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, markdown_summary, metadata, optional_text, required_text, required_url, response_json, response_preview, title, validate_tact_spec

DEFAULT_API_URL = "https://slack.com/api"


class SlackMessagePublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class SlackMessagePayload:
    channel: str
    message: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"channel": self.channel, "message": self.message, "metadata": self.metadata}


@dataclass(frozen=True)
class SlackMessagePublishResult:
    status_code: int | None
    channel: str | None
    ts: str | None
    dry_run: bool
    payload: dict[str, Any]


class SlackMessagePublisher:
    def __init__(self, *, bot_token: str | None = None, channel: str | None = None, api_url: str = DEFAULT_API_URL, thread_ts: str | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.bot_token = optional_text(bot_token)
        self.channel = optional_text(channel)
        self.api_url = required_url(api_url, "Slack api_url must be an absolute http(s) URL")
        self.thread_ts = optional_text(thread_ts)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, *, bot_token: str | None = None, channel: str | None = None, api_url: str | None = None, thread_ts: str | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> SlackMessagePublisher:
        return cls(bot_token=bot_token or os.getenv("SLACK_BOT_TOKEN"), channel=channel or os.getenv("SLACK_CHANNEL"), api_url=api_url or os.getenv("SLACK_API_URL", DEFAULT_API_URL), thread_ts=thread_ts or os.getenv("SLACK_THREAD_TS"), timeout=timeout, client=client)

    @property
    def post_message_endpoint(self) -> str:
        return f"{self.api_url}/chat.postMessage"

    def build_message_payload(self, tact_spec: dict[str, Any], *, channel: str | None = None, thread_ts: str | None = None, blocks: list[dict[str, Any]] | None = None, attachments: list[dict[str, Any]] | None = None) -> SlackMessagePayload:
        try:
            validate_tact_spec(tact_spec, label="Slack message")
            resolved_channel = required_text(optional_text(channel) or self.channel, "SLACK_CHANNEL is required for Slack message publishing")
        except ValueError as exc:
            raise SlackMessagePublishError(str(exc)) from exc
        meta = metadata(tact_spec, publisher="max.slack_messages")
        text = markdown_summary(tact_spec, meta)
        message: dict[str, Any] = {
            "channel": resolved_channel,
            "text": text,
            "mrkdwn": True,
            "blocks": blocks
            or [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*{title(tact_spec)}*\n{text[:2500]}"},
                }
            ],
        }
        resolved_thread_ts = optional_text(thread_ts) or self.thread_ts
        if resolved_thread_ts:
            message["thread_ts"] = resolved_thread_ts
        if attachments:
            message["attachments"] = attachments
        return SlackMessagePayload(resolved_channel, message, meta)

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True, channel: str | None = None, thread_ts: str | None = None, blocks: list[dict[str, Any]] | None = None, attachments: list[dict[str, Any]] | None = None) -> SlackMessagePublishResult:
        payload = self.build_message_payload(tact_spec, channel=channel, thread_ts=thread_ts, blocks=blocks, attachments=attachments).to_dict()
        if dry_run:
            return SlackMessagePublishResult(None, payload["channel"], None, True, payload)
        if not self.bot_token:
            raise SlackMessagePublishError("SLACK_BOT_TOKEN is required for live Slack message publishing; use dry_run to preview")
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.post_message_endpoint, json=payload["message"], headers={"Authorization": f"Bearer {self.bot_token}", "Content-Type": "application/json", "User-Agent": "max-slack-messages-publisher/1"}, timeout=self.timeout)
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise SlackMessagePublishError(f"Slack message publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.bot_token])}", status_code=response.status_code)
        body = response_json(response, SlackMessagePublishError, "Slack message publish failed: response was not valid JSON")
        if body.get("ok") is False:
            raise SlackMessagePublishError(f"Slack message publish failed: {response_preview(response, secrets=[self.bot_token])}", status_code=response.status_code)
        return SlackMessagePublishResult(response.status_code, optional_text(body.get("channel")), optional_text(body.get("ts")), False, payload)


SlackMessagesPublisher = SlackMessagePublisher


def publish_slack_message(tact_spec: dict[str, Any], **kwargs: Any) -> SlackMessagePublishResult:
    dry_run = bool(kwargs.pop("dry_run", True))
    return SlackMessagePublisher.from_env(**kwargs).publish(tact_spec, dry_run=dry_run)
