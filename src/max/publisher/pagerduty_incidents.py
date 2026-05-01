"""PagerDuty incident publisher for generated TactSpecs."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx


DEFAULT_EVENTS_API_URL = "https://events.pagerduty.com"
DEFAULT_EVENT_ACTION = "trigger"
DEFAULT_SEVERITY = "warning"
DEFAULT_TIMEOUT_SECONDS = 10.0
VALID_EVENT_ACTIONS = {"trigger", "acknowledge", "resolve"}
VALID_SEVERITIES = {"critical", "error", "warning", "info"}
SECRET_QUERY_KEYS = {
    "access_token",
    "api_key",
    "auth",
    "authorization",
    "client_secret",
    "key",
    "routing_key",
    "secret",
    "token",
}


class PagerDutyIncidentPublishError(RuntimeError):
    """Raised when a PagerDuty incident publish cannot be completed."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        secrets: list[str | None] | None = None,
    ) -> None:
        super().__init__(_redact_text(message, secrets=secrets))
        self.status_code = status_code


@dataclass(frozen=True)
class PagerDutyIncidentPayload:
    """PagerDuty Events API v2 payload plus Max-specific metadata."""

    routing_key: str | None
    event_action: str
    summary: str
    severity: str
    source: str
    dedup_key: str
    custom_details: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable PagerDuty event payload preview."""
        payload: dict[str, Any] = {
            "event_action": self.event_action,
            "dedup_key": self.dedup_key,
            "payload": {
                "summary": self.summary,
                "severity": self.severity,
                "source": self.source,
                "custom_details": self.custom_details,
            },
            "metadata": self.metadata,
        }
        if self.routing_key:
            payload["routing_key"] = self.routing_key
        return payload


@dataclass(frozen=True)
class PagerDutyIncidentPublishResult:
    """Summary of a PagerDuty incident publish or dry run."""

    status_code: int | None
    dedup_key: str | None
    incident_key: str | None
    dry_run: bool
    payload: dict[str, Any]


class PagerDutyIncidentPublisher:
    """Build and optionally trigger PagerDuty incidents from TactSpec previews."""

    def __init__(
        self,
        *,
        routing_key: str | None = None,
        events_api_url: str | None = None,
        event_action: str = DEFAULT_EVENT_ACTION,
        severity: str = DEFAULT_SEVERITY,
        source: str | None = None,
        dedup_key: str | None = None,
        custom_details: dict[str, Any] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.routing_key = _optional_text(routing_key)
        self.events_api_url = _normalize_events_api_url(events_api_url)
        self.event_action = _event_action_value(event_action)
        self.severity = _severity_value(severity)
        self.source = _optional_text(source)
        self.dedup_key = _optional_text(dedup_key)
        self.custom_details = _custom_details_value(custom_details)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        routing_key: str | None = None,
        events_api_url: str | None = None,
        event_action: str | None = None,
        severity: str | None = None,
        source: str | None = None,
        dedup_key: str | None = None,
        custom_details: dict[str, Any] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> PagerDutyIncidentPublisher:
        """Create a publisher using API values first, then environment variables."""
        return cls(
            routing_key=routing_key or os.getenv("PAGERDUTY_ROUTING_KEY"),
            events_api_url=events_api_url or os.getenv("PAGERDUTY_EVENTS_API_URL"),
            event_action=event_action or os.getenv("PAGERDUTY_EVENT_ACTION") or DEFAULT_EVENT_ACTION,
            severity=severity or os.getenv("PAGERDUTY_SEVERITY") or DEFAULT_SEVERITY,
            source=source or os.getenv("PAGERDUTY_SOURCE"),
            dedup_key=dedup_key or os.getenv("PAGERDUTY_DEDUP_KEY"),
            custom_details=custom_details,
            timeout=timeout,
            client=client,
        )

    @property
    def enqueue_endpoint(self) -> str:
        """Return the PagerDuty Events API endpoint used for event enqueue."""
        return f"{self.events_api_url}/v2/enqueue"

    def build_incident_payload(self, tact_spec: dict[str, Any]) -> PagerDutyIncidentPayload:
        """Convert a generated TactSpec preview into a PagerDuty trigger payload."""
        _validate_tact_spec(tact_spec)
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")
        quality = _dict_value(tact_spec, "quality")
        evidence = _dict_value(tact_spec, "evidence")
        evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}

        source_type = str(source.get("type") or "idea")
        source_id = source.get("idea_id") or source.get("design_brief_id")
        metadata = {
            "publisher": "max.pagerduty_incidents",
            "source_system": source.get("system", "max"),
            "source_type": source_type,
            "source_id": source_id,
            "idea_id": source.get("idea_id"),
            "design_brief_id": source.get("design_brief_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
        }
        custom_details = {
            **_generated_custom_details(
                tact_spec,
                source=source,
                quality=quality,
                evidence=evidence,
                evaluation=evaluation,
                metadata=metadata,
            ),
            **self.custom_details,
        }

        return PagerDutyIncidentPayload(
            routing_key=self.routing_key,
            event_action=self.event_action,
            summary=_incident_summary(project.get("title"), source_id),
            severity=self.severity,
            source=self.source or _incident_source(source, source_id),
            dedup_key=self.dedup_key or _dedup_key(source, source_id),
            custom_details=custom_details,
            metadata=metadata,
        )

    def publish(
        self,
        tact_spec: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> PagerDutyIncidentPublishResult:
        """Build the incident payload and optionally enqueue it in PagerDuty."""
        payload = self.build_incident_payload(tact_spec).to_dict()
        if dry_run:
            return PagerDutyIncidentPublishResult(
                status_code=None,
                dedup_key=payload["dedup_key"],
                incident_key=None,
                dry_run=True,
                payload=payload,
            )

        if not self.routing_key:
            raise PagerDutyIncidentPublishError(
                "PAGERDUTY_ROUTING_KEY is required for live PagerDuty incident publishing; "
                "use dry_run to preview",
                secrets=self._secrets,
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.enqueue_endpoint,
                    json=_pagerduty_event_request(payload),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                message = _redact_text(str(exc), secrets=self._secrets)
                raise PagerDutyIncidentPublishError(
                    f"PagerDuty incident publish failed for "
                    f"{_redact_url(self.enqueue_endpoint)}: {message}",
                    secrets=self._secrets,
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise PagerDutyIncidentPublishError(
                f"PagerDuty incident publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response, secrets=self._secrets)}",
                status_code=response.status_code,
                secrets=self._secrets,
            )

        body = _json_response(response, secrets=self._secrets)
        dedup_key = _optional_text(body.get("dedup_key")) or payload["dedup_key"]
        incident_key = _optional_text(body.get("incident_key")) or dedup_key
        return PagerDutyIncidentPublishResult(
            status_code=response.status_code,
            dedup_key=dedup_key,
            incident_key=incident_key,
            dry_run=False,
            payload={
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "pagerduty_dedup_key": dedup_key,
                    "pagerduty_incident_key": incident_key,
                },
            },
        )

    @property
    def _secrets(self) -> list[str | None]:
        return [self.routing_key]

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "max-pagerduty-incidents-publisher/1",
        }


PagerDutyIncidentsPublisher = PagerDutyIncidentPublisher


def _pagerduty_event_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "routing_key": payload["routing_key"],
        "event_action": payload["event_action"],
        "dedup_key": payload["dedup_key"],
        "payload": payload["payload"],
    }


def _validate_tact_spec(tact_spec: dict[str, Any]) -> None:
    if not isinstance(tact_spec, dict):
        raise PagerDutyIncidentPublishError(
            "PagerDuty incident publishing requires a TactSpec dict"
        )
    project = _dict_value(tact_spec, "project")
    source = _dict_value(tact_spec, "source")
    if not _optional_text(project.get("title")) and not (
        _optional_text(source.get("idea_id")) or _optional_text(source.get("design_brief_id"))
    ):
        raise PagerDutyIncidentPublishError(
            "PagerDuty incident publishing requires project.title or a source id"
        )
    if not _optional_text(tact_spec.get("schema_version")):
        raise PagerDutyIncidentPublishError(
            "PagerDuty incident publishing requires schema_version in the TactSpec payload"
        )


def _incident_summary(title: object, source_id: object) -> str:
    base = str(title).strip() if title else str(source_id or "Generated TactSpec").strip()
    return f"[Max] Launch risk: {base}"[:1024]


def _incident_source(source: dict[str, Any], source_id: object) -> str:
    system = _token_value(source.get("system")) or "max"
    source_type = _token_value(source.get("type")) or "idea"
    identifier = _token_value(source_id) or "generated"
    return f"{system}/{source_type}/{identifier}"[:1024]


def _dedup_key(source: dict[str, Any], source_id: object) -> str:
    source_type = _token_value(source.get("type")) or "idea"
    identifier = _token_value(source_id) or _token_value(source.get("category")) or "generated"
    return f"max:{source_type}:{identifier}"[:255]


def _generated_custom_details(
    tact_spec: dict[str, Any],
    *,
    source: dict[str, Any],
    quality: dict[str, Any],
    evidence: dict[str, Any],
    evaluation: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    project = _dict_value(tact_spec, "project")
    problem = _dict_value(tact_spec, "problem")
    solution = _dict_value(tact_spec, "solution")
    execution = _dict_value(tact_spec, "execution")
    return {
        "project_title": project.get("title"),
        "project_summary": project.get("summary"),
        "problem": problem.get("statement"),
        "approach": solution.get("approach"),
        "validation_plan": execution.get("validation_plan"),
        "mvp_scope": execution.get("mvp_scope") or [],
        "recommendation": evaluation.get("recommendation"),
        "overall_score": evaluation.get("overall_score"),
        "quality_score": quality.get("quality_score"),
        "rejection_tags": quality.get("rejection_tags") or [],
        "rationale": evidence.get("rationale"),
        "insight_ids": evidence.get("insight_ids") or [],
        "signal_ids": evidence.get("signal_ids") or [],
        "source_url": source.get("url") or source.get("source_url"),
        "max_metadata": metadata,
    }


def _custom_details_value(value: object) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise PagerDutyIncidentPublishError("PagerDuty custom_details must be a dict")
    return dict(value)


def _event_action_value(value: object) -> str:
    text = str(value).strip().lower() if value else ""
    if text not in VALID_EVENT_ACTIONS:
        raise PagerDutyIncidentPublishError(
            "PagerDuty event_action must be one of trigger, acknowledge, or resolve"
        )
    return text


def _severity_value(value: object) -> str:
    text = str(value).strip().lower() if value else ""
    if text not in VALID_SEVERITIES:
        raise PagerDutyIncidentPublishError(
            "PagerDuty severity must be one of critical, error, warning, or info"
        )
    return text


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _token_value(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower().replace("_", "-").replace(" ", "-")
    return "".join(ch for ch in text if ch.isalnum() or ch in "-.:/")[:200]


def _normalize_events_api_url(events_api_url: str | None) -> str:
    raw = _optional_text(events_api_url)
    if not raw:
        return DEFAULT_EVENTS_API_URL
    if "://" not in raw:
        raw = f"https://{raw}"
    raw = raw.rstrip("/")
    if raw.endswith("/v2/enqueue"):
        raw = raw[: -len("/v2/enqueue")]
    parts = urlsplit(raw)
    if not parts.scheme or not parts.netloc:
        raise PagerDutyIncidentPublishError(
            "PagerDuty events_api_url must be an absolute URL"
        )
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _response_body_preview(
    response: httpx.Response,
    *,
    secrets: list[str | None],
    limit: int = 500,
) -> str:
    text = _redact_text(response.text.strip(), secrets=secrets)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(response: httpx.Response, *, secrets: list[str | None]) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise PagerDutyIncidentPublishError(
            "PagerDuty incident publish failed: response was not valid JSON",
            status_code=response.status_code,
            secrets=secrets,
        ) from exc
    return body if isinstance(body, dict) else {}


def _redact_text(text: str, *, secrets: list[str | None] | None = None) -> str:
    redacted = text
    for secret in secrets or []:
        if secret:
            redacted = redacted.replace(secret, "<redacted>")
    redacted = re.sub(
        r"(?i)\b(token|api_token|api_key|routing_key|password|secret|authorization)\b"
        r"([=:]\s*)[^&\s,'\"}]+",
        r"\1\2<redacted>",
        redacted,
    )
    return _redact_url(redacted)


def _redact_url(text: str) -> str:
    words = text.split()
    return " ".join(_redact_url_word(word) for word in words)


def _redact_url_word(word: str) -> str:
    try:
        parts = urlsplit(word)
    except ValueError:
        return word
    if not parts.scheme or not parts.netloc:
        return word
    query = urlencode(
        [
            (key, "<redacted>" if key.lower() in SECRET_QUERY_KEYS else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
    )
    netloc = parts.hostname or ""
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))
