"""Opsgenie alert publisher for generated TactSpecs and design briefs."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx


DEFAULT_API_URL = "https://api.opsgenie.com"
DEFAULT_PRIORITY = "P3"
DEFAULT_TIMEOUT_SECONDS = 10.0
VALID_PRIORITIES = {"P1", "P2", "P3", "P4", "P5"}
SECRET_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "client_secret",
    "geniekey",
    "key",
    "password",
    "secret",
    "token",
}


class OpsgenieAlertPublishError(RuntimeError):
    """Raised when an Opsgenie alert publish cannot be completed."""

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
class OpsgenieAlertPayload:
    """Opsgenie alert creation payload plus Max-specific metadata."""

    message: str
    alias: str
    description: str
    priority: str
    tags: list[str]
    responders: list[dict[str, str]]
    details: dict[str, Any]
    metadata: dict[str, Any]
    entity: str | None = None
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable Opsgenie alert payload preview."""
        payload: dict[str, Any] = {
            "message": self.message,
            "alias": self.alias,
            "description": self.description,
            "priority": self.priority,
            "tags": self.tags,
            "responders": self.responders,
            "details": self.details,
            "metadata": self.metadata,
        }
        if self.entity:
            payload["entity"] = self.entity
        if self.source:
            payload["source"] = self.source
        return payload


@dataclass(frozen=True)
class OpsgenieAlertPublishResult:
    """Summary of an Opsgenie alert publish or dry run."""

    status_code: int | None
    request_id: str | None
    alert_id: str | None
    alias: str
    dry_run: bool
    payload: dict[str, Any]


class OpsgenieAlertPublisher:
    """Build and optionally create Opsgenie alerts from Max payloads."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        message: str | None = None,
        description: str | None = None,
        priority: str = DEFAULT_PRIORITY,
        tags: list[str] | None = None,
        responders: list[dict[str, str] | str] | None = None,
        alias: str | None = None,
        entity: str | None = None,
        source: str | None = None,
        details: dict[str, Any] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = _optional_text(api_key)
        self.api_url = _normalize_api_url(api_url)
        self.message = _optional_text(message)
        self.description = _optional_text(description)
        self.priority = _priority_value(priority)
        self.tags = [_tag_value(tag) for tag in tags or [] if _tag_value(tag)]
        self.responders = [_responder_value(responder) for responder in responders or []]
        self.alias = _optional_text(alias)
        self.entity = _optional_text(entity)
        self.source = _optional_text(source)
        self.details = _details_value(details)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        message: str | None = None,
        description: str | None = None,
        priority: str | None = None,
        tags: list[str] | None = None,
        responders: list[dict[str, str] | str] | None = None,
        alias: str | None = None,
        entity: str | None = None,
        source: str | None = None,
        details: dict[str, Any] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> OpsgenieAlertPublisher:
        """Create a publisher using API values first, then environment variables."""
        return cls(
            api_key=api_key or os.getenv("OPSGENIE_API_KEY"),
            api_url=api_url or os.getenv("OPSGENIE_API_URL"),
            message=message if message is not None else os.getenv("OPSGENIE_ALERT_MESSAGE"),
            description=(
                description
                if description is not None
                else os.getenv("OPSGENIE_ALERT_DESCRIPTION")
            ),
            priority=priority or os.getenv("OPSGENIE_ALERT_PRIORITY") or DEFAULT_PRIORITY,
            tags=tags if tags is not None else _env_list("OPSGENIE_ALERT_TAGS"),
            responders=(
                responders
                if responders is not None
                else _env_responders("OPSGENIE_ALERT_RESPONDERS")
            ),
            alias=alias if alias is not None else os.getenv("OPSGENIE_ALERT_ALIAS"),
            entity=entity if entity is not None else os.getenv("OPSGENIE_ALERT_ENTITY"),
            source=source if source is not None else os.getenv("OPSGENIE_ALERT_SOURCE"),
            details=details,
            timeout=timeout,
            client=client,
        )

    @property
    def alerts_endpoint(self) -> str:
        """Return the Opsgenie REST endpoint used for alert creation."""
        return f"{self.api_url}/v2/alerts"

    def build_alert_payload(self, tact_spec: dict[str, Any]) -> OpsgenieAlertPayload:
        """Convert a generated TactSpec preview into an Opsgenie alert payload."""
        _validate_tact_spec(tact_spec)
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")
        quality = _dict_value(tact_spec, "quality")
        evidence = _dict_value(tact_spec, "evidence")
        evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}

        source_type = str(source.get("type") or "idea")
        source_id = source.get("design_brief_id") or source.get("idea_id")
        metadata = {
            "publisher": "max.opsgenie_alerts",
            "source_system": source.get("system", "max"),
            "source_type": source_type,
            "source_id": source_id,
            "idea_id": source.get("idea_id"),
            "design_brief_id": source.get("design_brief_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "priority": self.priority,
        }
        generated_details = _generated_details(
            tact_spec,
            source=source,
            quality=quality,
            evidence=evidence,
            evaluation=evaluation,
            metadata=metadata,
        )

        return OpsgenieAlertPayload(
            message=self.message or _alert_message(project.get("title"), source_id),
            alias=self.alias or _alias(source, source_id),
            description=self.description or _tact_spec_description(tact_spec, metadata),
            priority=self.priority,
            tags=_merge_tags(
                _alert_tags(source=source, quality=quality, evaluation=evaluation),
                self.tags,
            ),
            responders=self.responders,
            details={**generated_details, **self.details},
            entity=self.entity or _entity(source, source_id),
            source=self.source or _source(source, source_id),
            metadata={
                **metadata,
                "quality_score": quality.get("quality_score"),
                "recommendation": evaluation.get("recommendation"),
            },
        )

    def build_design_brief_payload(
        self,
        design_brief: dict[str, Any],
        *,
        markdown: str | None = None,
        title: str | None = None,
    ) -> OpsgenieAlertPayload:
        """Convert a persisted design brief into an Opsgenie alert payload."""
        brief = _brief_payload(design_brief)
        brief_id = _optional_text(brief.get("id"))
        source_idea_ids = _string_list(brief.get("source_idea_ids"))
        metadata = {
            "publisher": "max.opsgenie_alerts",
            "source_system": "max",
            "source_type": "design_brief",
            "source_id": brief_id,
            "design_brief_id": brief_id,
            "lead_idea_id": brief.get("lead_idea_id"),
            "source_idea_ids": source_idea_ids,
            "schema_version": design_brief.get("schema_version") or "max.blueprint.source_brief.v1",
            "priority": self.priority,
        }
        message = self.message or _alert_message(title or brief.get("title"), brief_id)
        return OpsgenieAlertPayload(
            message=message,
            alias=self.alias or _token_alias("design_brief", brief_id or brief.get("title")),
            description=self.description
            or _design_brief_description(design_brief, markdown=markdown, metadata=metadata),
            priority=self.priority,
            tags=_merge_tags(_design_brief_tags(brief), self.tags),
            responders=self.responders,
            details={**_design_brief_details(brief, metadata), **self.details},
            entity=self.entity or _entity_from_parts("design_brief", brief_id),
            source=self.source or "max/design-brief",
            metadata=metadata,
        )

    def publish(
        self,
        tact_spec: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> OpsgenieAlertPublishResult:
        """Build the alert payload and optionally create it in Opsgenie."""
        return self._publish_payload(self.build_alert_payload(tact_spec).to_dict(), dry_run=dry_run)

    def publish_design_brief(
        self,
        design_brief: dict[str, Any],
        *,
        markdown: str | None = None,
        title: str | None = None,
        dry_run: bool = True,
    ) -> OpsgenieAlertPublishResult:
        """Build a design brief alert payload and optionally create it in Opsgenie."""
        payload = self.build_design_brief_payload(
            design_brief,
            markdown=markdown,
            title=title,
        ).to_dict()
        return self._publish_payload(payload, dry_run=dry_run)

    def _publish_payload(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool,
    ) -> OpsgenieAlertPublishResult:
        if dry_run:
            return OpsgenieAlertPublishResult(
                status_code=None,
                request_id=None,
                alert_id=None,
                alias=payload["alias"],
                dry_run=True,
                payload=payload,
            )

        if not self.api_key:
            raise OpsgenieAlertPublishError(
                "OPSGENIE_API_KEY is required for live Opsgenie alert publishing; "
                "use dry_run to preview",
                secrets=self._secrets,
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.alerts_endpoint,
                    json=_opsgenie_alert_request(payload),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                message = _redact_text(str(exc), secrets=self._secrets)
                raise OpsgenieAlertPublishError(
                    f"Opsgenie alert publish failed for "
                    f"{_redact_url(self.alerts_endpoint)}: {message}",
                    secrets=self._secrets,
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise OpsgenieAlertPublishError(
                f"Opsgenie alert publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response, secrets=self._secrets)}",
                status_code=response.status_code,
                secrets=self._secrets,
            )

        body = _json_response(response, secrets=self._secrets)
        request_id = _optional_text(body.get("requestId")) or _optional_text(body.get("request_id"))
        alert_id = _optional_text(body.get("alertId")) or _optional_text(body.get("alert_id"))
        metadata = {**payload["metadata"], "opsgenie_alert_alias": payload["alias"]}
        if request_id:
            metadata["opsgenie_request_id"] = request_id
        if alert_id:
            metadata["opsgenie_alert_id"] = alert_id

        return OpsgenieAlertPublishResult(
            status_code=response.status_code,
            request_id=request_id,
            alert_id=alert_id,
            alias=payload["alias"],
            dry_run=False,
            payload={**payload, "metadata": metadata},
        )

    @property
    def _secrets(self) -> list[str | None]:
        return [self.api_key]

    def _headers(self) -> dict[str, str]:
        assert self.api_key is not None
        return {
            "Accept": "application/json",
            "Authorization": f"GenieKey {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "max-opsgenie-alerts-publisher/1",
        }


OpsgenieAlertsPublisher = OpsgenieAlertPublisher


def _opsgenie_alert_request(payload: dict[str, Any]) -> dict[str, Any]:
    request: dict[str, Any] = {
        "message": payload["message"],
        "alias": payload["alias"],
        "description": payload["description"],
        "priority": payload["priority"],
        "tags": payload.get("tags") or [],
        "details": _string_details(payload.get("details") or {}),
    }
    for key in ("responders", "entity", "source"):
        if payload.get(key):
            request[key] = payload[key]
    return request


def _validate_tact_spec(tact_spec: dict[str, Any]) -> None:
    if not isinstance(tact_spec, dict):
        raise OpsgenieAlertPublishError("Opsgenie alert publishing requires a TactSpec dict")
    project = _dict_value(tact_spec, "project")
    source = _dict_value(tact_spec, "source")
    if not _optional_text(project.get("title")) and not (
        _optional_text(source.get("idea_id")) or _optional_text(source.get("design_brief_id"))
    ):
        raise OpsgenieAlertPublishError(
            "Opsgenie alert publishing requires project.title or a source id"
        )
    if not _optional_text(tact_spec.get("schema_version")):
        raise OpsgenieAlertPublishError(
            "Opsgenie alert publishing requires schema_version in the TactSpec payload"
        )


def _alert_message(title: object, source_id: object) -> str:
    base = str(title).strip() if title else str(source_id or "Generated TactSpec").strip()
    return f"[Max] {base}"[:130]


def _tact_spec_description(tact_spec: dict[str, Any], metadata: dict[str, Any]) -> str:
    project = _dict_value(tact_spec, "project")
    problem = _dict_value(tact_spec, "problem")
    solution = _dict_value(tact_spec, "solution")
    execution = _dict_value(tact_spec, "execution")
    evidence = _dict_value(tact_spec, "evidence")
    source = _dict_value(tact_spec, "source")
    evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}
    lines = [
        f"# {project.get('title') or source.get('design_brief_id') or source.get('idea_id') or 'Generated TactSpec'}",
        "",
        _text_or_placeholder(project.get("summary")),
        "",
        "## Source",
        f"- Type: {_text_or_placeholder(source.get('type'))}",
        f"- Idea ID: {_text_or_placeholder(source.get('idea_id'))}",
        f"- Design brief ID: {_text_or_placeholder(source.get('design_brief_id'))}",
        f"- Status: {_text_or_placeholder(source.get('status'))}",
        f"- Domain: {_text_or_placeholder(source.get('domain'))}",
        f"- Category: {_text_or_placeholder(source.get('category'))}",
        "",
        "## Problem",
        _text_or_placeholder(problem.get("statement")),
        "",
        "## Solution",
        _text_or_placeholder(solution.get("approach")),
        "",
        "## Evaluation",
        f"- Recommendation: {_text_or_placeholder(evaluation.get('recommendation'))}",
        f"- Overall score: {_score_text(evaluation.get('overall_score'))}",
        "",
        "## Evidence Chain",
        f"- Rationale: {_text_or_placeholder(evidence.get('rationale'))}",
        f"- Insights: {_join_strings(evidence.get('insight_ids')) or 'None'}",
        f"- Signals: {_join_strings(evidence.get('signal_ids')) or 'None'}",
        "",
        "## Validation Plan",
        _text_or_placeholder(execution.get("validation_plan")),
    ]
    lines.extend(_metadata_lines(metadata))
    return "\n".join(lines)


def _design_brief_description(
    design_brief: dict[str, Any],
    *,
    markdown: str | None,
    metadata: dict[str, Any],
) -> str:
    brief = _brief_payload(design_brief)
    source_ideas = _source_ideas(design_brief)
    lead_problem = _lead_source_value(source_ideas, "problem")
    lead_solution = _lead_source_value(source_ideas, "solution")
    lines = [
        f"# {brief.get('title') or brief.get('id') or 'Design Brief'}",
        "",
        _text_or_placeholder(
            brief.get("merged_product_concept")
            or brief.get("synthesis_rationale")
            or brief.get("why_this_now")
        ),
        "",
        "## Source",
        f"- Design brief ID: {_text_or_placeholder(brief.get('id'))}",
        f"- Lead idea ID: {_text_or_placeholder(brief.get('lead_idea_id'))}",
        f"- Source idea IDs: {_join_strings(brief.get('source_idea_ids')) or 'None'}",
        f"- Domain: {_text_or_placeholder(brief.get('domain'))}",
        f"- Theme: {_text_or_placeholder(brief.get('theme'))}",
        f"- Status: {_text_or_placeholder(brief.get('design_status') or brief.get('status'))}",
        f"- Readiness score: {_score_text(brief.get('readiness_score'))}",
        "",
        "## Problem",
        _text_or_placeholder(lead_problem),
        "",
        "## Solution",
        _text_or_placeholder(lead_solution or brief.get("merged_product_concept")),
        "",
        "## Validation Plan",
        _text_or_placeholder(brief.get("validation_plan")),
    ]
    if markdown:
        lines.extend(["", "## Design Brief Markdown", markdown.strip()])
    lines.extend(_metadata_lines(metadata))
    return "\n".join(lines)


def _generated_details(
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


def _design_brief_details(brief: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "design_brief_id": brief.get("id"),
        "title": brief.get("title"),
        "domain": brief.get("domain"),
        "theme": brief.get("theme"),
        "lead_idea_id": brief.get("lead_idea_id"),
        "source_idea_ids": _string_list(brief.get("source_idea_ids")),
        "readiness_score": brief.get("readiness_score"),
        "status": brief.get("design_status") or brief.get("status"),
        "max_metadata": metadata,
    }


def _alert_tags(
    *,
    source: dict[str, Any],
    quality: dict[str, Any],
    evaluation: dict[str, Any],
) -> list[str]:
    tags = [
        "max",
        "tact-spec",
        "publisher:opsgenie",
        _tag_pair("source_type", source.get("type") or "idea"),
        _tag_pair("source_system", source.get("system") or "max"),
        _tag_pair("domain", source.get("domain")),
        _tag_pair("category", source.get("category")),
        _tag_pair("status", source.get("status")),
        _tag_pair("recommendation", evaluation.get("recommendation")),
    ]
    tags.extend(_tag_pair("quality", tag) for tag in quality.get("rejection_tags") or [])
    return _unique(tags)


def _design_brief_tags(brief: dict[str, Any]) -> list[str]:
    return _unique(
        [
            "max",
            "design-brief",
            "publisher:opsgenie",
            _tag_pair("domain", brief.get("domain")),
            _tag_pair("theme", brief.get("theme")),
            _tag_pair("status", brief.get("design_status") or brief.get("status")),
        ]
    )


def _merge_tags(tags: list[str], extra_tags: list[str]) -> list[str]:
    return _unique([*tags, *(_tag_value(tag) for tag in extra_tags)])


def _unique(tags: list[str]) -> list[str]:
    unique: list[str] = []
    for tag in tags:
        if tag and tag not in unique:
            unique.append(tag)
    return unique


def _tag_pair(key: str, value: object) -> str:
    safe_value = _tag_value(value)
    return f"{key}:{safe_value}" if safe_value else ""


def _tag_value(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower().replace("_", "-").replace(" ", "-")
    safe = "".join(ch for ch in text if ch.isalnum() or ch in "-.:/")
    return safe[:100]


def _alias(source: dict[str, Any], source_id: object) -> str:
    source_type = _token_value(source.get("type")) or "idea"
    identifier = _token_value(source_id) or _token_value(source.get("category")) or "generated"
    return _token_alias(source_type, identifier)


def _token_alias(source_type: object, identifier: object) -> str:
    return f"max:{_token_value(source_type) or 'source'}:{_token_value(identifier) or 'generated'}"[:512]


def _entity(source: dict[str, Any], source_id: object) -> str:
    source_type = _token_value(source.get("type")) or "idea"
    return _entity_from_parts(source_type, source_id)


def _entity_from_parts(source_type: object, source_id: object) -> str:
    identifier = _token_value(source_id) or "generated"
    return f"max/{_token_value(source_type) or 'source'}/{identifier}"[:512]


def _source(source: dict[str, Any], source_id: object) -> str:
    system = _token_value(source.get("system")) or "max"
    source_type = _token_value(source.get("type")) or "idea"
    identifier = _token_value(source_id) or "generated"
    return f"{system}/{source_type}/{identifier}"[:100]


def _priority_value(value: object) -> str:
    text = str(value).strip().upper() if value else ""
    if text not in VALID_PRIORITIES:
        raise OpsgenieAlertPublishError("Opsgenie priority must be one of P1, P2, P3, P4, or P5")
    return text


def _responder_value(value: dict[str, str] | str) -> dict[str, str]:
    if isinstance(value, str):
        text = _required_text(value, "Opsgenie responder value is required")
        return {"name": text, "type": "team"}
    if not isinstance(value, dict):
        raise OpsgenieAlertPublishError("Opsgenie responders must be strings or dicts")
    responder_type = _required_text(value.get("type"), "Opsgenie responder type is required")
    if responder_type not in {"team", "user", "escalation", "schedule"}:
        raise OpsgenieAlertPublishError(
            "Opsgenie responder type must be one of team, user, escalation, or schedule"
        )
    responder = {"type": responder_type}
    for key in ("id", "name", "username"):
        text = _optional_text(value.get(key))
        if text:
            responder[key] = text
    if not any(key in responder for key in ("id", "name", "username")):
        raise OpsgenieAlertPublishError("Opsgenie responder requires id, name, or username")
    return responder


def _details_value(value: object) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise OpsgenieAlertPublishError("Opsgenie details must be a dict")
    return dict(value)


def _string_details(details: dict[str, Any]) -> dict[str, str]:
    stringified: dict[str, str] = {}
    for key, value in details.items():
        if value is None:
            continue
        text_key = str(key).strip()
        if not text_key:
            continue
        if isinstance(value, str):
            stringified[text_key] = value
        else:
            stringified[text_key] = json.dumps(value, sort_keys=True)
    return stringified


def _metadata_lines(metadata: dict[str, Any]) -> list[str]:
    return [
        "",
        "## Max Metadata",
        "```json",
        json.dumps(metadata, indent=2, sort_keys=True),
        "```",
    ]


def _brief_payload(payload: dict[str, Any]) -> dict[str, Any]:
    brief = payload.get("design_brief") if isinstance(payload.get("design_brief"), dict) else payload
    if not isinstance(brief, dict):
        raise OpsgenieAlertPublishError("Opsgenie alert publishing requires a design brief dict")
    if not _optional_text(brief.get("title")) and not _optional_text(brief.get("id")):
        raise OpsgenieAlertPublishError(
            "Opsgenie design brief alert publishing requires design_brief.title or id"
        )
    return brief


def _source_ideas(payload: dict[str, Any]) -> list[dict[str, Any]]:
    ideas = payload.get("source_ideas")
    return [idea for idea in ideas if isinstance(idea, dict)] if isinstance(ideas, list) else []


def _lead_source_value(source_ideas: list[dict[str, Any]], key: str) -> Any:
    for idea in source_ideas:
        if idea.get("role") == "lead" and idea.get(key):
            return idea[key]
    for idea in source_ideas:
        if idea.get(key):
            return idea[key]
    return None


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _text_or_placeholder(value: object) -> str:
    text = str(value).strip() if value else ""
    return text or "Not specified"


def _score_text(value: object) -> str:
    if isinstance(value, int | float):
        return f"{value:.1f}"
    return _text_or_placeholder(value)


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return _unique_strings(value)
    if value is None:
        return []
    return _unique_strings(str(value).split(","))


def _join_strings(value: object) -> str:
    return ", ".join(_string_list(value))


def _unique_strings(values: list[object]) -> list[str]:
    unique: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in unique:
            unique.append(text)
    return unique


def _token_value(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower().replace("_", "-").replace(" ", "-")
    return "".join(ch for ch in text if ch.isalnum() or ch in "-.:/")[:200]


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value else ""
    if not text:
        raise OpsgenieAlertPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _env_list(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_responders(name: str) -> list[str]:
    return _env_list(name)


def _normalize_api_url(api_url: str | None) -> str:
    raw = _optional_text(api_url)
    if not raw:
        return DEFAULT_API_URL
    if "://" not in raw:
        raw = f"https://{raw}"
    raw = raw.rstrip("/")
    if raw.endswith("/v2/alerts"):
        raw = raw[: -len("/v2/alerts")]
    parts = urlsplit(raw)
    if not parts.scheme or not parts.netloc:
        raise OpsgenieAlertPublishError("Opsgenie api_url must be an absolute URL")
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
        raise OpsgenieAlertPublishError(
            "Opsgenie alert publish failed: response was not valid JSON",
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
        r"(?i)\b(token|api_token|api_key|geniekey|password|secret|authorization)\b"
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
