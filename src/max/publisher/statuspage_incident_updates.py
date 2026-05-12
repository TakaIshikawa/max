"""Statuspage incident update publisher for Max TactSpecs and design briefs."""

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


DEFAULT_API_URL = "https://api.statuspage.io"
DEFAULT_INCIDENT_STATUS = "investigating"


class StatuspageIncidentUpdatePublishError(RuntimeError):
    """Raised when a Statuspage incident update publish cannot be completed."""

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
class StatuspageIncidentUpdatePayload:
    """Statuspage incident update payload plus Max-specific metadata."""

    page_id: str
    incident_id: str
    body: str
    status: str
    deliver_notifications: bool | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "incident_id": self.incident_id,
            "body": self.body,
            "status": self.status,
            "deliver_notifications": self.deliver_notifications,
            "metadata": self.metadata,
        }

    def to_request(self) -> dict[str, Any]:
        update: dict[str, Any] = {"body": self.body, "status": self.status}
        if self.deliver_notifications is not None:
            update["deliver_notifications"] = self.deliver_notifications
        return {"incident_update": update}


@dataclass(frozen=True)
class StatuspageIncidentUpdatePublishResult:
    """Summary of a Statuspage incident update publish or dry run."""

    status_code: int | None
    page_id: str
    incident_id: str
    update_id: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class StatuspageIncidentUpdatePublisher:
    """Build and optionally post updates to existing Statuspage incidents."""

    def __init__(
        self,
        *,
        page_id: str | None = None,
        incident_id: str | None = None,
        api_key: str | None = None,
        api_url: str = DEFAULT_API_URL,
        status: str = DEFAULT_INCIDENT_STATUS,
        body: str | None = None,
        deliver_notifications: bool | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        self.page_id = optional_text(page_id)
        self.incident_id = optional_text(incident_id)
        self.api_key = optional_text(api_key)
        self.api_url = required_url(api_url, "Statuspage api_url must be an absolute http(s) URL")
        self.status = optional_text(status) or DEFAULT_INCIDENT_STATUS
        self.body = optional_text(body)
        self.deliver_notifications = deliver_notifications
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        page_id: str | None = None,
        incident_id: str | None = None,
        api_key: str | None = None,
        api_url: str | None = None,
        status: str | None = None,
        body: str | None = None,
        deliver_notifications: bool | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> StatuspageIncidentUpdatePublisher:
        return cls(
            page_id=page_id or os.getenv("STATUSPAGE_PAGE_ID"),
            incident_id=incident_id or os.getenv("STATUSPAGE_INCIDENT_ID"),
            api_key=api_key or os.getenv("STATUSPAGE_API_KEY"),
            api_url=api_url or os.getenv("STATUSPAGE_API_URL", DEFAULT_API_URL),
            status=status or os.getenv("STATUSPAGE_INCIDENT_STATUS") or os.getenv("STATUSPAGE_STATUS") or DEFAULT_INCIDENT_STATUS,
            body=body,
            deliver_notifications=(
                deliver_notifications
                if deliver_notifications is not None
                else _env_bool("STATUSPAGE_DELIVER_NOTIFICATIONS")
            ),
            timeout=timeout,
            max_retries=max_retries,
            client=client,
        )

    def incident_updates_endpoint(
        self,
        *,
        page_id: str | None = None,
        incident_id: str | None = None,
    ) -> str:
        resolved_page_id = _required_page_id(optional_text(page_id) or self.page_id)
        resolved_incident_id = _required_incident_id(optional_text(incident_id) or self.incident_id)
        return (
            f"{self.api_url}/v1/pages/{quote_path(resolved_page_id)}/incidents/"
            f"{quote_path(resolved_incident_id)}/incident_updates"
        )

    def build_update_payload(
        self,
        tact_spec: dict[str, Any],
        *,
        page_id: str | None = None,
        incident_id: str | None = None,
        body: str | None = None,
        status: str | None = None,
        deliver_notifications: bool | None = None,
    ) -> StatuspageIncidentUpdatePayload:
        try:
            validate_tact_spec(tact_spec, label="Statuspage incident update")
            resolved_page_id = _required_page_id(optional_text(page_id) or self.page_id)
            resolved_incident_id = _required_incident_id(optional_text(incident_id) or self.incident_id)
        except ValueError as exc:
            raise StatuspageIncidentUpdatePublishError(str(exc), secrets=self._secrets()) from exc

        update_metadata = metadata(
            tact_spec,
            publisher="max.statuspage_incident_updates",
            extra={"statuspage_page_id": resolved_page_id, "statuspage_incident_id": resolved_incident_id},
        )
        update_body = optional_text(body) or self.body or markdown_summary(tact_spec, update_metadata)
        return StatuspageIncidentUpdatePayload(
            page_id=resolved_page_id,
            incident_id=resolved_incident_id,
            body=update_body,
            status=optional_text(status) or self.status,
            deliver_notifications=(
                self.deliver_notifications
                if deliver_notifications is None
                else deliver_notifications
            ),
            metadata=update_metadata,
        )

    def build_design_brief_update_payload(
        self,
        design_brief: dict[str, Any],
        *,
        markdown: str | None = None,
        page_id: str | None = None,
        incident_id: str | None = None,
        body: str | None = None,
        status: str | None = None,
        deliver_notifications: bool | None = None,
    ) -> StatuspageIncidentUpdatePayload:
        return self.build_update_payload(
            _design_brief_tact_spec(design_brief, markdown=markdown),
            page_id=page_id,
            incident_id=incident_id,
            body=body,
            status=status,
            deliver_notifications=deliver_notifications,
        )

    def publish(
        self,
        tact_spec: dict[str, Any],
        *,
        dry_run: bool = True,
        page_id: str | None = None,
        incident_id: str | None = None,
        body: str | None = None,
        status: str | None = None,
        deliver_notifications: bool | None = None,
    ) -> StatuspageIncidentUpdatePublishResult:
        payload = self.build_update_payload(
            tact_spec,
            page_id=page_id,
            incident_id=incident_id,
            body=body,
            status=status,
            deliver_notifications=deliver_notifications,
        )
        return self._publish_payload(payload, dry_run=dry_run)

    def publish_design_brief(
        self,
        design_brief: dict[str, Any],
        *,
        markdown: str | None = None,
        dry_run: bool = True,
        page_id: str | None = None,
        incident_id: str | None = None,
        body: str | None = None,
        status: str | None = None,
        deliver_notifications: bool | None = None,
    ) -> StatuspageIncidentUpdatePublishResult:
        payload = self.build_design_brief_update_payload(
            design_brief,
            markdown=markdown,
            page_id=page_id,
            incident_id=incident_id,
            body=body,
            status=status,
            deliver_notifications=deliver_notifications,
        )
        return self._publish_payload(payload, dry_run=dry_run)

    def _publish_payload(
        self,
        payload: StatuspageIncidentUpdatePayload,
        *,
        dry_run: bool,
    ) -> StatuspageIncidentUpdatePublishResult:
        endpoint = self.incident_updates_endpoint(
            page_id=payload.page_id,
            incident_id=payload.incident_id,
        )
        payload_dict = payload.to_dict()
        if dry_run:
            return StatuspageIncidentUpdatePublishResult(
                None,
                payload.page_id,
                payload.incident_id,
                None,
                True,
                endpoint,
                payload_dict,
            )

        if not self.api_key:
            raise StatuspageIncidentUpdatePublishError(
                "STATUSPAGE_API_KEY is required for live Statuspage incident update publishing; "
                "use dry_run to preview",
                secrets=self._secrets(),
            )
        response = self._post_with_retries(endpoint, payload.to_request())
        response_body = response_json(
            response,
            StatuspageIncidentUpdatePublishError,
            "Statuspage incident update publish failed: response was not valid JSON",
        )
        update = (
            response_body.get("incident_update")
            if isinstance(response_body.get("incident_update"), dict)
            else response_body
        )
        update_id = optional_text(update.get("id")) if isinstance(update, dict) else None
        return StatuspageIncidentUpdatePublishResult(
            response.status_code,
            payload.page_id,
            payload.incident_id,
            update_id,
            False,
            endpoint,
            payload_dict,
            response_body,
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
                        raise StatuspageIncidentUpdatePublishError(
                            f"Statuspage incident update publish failed for {endpoint}: {exc}",
                            secrets=self._secrets(),
                        ) from exc
                    continue
                if response.status_code not in {429, 500, 502, 503, 504} or attempt >= self.max_retries:
                    break
            assert response is not None
            if not 200 <= response.status_code < 300:
                raise StatuspageIncidentUpdatePublishError(
                    "Statuspage incident update publish failed with HTTP "
                    f"{response.status_code}: {response_preview(response, secrets=self._secrets())}",
                    status_code=response.status_code,
                    secrets=self._secrets(),
                )
            return response
        finally:
            if close_client:
                client.close()

    def _headers(self) -> dict[str, str]:
        assert self.api_key is not None
        return {
            "Accept": "application/json",
            "Authorization": f"OAuth {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "max-statuspage-incident-updates-publisher/1",
        }

    def _secrets(self) -> list[str | None]:
        return [self.api_key]


StatuspageIncidentUpdatesPublisher = StatuspageIncidentUpdatePublisher


def _required_page_id(value: str | None) -> str:
    return required_text(value, "Statuspage page_id is required; pass page_id or set STATUSPAGE_PAGE_ID")


def _required_incident_id(value: str | None) -> str:
    return required_text(
        value,
        "Statuspage incident_id is required; pass incident_id or set STATUSPAGE_INCIDENT_ID",
    )


def _env_bool(name: str) -> bool | None:
    value = optional_text(os.getenv(name))
    if value is None:
        return None
    return value.lower() in {"1", "true", "yes", "y", "on"}


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
