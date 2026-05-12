"""Segment track event publisher for generated TactSpec previews."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, dict_value, metadata, optional_text, required_text, required_url, response_preview, title, validate_tact_spec

DEFAULT_API_URL = "https://api.segment.io"
DEFAULT_EVENT_NAME = "TactSpec Published"


class SegmentTrackEventPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class SegmentTrackEventPayload:
    event: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"event": self.event, "metadata": self.metadata}


@dataclass(frozen=True)
class SegmentTrackEventPublishResult:
    status_code: int | None
    dry_run: bool
    payload: dict[str, Any]


class SegmentTrackEventPublisher:
    def __init__(self, *, write_key: str | None = None, user_id: str | None = None, anonymous_id: str | None = None, api_url: str = DEFAULT_API_URL, event_name: str = DEFAULT_EVENT_NAME, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.write_key = optional_text(write_key)
        self.user_id = optional_text(user_id)
        self.anonymous_id = optional_text(anonymous_id)
        self.api_url = required_url(api_url, "Segment api_url must be an absolute http(s) URL")
        self.event_name = optional_text(event_name) or DEFAULT_EVENT_NAME
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, *, write_key: str | None = None, user_id: str | None = None, anonymous_id: str | None = None, api_url: str | None = None, event_name: str | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> SegmentTrackEventPublisher:
        return cls(write_key=write_key or os.getenv("SEGMENT_WRITE_KEY"), user_id=user_id or os.getenv("SEGMENT_USER_ID"), anonymous_id=anonymous_id or os.getenv("SEGMENT_ANONYMOUS_ID"), api_url=api_url or os.getenv("SEGMENT_API_URL", DEFAULT_API_URL), event_name=event_name or os.getenv("SEGMENT_EVENT_NAME", DEFAULT_EVENT_NAME), timeout=timeout, client=client)

    @property
    def track_endpoint(self) -> str:
        return f"{self.api_url}/v1/track"

    def build_track_payload(self, tact_spec: dict[str, Any]) -> SegmentTrackEventPayload:
        try:
            validate_tact_spec(tact_spec, label="Segment track event")
            if not self.user_id and not self.anonymous_id:
                raise ValueError("SEGMENT_USER_ID or SEGMENT_ANONYMOUS_ID is required for Segment track event publishing")
        except ValueError as exc:
            raise SegmentTrackEventPublishError(str(exc)) from exc
        meta = metadata(tact_spec, publisher="max.segment_track_events")
        event: dict[str, Any] = {"event": self.event_name, "properties": _properties(tact_spec), "context": {"integration": {"name": "max.segment_track_events", "version": "1"}}}
        if self.user_id:
            event["userId"] = self.user_id
        if self.anonymous_id:
            event["anonymousId"] = self.anonymous_id
        return SegmentTrackEventPayload(event, meta)

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True) -> SegmentTrackEventPublishResult:
        payload = self.build_track_payload(tact_spec).to_dict()
        if dry_run:
            return SegmentTrackEventPublishResult(None, True, payload)
        if not self.write_key:
            raise SegmentTrackEventPublishError("SEGMENT_WRITE_KEY is required for live Segment track event publishing; use dry_run to preview")
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.track_endpoint, json=payload["event"], headers=self._headers(), timeout=self.timeout)
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise SegmentTrackEventPublishError(f"Segment track event publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.write_key])}", status_code=response.status_code)
        return SegmentTrackEventPublishResult(response.status_code, False, payload)

    def _headers(self) -> dict[str, str]:
        assert self.write_key is not None
        token = base64.b64encode(f"{self.write_key}:".encode()).decode("ascii")
        return {"Authorization": f"Basic {token}", "Content-Type": "application/json", "User-Agent": "max-segment-track-events-publisher/1"}


SegmentTrackEventsPublisher = SegmentTrackEventPublisher


def _properties(tact_spec: dict[str, Any]) -> dict[str, Any]:
    source = dict_value(tact_spec, "source")
    project = dict_value(tact_spec, "project")
    quality = dict_value(tact_spec, "quality")
    evaluation = dict_value(tact_spec, "evaluation")
    return {"title": title(tact_spec), "summary": project.get("summary"), "source": source, "quality": quality, "evaluation": evaluation}
