"""Gainsight timeline activity publisher for Max buildable units."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, redact_text, required_text, required_url, response_json, response_preview
from max.publisher.stripe_customer_notes import _RETRYABLE_STATUS_CODES, _unit_fields

DEFAULT_API_URL = "https://api.gainsight.com"
DEFAULT_ACTIVITY_TYPE = "Update"


class GainsightTimelineActivityPublishError(RuntimeError):
    """Raised when a Gainsight timeline activity publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class GainsightTimelineActivityPayload:
    target_type: str
    target_id: str
    activity_type: str
    subject: str
    body: dict[str, Any]
    metadata: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_type": self.target_type,
            "target_id": self.target_id,
            "activity_type": self.activity_type,
            "subject": self.subject,
            "body": self.body,
            "metadata": self.metadata,
        }

    def to_request_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.activity_type,
            "subject": self.subject,
            "body": self.body,
            "metadata": self.metadata,
        }
        if self.target_type == "company":
            payload["companyId"] = self.target_id
        else:
            payload["relationshipId"] = self.target_id
        return payload


@dataclass(frozen=True)
class GainsightTimelineActivityPublishResult:
    status_code: int | None
    activity_id: str | None
    target_type: str
    target_id: str
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class GainsightTimelineActivityPublisher:
    """Build and optionally create a Gainsight timeline activity from Max context."""

    def __init__(
        self,
        *,
        token: str | None = None,
        api_url: str = DEFAULT_API_URL,
        company_id: str | None = None,
        relationship_id: str | None = None,
        activity_type: str = DEFAULT_ACTIVITY_TYPE,
        subject: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        self.token = optional_text(token)
        self.api_url = required_url(api_url, "Gainsight api_url must be an absolute http(s) URL")
        self.company_id = optional_text(company_id)
        self.relationship_id = optional_text(relationship_id)
        self.activity_type = optional_text(activity_type) or DEFAULT_ACTIVITY_TYPE
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
            activity_type=kwargs.pop("activity_type", None) or os.getenv("GAINSIGHT_ACTIVITY_TYPE", DEFAULT_ACTIVITY_TYPE),
            subject=kwargs.pop("subject", None) or os.getenv("GAINSIGHT_ACTIVITY_SUBJECT"),
            **kwargs,
        )

    @property
    def activities_endpoint(self) -> str:
        return f"{self.api_url}/v1/timeline/activities"

    def build_activity_payload(
        self,
        unit: dict[str, Any],
        *,
        company_id: str | None = None,
        relationship_id: str | None = None,
        subject: str | None = None,
    ) -> GainsightTimelineActivityPayload:
        target_type, target_id = self._resolve_target(company_id=company_id, relationship_id=relationship_id)
        fields = _unit_fields(unit)
        validation_plan = _validation_plan(unit)
        activity_subject = optional_text(subject) or self.subject or f"Max idea: {fields['title']}"
        metadata = {
            "publisher": "max.gainsight_timeline_activities",
            "idea_id": fields["idea_id"],
            "status": fields["status"],
            "category": fields["category"],
            "score": fields["score"],
            "target_type": target_type,
            "target_id": target_id,
        }
        body = {
            "title": fields["title"],
            "category": fields["category"],
            "problem": fields["problem"],
            "solution": fields["solution"],
            "validation_plan": validation_plan,
            "score": fields["score"],
            "metadata": metadata,
        }
        return GainsightTimelineActivityPayload(target_type, target_id, self.activity_type, activity_subject, body, metadata)

    def publish(
        self,
        unit: dict[str, Any],
        *,
        dry_run: bool = True,
        company_id: str | None = None,
        relationship_id: str | None = None,
        subject: str | None = None,
    ) -> GainsightTimelineActivityPublishResult:
        payload = self.build_activity_payload(unit, company_id=company_id, relationship_id=relationship_id, subject=subject)
        payload_dict = payload.to_dict()
        if dry_run:
            return GainsightTimelineActivityPublishResult(None, None, payload.target_type, payload.target_id, True, self.activities_endpoint, payload_dict)
        if not self.token:
            raise GainsightTimelineActivityPublishError("GAINSIGHT_API_TOKEN is required for live Gainsight timeline activity publishing; use dry_run to preview")

        response = self._post_with_retries(payload.to_request_json())
        body = response_json(response, GainsightTimelineActivityPublishError, "Gainsight timeline activity publish failed: response was not valid JSON")
        return GainsightTimelineActivityPublishResult(
            response.status_code,
            _activity_id(body),
            payload.target_type,
            payload.target_id,
            False,
            self.activities_endpoint,
            payload_dict,
            body,
        )

    def _resolve_target(self, *, company_id: str | None = None, relationship_id: str | None = None) -> tuple[str, str]:
        resolved_company_id = optional_text(company_id) or self.company_id
        resolved_relationship_id = optional_text(relationship_id) or self.relationship_id
        if resolved_company_id and resolved_relationship_id:
            raise GainsightTimelineActivityPublishError("Gainsight timeline activity publishing requires exactly one target: company_id or relationship_id")
        if resolved_company_id:
            return "company", resolved_company_id
        if resolved_relationship_id:
            return "relationship", resolved_relationship_id
        try:
            required_text(None, "Gainsight timeline activity publishing requires company_id or relationship_id; set GAINSIGHT_COMPANY_ID or GAINSIGHT_RELATIONSHIP_ID")
        except ValueError as exc:
            raise GainsightTimelineActivityPublishError(str(exc), token=self.token) from exc
        raise AssertionError("unreachable")

    def _post_with_retries(self, request_json: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response: httpx.Response | None = None
            for attempt in range(self.max_retries + 1):
                try:
                    response = client.post(self.activities_endpoint, json=request_json, headers=self._headers(), timeout=self.timeout)
                except (httpx.RequestError, httpx.TimeoutException) as exc:
                    if attempt >= self.max_retries:
                        raise GainsightTimelineActivityPublishError(f"Gainsight timeline activity publish failed for {self.activities_endpoint}: {exc}", token=self.token) from exc
                    continue
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


def _validation_plan(unit: dict[str, Any]) -> str:
    execution = unit.get("execution") if isinstance(unit.get("execution"), dict) else {}
    return optional_text(execution.get("validation_plan")) or optional_text(unit.get("validation_plan")) or "Not specified"


def _activity_id(body: dict[str, Any]) -> str | None:
    data = body.get("data")
    if isinstance(data, dict):
        return optional_text(data.get("id")) or optional_text(data.get("activityId"))
    activity = body.get("activity")
    if isinstance(activity, dict):
        return optional_text(activity.get("id")) or optional_text(activity.get("activityId"))
    return optional_text(body.get("id")) or optional_text(body.get("activityId"))
