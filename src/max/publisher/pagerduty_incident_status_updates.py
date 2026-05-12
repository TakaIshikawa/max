"""PagerDuty incident status update publisher."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import quote_path, redact_text, required_url


DEFAULT_API_URL = "https://api.pagerduty.com"
DEFAULT_TIMEOUT_SECONDS = 10.0
VALID_STATUSES = {"triggered", "acknowledged", "resolved"}


class PagerDutyIncidentStatusUpdatePublishError(RuntimeError):
    """Raised when a PagerDuty incident status update cannot be completed."""

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
class PagerDutyIncidentStatusUpdatePayload:
    """PagerDuty incident status update payload."""

    incident_id: str
    status: str
    resolution_note: str | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "incident_id": self.incident_id,
            "status": self.status,
            "resolution_note": self.resolution_note,
            "metadata": self.metadata,
        }
        return payload

    def to_request(self) -> dict[str, Any]:
        incident: dict[str, Any] = {"type": "incident", "status": self.status}
        if self.resolution_note:
            incident["resolution"] = self.resolution_note
        return {"incident": incident}


@dataclass(frozen=True)
class PagerDutyIncidentStatusUpdatePublishResult:
    """Summary of a PagerDuty incident status update publish or dry run."""

    status_code: int | None
    incident_id: str
    status: str
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class PagerDutyIncidentStatusUpdatePublisher:
    """Build and optionally update PagerDuty incident status."""

    def __init__(
        self,
        *,
        incident_id: str | None = None,
        status: str | None = None,
        api_token: str | None = None,
        from_email: str | None = None,
        api_url: str = DEFAULT_API_URL,
        resolution_note: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.incident_id = _optional_text(incident_id)
        self.status = _optional_text(status)
        self.api_token = _optional_text(api_token)
        self.from_email = _optional_text(from_email)
        self.api_url = required_url(api_url, "PagerDuty api_url must be an absolute http(s) URL")
        self.resolution_note = _optional_text(resolution_note)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        incident_id: str | None = None,
        status: str | None = None,
        api_token: str | None = None,
        from_email: str | None = None,
        api_url: str | None = None,
        resolution_note: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> PagerDutyIncidentStatusUpdatePublisher:
        return cls(
            incident_id=incident_id or os.getenv("PAGERDUTY_INCIDENT_ID"),
            status=status or os.getenv("PAGERDUTY_INCIDENT_STATUS"),
            api_token=api_token or os.getenv("PAGERDUTY_API_TOKEN"),
            from_email=from_email or os.getenv("PAGERDUTY_FROM_EMAIL"),
            api_url=api_url or os.getenv("PAGERDUTY_API_URL", DEFAULT_API_URL),
            resolution_note=resolution_note or os.getenv("PAGERDUTY_RESOLUTION_NOTE"),
            timeout=timeout,
            client=client,
        )

    def incident_endpoint(self, incident_id: str | None = None) -> str:
        resolved = _required_text(
            incident_id or self.incident_id,
            "PagerDuty incident_id is required; pass incident_id or set PAGERDUTY_INCIDENT_ID",
        )
        return f"{self.api_url}/incidents/{quote_path(resolved)}"

    def build_status_update_payload(
        self,
        *,
        incident_id: str | None = None,
        status: str | None = None,
        resolution_note: str | None = None,
    ) -> PagerDutyIncidentStatusUpdatePayload:
        resolved_incident_id = _required_text(
            incident_id or self.incident_id,
            "PagerDuty incident_id is required; pass incident_id or set PAGERDUTY_INCIDENT_ID",
        )
        resolved_status = _status_value(status or self.status)
        note = _optional_text(resolution_note) or self.resolution_note
        return PagerDutyIncidentStatusUpdatePayload(
            incident_id=resolved_incident_id,
            status=resolved_status,
            resolution_note=note,
            metadata={
                "publisher": "max.pagerduty_incident_status_updates",
                "pagerduty_incident_id": resolved_incident_id,
                "target_status": resolved_status,
            },
        )

    def publish(
        self,
        *,
        incident_id: str | None = None,
        status: str | None = None,
        resolution_note: str | None = None,
        dry_run: bool = True,
    ) -> PagerDutyIncidentStatusUpdatePublishResult:
        payload_obj = self.build_status_update_payload(
            incident_id=incident_id,
            status=status,
            resolution_note=resolution_note,
        )
        endpoint = self.incident_endpoint(payload_obj.incident_id)
        payload = payload_obj.to_dict()
        if dry_run:
            return PagerDutyIncidentStatusUpdatePublishResult(
                None,
                payload_obj.incident_id,
                payload_obj.status,
                True,
                endpoint,
                payload,
            )
        self._validate_live_auth()

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.put(
                    endpoint,
                    json=payload_obj.to_request(),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise PagerDutyIncidentStatusUpdatePublishError(
                    f"PagerDuty incident status update failed for {endpoint}: {exc}",
                    secrets=self._secrets(),
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise PagerDutyIncidentStatusUpdatePublishError(
                f"PagerDuty incident status update failed with HTTP {response.status_code}: {_response_body_preview(response, secrets=self._secrets())}",
                status_code=response.status_code,
                secrets=self._secrets(),
            )
        response_body = _json_response(response, secrets=self._secrets())
        incident = response_body.get("incident") if isinstance(response_body.get("incident"), dict) else {}
        return PagerDutyIncidentStatusUpdatePublishResult(
            response.status_code,
            payload_obj.incident_id,
            _optional_text(incident.get("status")) or payload_obj.status,
            False,
            endpoint,
            payload,
            response_body,
        )

    def _headers(self) -> dict[str, str]:
        assert self.api_token is not None
        assert self.from_email is not None
        return {
            "Accept": "application/vnd.pagerduty+json;version=2",
            "Authorization": f"Token token={self.api_token}",
            "Content-Type": "application/json",
            "From": self.from_email,
            "User-Agent": "max-pagerduty-incident-status-updates-publisher/1",
        }

    def _validate_live_auth(self) -> None:
        if not self.api_token:
            raise PagerDutyIncidentStatusUpdatePublishError(
                "PAGERDUTY_API_TOKEN is required for live PagerDuty incident status updates; use dry_run to preview",
                secrets=self._secrets(),
            )
        if not self.from_email:
            raise PagerDutyIncidentStatusUpdatePublishError(
                "PAGERDUTY_FROM_EMAIL is required for live PagerDuty incident status updates; use dry_run to preview",
                secrets=self._secrets(),
            )

    def _secrets(self) -> list[str | None]:
        return [self.api_token]


PagerDutyIncidentStatusUpdatesPublisher = PagerDutyIncidentStatusUpdatePublisher


def _status_value(value: object) -> str:
    status = _required_text(value, "PagerDuty incident status is required").lower()
    if status not in VALID_STATUSES:
        allowed = ", ".join(sorted(VALID_STATUSES))
        raise PagerDutyIncidentStatusUpdatePublishError(
            f"PagerDuty incident status must be one of: {allowed}"
        )
    return status


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise PagerDutyIncidentStatusUpdatePublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _response_body_preview(
    response: httpx.Response,
    *,
    limit: int = 500,
    secrets: list[str | None] | None = None,
) -> str:
    text = response.text.strip()
    if len(text) > limit:
        text = text[:limit] + "..."
    return redact_text(text, secrets=secrets)


def _json_response(response: httpx.Response, *, secrets: list[str | None]) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise PagerDutyIncidentStatusUpdatePublishError(
            "PagerDuty incident status update failed: response was not valid JSON",
            status_code=response.status_code,
            secrets=secrets,
        ) from exc
    return body if isinstance(body, dict) else {}
