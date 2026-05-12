"""Gainsight timeline activity publisher for Max buildable units."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, redact_text, required_url, response_json, response_preview
from max.publisher.stripe_customer_notes import _RETRYABLE_STATUS_CODES, _unit_fields

DEFAULT_API_URL = "https://api.gainsight.com"


class GainsightTimelineActivityPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class GainsightTimelineActivityPayload:
    subject: str
    activity_type: str
    body: str
    company_id: str | None
    relationship_id: str | None
    metadata: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {"subject": self.subject, "activity_type": self.activity_type, "body": self.body, "company_id": self.company_id, "relationship_id": self.relationship_id, "metadata": self.metadata}

    def to_request_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"subject": self.subject, "type": self.activity_type, "body": self.body, "metadata": self.metadata}
        if self.company_id:
            payload["companyId"] = self.company_id
        if self.relationship_id:
            payload["relationshipId"] = self.relationship_id
        return payload


@dataclass(frozen=True)
class GainsightTimelineActivityPublishResult:
    status_code: int | None
    activity_id: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]


class GainsightTimelineActivityPublisher:
    def __init__(
        self,
        *,
        token: str | None = None,
        api_url: str = DEFAULT_API_URL,
        company_id: str | None = None,
        relationship_id: str | None = None,
        activity_type: str = "Update",
        subject: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        self.token = optional_text(token)
        self.api_url = required_url(api_url, "Gainsight api_url must be an absolute http(s) URL")
        self.company_id = optional_text(company_id)
        self.relationship_id = optional_text(relationship_id)
        self.activity_type = optional_text(activity_type) or "Update"
        self.subject = optional_text(subject)
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> GainsightTimelineActivityPublisher:
        return cls(
            token=kwargs.pop("token", None) or os.getenv("GAINSIGHT_API_TOKEN"),
            api_url=kwargs.pop("api_url", None) or os.getenv("GAINSIGHT_API_URL", DEFAULT_API_URL),
            company_id=kwargs.pop("company_id", None) or os.getenv("GAINSIGHT_COMPANY_ID"),
            relationship_id=kwargs.pop("relationship_id", None) or os.getenv("GAINSIGHT_RELATIONSHIP_ID"),
            **kwargs,
        )

    @property
    def activities_endpoint(self) -> str:
        return f"{self.api_url}/v1/timeline/activities"

    def build_activity_payload(self, unit: dict[str, Any]) -> GainsightTimelineActivityPayload:
        if not self.company_id and not self.relationship_id:
            raise GainsightTimelineActivityPublishError("Gainsight company_id or relationship_id is required; set GAINSIGHT_COMPANY_ID or GAINSIGHT_RELATIONSHIP_ID", token=self.token)
        fields = _unit_fields(unit)
        execution = unit.get("execution") if isinstance(unit.get("execution"), dict) else {}
        validation_plan = optional_text(execution.get("validation_plan")) or optional_text(unit.get("validation_plan")) or "Not specified"
        metadata = {"publisher": "max.gainsight_timeline_activities", "idea_id": fields["idea_id"], "status": fields["status"], "category": fields["category"], "score": fields["score"]}
        body = "\n".join([f"Problem: {fields['problem']}", f"Solution: {fields['solution']}", f"Validation plan: {validation_plan}", f"Score: {fields['score']}", f"Idea ID: {fields['idea_id']}"])
        return GainsightTimelineActivityPayload(self.subject or fields["title"], self.activity_type, body, self.company_id, self.relationship_id, metadata)

    def publish(self, unit: dict[str, Any], *, dry_run: bool = True) -> GainsightTimelineActivityPublishResult:
        payload = self.build_activity_payload(unit)
        payload_dict = payload.to_dict()
        if dry_run:
            return GainsightTimelineActivityPublishResult(None, None, True, self.activities_endpoint, payload_dict)
        if not self.token:
            raise GainsightTimelineActivityPublishError("GAINSIGHT_API_TOKEN is required for live Gainsight timeline activity publishing; use dry_run to preview")
        response = self._post_with_retries(payload.to_request_json())
        body = response_json(response, GainsightTimelineActivityPublishError, "Gainsight timeline activity publish failed: response was not valid JSON")
        activity = body.get("activity") if isinstance(body.get("activity"), dict) else body
        return GainsightTimelineActivityPublishResult(response.status_code, optional_text(activity.get("id")) if isinstance(activity, dict) else None, False, self.activities_endpoint, payload_dict)

    def _post_with_retries(self, request_json: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response: httpx.Response | None = None
            for attempt in range(self.max_retries + 1):
                response = client.post(self.activities_endpoint, json=request_json, headers=self._headers(), timeout=self.timeout)
                if response.status_code not in _RETRYABLE_STATUS_CODES or attempt >= self.max_retries:
                    break
            assert response is not None
            if not 200 <= response.status_code < 300:
                raise GainsightTimelineActivityPublishError(
                    f"Gainsight timeline activity publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.token])}",
                    status_code=response.status_code,
                    token=self.token,
                )
            return response
        finally:
            if close_client:
                client.close()

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {"Accept": "application/json", "Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "User-Agent": "max-gainsight-timeline-activities-publisher/1"}


GainsightTimelineActivitiesPublisher = GainsightTimelineActivityPublisher
