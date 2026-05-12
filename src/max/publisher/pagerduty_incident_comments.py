"""PagerDuty incident note publisher for Max TactSpecs and design briefs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import (
    DEFAULT_TIMEOUT_SECONDS,
    dict_value,
    markdown_summary,
    metadata,
    optional_text,
    quote_path,
    redact_text,
    required_text,
    required_url,
    response_json,
    response_preview,
    validate_tact_spec,
)


DEFAULT_API_URL = "https://api.pagerduty.com"


class PagerDutyIncidentCommentPublishError(RuntimeError):
    """Raised when a PagerDuty incident comment publish cannot be completed."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        secrets: list[str | None] | None = None,
    ) -> None:
        super().__init__(redact_text(message, secrets=secrets))
        self.status_code = status_code


@dataclass(frozen=True)
class PagerDutyIncidentCommentPayload:
    """PagerDuty incident note payload plus Max-specific metadata."""

    incident_id: str
    content: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "content": self.content,
            "metadata": self.metadata,
        }

    def to_request(self) -> dict[str, Any]:
        return {"note": {"content": self.content}}


@dataclass(frozen=True)
class PagerDutyIncidentCommentPublishResult:
    """Summary of a PagerDuty incident comment publish or dry run."""

    status_code: int | None
    incident_id: str
    note_id: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class PagerDutyIncidentCommentPublisher:
    """Build and optionally append notes to existing PagerDuty incidents."""

    def __init__(
        self,
        *,
        incident_id: str | None = None,
        api_token: str | None = None,
        from_email: str | None = None,
        api_url: str = DEFAULT_API_URL,
        note_body: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        self.incident_id = optional_text(incident_id)
        self.api_token = optional_text(api_token)
        self.from_email = optional_text(from_email)
        self.api_url = required_url(api_url, "PagerDuty api_url must be an absolute http(s) URL")
        self.note_body = optional_text(note_body)
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        incident_id: str | None = None,
        api_token: str | None = None,
        from_email: str | None = None,
        api_url: str | None = None,
        note_body: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> PagerDutyIncidentCommentPublisher:
        return cls(
            incident_id=incident_id or os.getenv("PAGERDUTY_INCIDENT_ID"),
            api_token=api_token or os.getenv("PAGERDUTY_API_TOKEN"),
            from_email=from_email or os.getenv("PAGERDUTY_FROM_EMAIL"),
            api_url=api_url or os.getenv("PAGERDUTY_API_URL", DEFAULT_API_URL),
            note_body=note_body,
            timeout=timeout,
            max_retries=max_retries,
            client=client,
        )

    def notes_endpoint(self, incident_id: str | None = None) -> str:
        resolved = _required_incident_id(optional_text(incident_id) or self.incident_id)
        return f"{self.api_url}/incidents/{quote_path(resolved)}/notes"

    def build_comment_payload(
        self,
        tact_spec: dict[str, Any],
        *,
        incident_id: str | None = None,
        note_body: str | None = None,
    ) -> PagerDutyIncidentCommentPayload:
        try:
            validate_tact_spec(tact_spec, label="PagerDuty incident comment")
            resolved_incident_id = _required_incident_id(
                optional_text(incident_id) or self.incident_id
            )
        except ValueError as exc:
            raise PagerDutyIncidentCommentPublishError(str(exc), secrets=self._secrets()) from exc

        comment_metadata = metadata(
            tact_spec,
            publisher="max.pagerduty_incident_comments",
            extra={"pagerduty_incident_id": resolved_incident_id},
        )
        content = optional_text(note_body) or self.note_body or markdown_summary(
            tact_spec,
            comment_metadata,
        )
        return PagerDutyIncidentCommentPayload(
            incident_id=resolved_incident_id,
            content=content,
            metadata=comment_metadata,
        )

    def build_design_brief_comment_payload(
        self,
        design_brief: dict[str, Any],
        *,
        markdown: str | None = None,
        incident_id: str | None = None,
        note_body: str | None = None,
    ) -> PagerDutyIncidentCommentPayload:
        return self.build_comment_payload(
            _design_brief_tact_spec(design_brief, markdown=markdown),
            incident_id=incident_id,
            note_body=note_body,
        )

    def publish(
        self,
        tact_spec: dict[str, Any],
        *,
        dry_run: bool = True,
        incident_id: str | None = None,
        note_body: str | None = None,
    ) -> PagerDutyIncidentCommentPublishResult:
        payload = self.build_comment_payload(
            tact_spec,
            incident_id=incident_id,
            note_body=note_body,
        )
        return self._publish_payload(payload, dry_run=dry_run)

    def publish_design_brief(
        self,
        design_brief: dict[str, Any],
        *,
        markdown: str | None = None,
        dry_run: bool = True,
        incident_id: str | None = None,
        note_body: str | None = None,
    ) -> PagerDutyIncidentCommentPublishResult:
        payload = self.build_design_brief_comment_payload(
            design_brief,
            markdown=markdown,
            incident_id=incident_id,
            note_body=note_body,
        )
        return self._publish_payload(payload, dry_run=dry_run)

    def _publish_payload(
        self,
        payload: PagerDutyIncidentCommentPayload,
        *,
        dry_run: bool,
    ) -> PagerDutyIncidentCommentPublishResult:
        endpoint = self.notes_endpoint(payload.incident_id)
        payload_dict = payload.to_dict()
        if dry_run:
            return PagerDutyIncidentCommentPublishResult(
                None,
                payload.incident_id,
                None,
                True,
                endpoint,
                payload_dict,
            )

        self._validate_live_auth()
        response = self._post_with_retries(endpoint, payload.to_request())
        body = response_json(
            response,
            PagerDutyIncidentCommentPublishError,
            "PagerDuty incident comment publish failed: response was not valid JSON",
        )
        note = body.get("note") if isinstance(body.get("note"), dict) else body
        note_id = optional_text(note.get("id")) if isinstance(note, dict) else None
        return PagerDutyIncidentCommentPublishResult(
            response.status_code,
            payload.incident_id,
            note_id,
            False,
            endpoint,
            payload_dict,
            body,
        )

    def _post_with_retries(self, endpoint: str, request_json: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response: httpx.Response | None = None
            for attempt in range(self.max_retries + 1):
                try:
                    response = client.post(
                        endpoint,
                        json=request_json,
                        headers=self._headers(),
                        timeout=self.timeout,
                    )
                except (httpx.RequestError, httpx.TimeoutException) as exc:
                    if attempt >= self.max_retries:
                        raise PagerDutyIncidentCommentPublishError(
                            f"PagerDuty incident comment publish failed for {endpoint}: {exc}",
                            secrets=self._secrets(),
                        ) from exc
                    continue
                if response.status_code not in {429, 500, 502, 503, 504} or attempt >= self.max_retries:
                    break
            assert response is not None
            if not 200 <= response.status_code < 300:
                raise PagerDutyIncidentCommentPublishError(
                    "PagerDuty incident comment publish failed with HTTP "
                    f"{response.status_code}: {response_preview(response, secrets=self._secrets())}",
                    status_code=response.status_code,
                    secrets=self._secrets(),
                )
            return response
        finally:
            if close_client:
                client.close()

    def _headers(self) -> dict[str, str]:
        assert self.api_token is not None
        assert self.from_email is not None
        return {
            "Accept": "application/vnd.pagerduty+json;version=2",
            "Authorization": f"Token token={self.api_token}",
            "Content-Type": "application/json",
            "From": self.from_email,
            "User-Agent": "max-pagerduty-incident-comments-publisher/1",
        }

    def _validate_live_auth(self) -> None:
        if not self.api_token:
            raise PagerDutyIncidentCommentPublishError(
                "PAGERDUTY_API_TOKEN is required for live PagerDuty incident comment publishing; "
                "use dry_run to preview",
                secrets=self._secrets(),
            )
        if not self.from_email:
            raise PagerDutyIncidentCommentPublishError(
                "PAGERDUTY_FROM_EMAIL is required for live PagerDuty incident comment publishing; "
                "use dry_run to preview",
                secrets=self._secrets(),
            )

    def _secrets(self) -> list[str | None]:
        return [self.api_token]


PagerDutyIncidentCommentsPublisher = PagerDutyIncidentCommentPublisher


def _required_incident_id(value: str | None) -> str:
    return required_text(
        value,
        "PagerDuty incident_id is required; pass incident_id or set PAGERDUTY_INCIDENT_ID",
    )


def _design_brief_tact_spec(packet: dict[str, Any], *, markdown: str | None = None) -> dict[str, Any]:
    brief = dict_value(packet, "design_brief") or packet
    brief_id = optional_text(brief.get("id"))
    source_ids = _string_list(brief.get("source_idea_ids"))
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "design_brief",
            "design_brief_id": brief_id,
            "idea_id": optional_text(brief.get("lead_idea_id")) or (source_ids[0] if source_ids else None),
            "status": brief.get("design_status") or brief.get("status"),
            "domain": brief.get("domain"),
            "category": brief.get("theme"),
        },
        "project": {
            "title": brief.get("title") or brief_id,
            "summary": brief.get("summary")
            or brief.get("merged_product_concept")
            or brief.get("synthesis_rationale")
            or markdown,
        },
        "problem": {"statement": brief.get("problem")},
        "solution": {"approach": brief.get("solution") or brief.get("merged_product_concept")},
        "execution": {"validation_plan": brief.get("validation_plan")},
        "evidence": {"source_idea_ids": source_ids},
        "quality": {"quality_score": brief.get("quality_score")},
        "evaluation": {
            "overall_score": brief.get("readiness_score"),
            "recommendation": brief.get("recommendation") or brief.get("status_recommendation"),
        },
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
