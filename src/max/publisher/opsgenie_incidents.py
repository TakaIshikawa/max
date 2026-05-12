"""Opsgenie incident publisher for generated TactSpec previews."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, dict_value, join_list, metadata, optional_text, redact_text, required_url, response_json, response_preview, score_text, tag_value, text_or_placeholder, title, validate_tact_spec

DEFAULT_API_URL = "https://api.opsgenie.com"
DEFAULT_PRIORITY = "P3"
VALID_PRIORITIES = {"P1", "P2", "P3", "P4", "P5"}


class OpsgenieIncidentPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, api_key: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[api_key]))
        self.status_code = status_code


@dataclass(frozen=True)
class OpsgenieIncidentPublishResult:
    status_code: int | None
    request_id: str | None
    result: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class OpsgenieIncidentPublisher:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_url: str = DEFAULT_API_URL,
        message: str | None = None,
        description: str | None = None,
        priority: str = DEFAULT_PRIORITY,
        responders: list[dict[str, str] | str] | None = None,
        tags: list[str] | None = None,
        details: dict[str, Any] | None = None,
        note: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = optional_text(api_key)
        self.api_url = _normalize_api_url(api_url)
        self.message = optional_text(message)
        self.description = optional_text(description)
        self.priority = _priority(priority)
        self.responders = [_responder(responder) for responder in responders or []]
        self.tags = [_tag(tag) for tag in tags or [] if _tag(tag)]
        self.details = _details(details)
        self.note = optional_text(note)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> OpsgenieIncidentPublisher:
        return cls(
            api_key=kwargs.pop("api_key", None) or os.getenv("OPSGENIE_API_KEY"),
            api_url=kwargs.pop("api_url", None) or os.getenv("OPSGENIE_API_URL", DEFAULT_API_URL),
            message=kwargs.pop("message", None) or os.getenv("OPSGENIE_INCIDENT_MESSAGE"),
            description=kwargs.pop("description", None) or os.getenv("OPSGENIE_INCIDENT_DESCRIPTION"),
            priority=kwargs.pop("priority", None) or os.getenv("OPSGENIE_INCIDENT_PRIORITY") or DEFAULT_PRIORITY,
            responders=kwargs.pop("responders", None) or _env_list("OPSGENIE_INCIDENT_RESPONDERS"),
            tags=kwargs.pop("tags", None) or _env_list("OPSGENIE_INCIDENT_TAGS"),
            note=kwargs.pop("note", None) or os.getenv("OPSGENIE_INCIDENT_NOTE"),
            **kwargs,
        )

    @property
    def endpoint(self) -> str:
        return f"{self.api_url}/v1/incidents/create"

    def build_incident_payload(self, tact_spec: dict[str, Any]) -> dict[str, Any]:
        try:
            validate_tact_spec(tact_spec, label="Opsgenie incident")
        except ValueError as exc:
            raise OpsgenieIncidentPublishError(str(exc), api_key=self.api_key) from exc
        source = dict_value(tact_spec, "source")
        evidence = dict_value(tact_spec, "evidence")
        quality = dict_value(tact_spec, "quality")
        evaluation = dict_value(tact_spec, "evaluation")
        meta = metadata(tact_spec, publisher="max.opsgenie_incidents", extra={"priority": self.priority})
        payload: dict[str, Any] = {
            "message": self.message or f"[Max] {title(tact_spec)}",
            "description": self.description or _description(tact_spec, meta),
            "priority": self.priority,
            "responders": self.responders,
            "tags": _unique(["max", "tact-spec", "publisher:opsgenie", tag_value(source.get("domain"), prefix="domain"), tag_value(source.get("category"), prefix="category"), *self.tags]),
            "details": {
                "source_id": meta.get("source_id"),
                "source_type": meta.get("source_type"),
                "rationale": evidence.get("rationale"),
                "insight_ids": evidence.get("insight_ids") or [],
                "signal_ids": evidence.get("signal_ids") or [],
                "quality_score": quality.get("quality_score"),
                "recommendation": evaluation.get("recommendation"),
                "max_metadata": meta,
                **self.details,
            },
            "metadata": meta,
        }
        if self.note:
            payload["note"] = self.note
        return payload

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True) -> OpsgenieIncidentPublishResult:
        payload = self.build_incident_payload(tact_spec)
        if dry_run:
            return OpsgenieIncidentPublishResult(None, None, None, True, self.endpoint, payload)
        if not self.api_key:
            raise OpsgenieIncidentPublishError("OPSGENIE_API_KEY is required for live Opsgenie incident publishing; use dry_run to preview")
        response = self._post(payload)
        body = response_json(response, OpsgenieIncidentPublishError, "Opsgenie incident publish failed: response was not valid JSON")
        return OpsgenieIncidentPublishResult(response.status_code, optional_text(body.get("requestId")) or optional_text(body.get("request_id")), optional_text(body.get("result")), False, self.endpoint, payload, body)

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.endpoint, json=_incident_request(payload), headers=self._headers(), timeout=self.timeout)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise OpsgenieIncidentPublishError(f"Opsgenie incident publish failed for {self.endpoint}: {exc}", api_key=self.api_key) from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise OpsgenieIncidentPublishError(f"Opsgenie incident publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.api_key])}", status_code=response.status_code, api_key=self.api_key)
        return response

    def _headers(self) -> dict[str, str]:
        assert self.api_key is not None
        return {"Accept": "application/json", "Authorization": f"GenieKey {self.api_key}", "Content-Type": "application/json", "User-Agent": "max-opsgenie-incidents-publisher/1"}


OpsgenieIncidentsPublisher = OpsgenieIncidentPublisher


def _incident_request(payload: dict[str, Any]) -> dict[str, Any]:
    request = {key: payload[key] for key in ("message", "description", "priority", "responders", "tags") if payload.get(key)}
    request["details"] = {key: _string_detail(value) for key, value in (payload.get("details") or {}).items()}
    if payload.get("note"):
        request["note"] = payload["note"]
    return request


def _description(tact_spec: dict[str, Any], meta: dict[str, Any]) -> str:
    project = dict_value(tact_spec, "project")
    evidence = dict_value(tact_spec, "evidence")
    quality = dict_value(tact_spec, "quality")
    evaluation = dict_value(tact_spec, "evaluation")
    lines = [
        f"# {title(tact_spec)}",
        "",
        text_or_placeholder(project.get("summary")),
        "",
        f"Evidence: {text_or_placeholder(evidence.get('rationale'))}",
        f"Insights: {join_list(evidence.get('insight_ids'))}",
        f"Risk tags: {join_list(quality.get('rejection_tags'))}",
        f"Recommendation: {text_or_placeholder(evaluation.get('recommendation'))}; score {score_text(evaluation.get('overall_score'))}",
        "",
        json.dumps(meta, sort_keys=True),
    ]
    return "\n".join(lines)


def _normalize_api_url(value: str | None) -> str:
    raw = optional_text(value) or DEFAULT_API_URL
    if "://" not in raw:
        raw = f"https://{raw}"
    raw = required_url(raw, "Opsgenie api_url must be an absolute http(s) URL")
    if raw.endswith("/v1/incidents/create"):
        raw = raw[: -len("/v1/incidents/create")]
    return raw


def _priority(value: object) -> str:
    text = str(value).strip().upper() if value else ""
    if text not in VALID_PRIORITIES:
        raise OpsgenieIncidentPublishError("Opsgenie incident priority must be one of P1, P2, P3, P4, or P5")
    return text


def _responder(value: dict[str, str] | str) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(key): str(val) for key, val in value.items() if val is not None}
    return {"type": "team", "name": str(value)}


def _tag(value: object) -> str:
    return tag_value(value) or ""


def _details(value: object) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise OpsgenieIncidentPublishError("Opsgenie incident details must be a dict")
    return dict(value)


def _unique(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen


def _string_detail(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)


def _env_list(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]
