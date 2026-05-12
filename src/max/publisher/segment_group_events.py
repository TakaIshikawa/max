"""Segment group event publisher for Max buildable units."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, redact_text, required_text, required_url, response_json, response_preview
from max.publisher.stripe_customer_notes import _RETRYABLE_STATUS_CODES, _unit_fields

DEFAULT_API_URL = "https://api.segment.io"


class SegmentGroupEventPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, write_key: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[write_key]))
        self.status_code = status_code


@dataclass(frozen=True)
class SegmentGroupEventPayload:
    group_id: str
    user_id: str | None
    traits: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"groupId": self.group_id, "traits": self.traits, "context": {"integration": {"name": "max.segment_group_events", "version": "1"}}}
        if self.user_id:
            data["userId"] = self.user_id
        return {"group": data, "metadata": self.metadata}


@dataclass(frozen=True)
class SegmentGroupEventPublishResult:
    status_code: int | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    authorization: str | None = None
    response: dict[str, Any] | None = None


class SegmentGroupEventPublisher:
    def __init__(
        self,
        *,
        write_key: str | None = None,
        group_id: str | None = None,
        user_id: str | None = None,
        api_url: str = DEFAULT_API_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        self.write_key = optional_text(write_key)
        self.group_id = optional_text(group_id)
        self.user_id = optional_text(user_id)
        self.api_url = required_url(api_url, "Segment api_url must be an absolute http(s) URL")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> SegmentGroupEventPublisher:
        return cls(
            write_key=kwargs.pop("write_key", None) or os.getenv("SEGMENT_WRITE_KEY"),
            group_id=kwargs.pop("group_id", None) or os.getenv("SEGMENT_GROUP_ID"),
            user_id=kwargs.pop("user_id", None) or os.getenv("SEGMENT_USER_ID"),
            api_url=kwargs.pop("api_url", None) or os.getenv("SEGMENT_API_URL", DEFAULT_API_URL),
            **kwargs,
        )

    @property
    def group_endpoint(self) -> str:
        return f"{self.api_url}/v1/group"

    def build_group_payload(self, unit: dict[str, Any]) -> SegmentGroupEventPayload:
        try:
            group_id = required_text(self.group_id, "SEGMENT_GROUP_ID is required for Segment group event publishing")
        except ValueError as exc:
            raise SegmentGroupEventPublishError(str(exc), write_key=self.write_key) from exc
        fields = _unit_fields(unit)
        traits = {
            "max_idea_id": fields["idea_id"],
            "max_title": fields["title"],
            "max_status": fields["status"],
            "max_category": fields["category"],
            "max_problem": fields["problem"],
            "max_solution": fields["solution"],
            "max_score": fields["score"],
            "source": "max",
        }
        metadata = {
            "publisher": "max.segment_group_events",
            "provider": "segment",
            "group_id": group_id,
            "user_id": self.user_id,
            "idea_id": fields["idea_id"],
            "status": fields["status"],
            "category": fields["category"],
            "score": fields["score"],
        }
        return SegmentGroupEventPayload(group_id, self.user_id, traits, metadata)

    def publish(self, unit: dict[str, Any], *, dry_run: bool = True) -> SegmentGroupEventPublishResult:
        payload = self.build_group_payload(unit).to_dict()
        redacted_auth = "Basic [REDACTED]" if self.write_key else None
        if dry_run:
            return SegmentGroupEventPublishResult(None, True, self.group_endpoint, payload, authorization=redacted_auth)
        if not self.write_key:
            raise SegmentGroupEventPublishError("SEGMENT_WRITE_KEY is required for live Segment group event publishing; use dry_run to preview")
        response = self._post_with_retries(payload["group"])
        body = response_json(response, SegmentGroupEventPublishError, "Segment group event publish failed: response was not valid JSON")
        return SegmentGroupEventPublishResult(response.status_code, False, self.group_endpoint, payload, authorization=redacted_auth, response=body)

    def _post_with_retries(self, request_json: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            last_response: httpx.Response | None = None
            for attempt in range(self.max_retries + 1):
                try:
                    response = client.post(self.group_endpoint, json=request_json, headers=self._headers(), timeout=self.timeout)
                except (httpx.RequestError, httpx.TimeoutException) as exc:
                    if attempt >= self.max_retries:
                        raise SegmentGroupEventPublishError(f"Segment group event publish failed for {self.group_endpoint}: {exc}", write_key=self.write_key) from exc
                    continue
                last_response = response
                if response.status_code not in _RETRYABLE_STATUS_CODES or attempt >= self.max_retries:
                    break
            assert last_response is not None
            if not 200 <= last_response.status_code < 300:
                raise SegmentGroupEventPublishError(
                    f"Segment group event publish failed with HTTP {last_response.status_code}: {response_preview(last_response, secrets=[self.write_key])}",
                    status_code=last_response.status_code,
                    write_key=self.write_key,
                )
            return last_response
        finally:
            if close_client:
                client.close()

    def _headers(self) -> dict[str, str]:
        assert self.write_key is not None
        token = base64.b64encode(f"{self.write_key}:".encode()).decode("ascii")
        return {"Authorization": f"Basic {token}", "Content-Type": "application/json", "User-Agent": "max-segment-group-events-publisher/1"}


SegmentGroupEventsPublisher = SegmentGroupEventPublisher
