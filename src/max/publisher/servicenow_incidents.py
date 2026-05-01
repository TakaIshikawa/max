"""ServiceNow incident publisher for TactSpecs and design briefs."""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx


DEFAULT_CATEGORY = "inquiry"
DEFAULT_CONTACT_TYPE = "integration"
DEFAULT_IMPACT = "3"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_URGENCY = "3"
SECRET_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "client_secret",
    "password",
    "secret",
    "sid",
    "token",
}


class ServiceNowIncidentPublishError(RuntimeError):
    """Raised when a ServiceNow incident publish cannot be completed."""

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
class ServiceNowIncidentPayload:
    """ServiceNow incident creation payload plus Max-specific metadata."""

    short_description: str
    description: str
    impact: str
    urgency: str
    category: str
    contact_type: str
    metadata: dict[str, Any]
    assignment_group: str | None = None
    caller_id: str | None = None
    cmdb_ci: str | None = None
    subcategory: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable ServiceNow incident payload preview."""
        payload: dict[str, Any] = {
            "short_description": self.short_description,
            "description": self.description,
            "impact": self.impact,
            "urgency": self.urgency,
            "category": self.category,
            "contact_type": self.contact_type,
            "metadata": self.metadata,
        }
        if self.assignment_group:
            payload["assignment_group"] = self.assignment_group
        if self.caller_id:
            payload["caller_id"] = self.caller_id
        if self.cmdb_ci:
            payload["cmdb_ci"] = self.cmdb_ci
        if self.subcategory:
            payload["subcategory"] = self.subcategory
        return payload


@dataclass(frozen=True)
class ServiceNowIncidentPublishResult:
    """Summary of a ServiceNow incident publish or dry run."""

    status_code: int | None
    sys_id: str | None
    number: str | None
    incident_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class ServiceNowIncidentPublisher:
    """Build and optionally create ServiceNow incidents from Max payloads."""

    def __init__(
        self,
        *,
        instance_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        bearer_token: str | None = None,
        impact: str = DEFAULT_IMPACT,
        urgency: str = DEFAULT_URGENCY,
        category: str = DEFAULT_CATEGORY,
        subcategory: str | None = None,
        contact_type: str = DEFAULT_CONTACT_TYPE,
        assignment_group: str | None = None,
        caller_id: str | None = None,
        cmdb_ci: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.instance_url = _normalize_instance_url(instance_url)
        self.username = _optional_text(username)
        self.password = _optional_text(password)
        self.bearer_token = _optional_text(bearer_token)
        self.impact = _required_text(impact, "ServiceNow incident impact is required")
        self.urgency = _required_text(urgency, "ServiceNow incident urgency is required")
        self.category = _required_text(category, "ServiceNow incident category is required")
        self.subcategory = _optional_text(subcategory)
        self.contact_type = _required_text(
            contact_type,
            "ServiceNow incident contact_type is required",
        )
        self.assignment_group = _optional_text(assignment_group)
        self.caller_id = _optional_text(caller_id)
        self.cmdb_ci = _optional_text(cmdb_ci)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        instance_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        bearer_token: str | None = None,
        impact: str | None = None,
        urgency: str | None = None,
        category: str | None = None,
        subcategory: str | None = None,
        contact_type: str | None = None,
        assignment_group: str | None = None,
        caller_id: str | None = None,
        cmdb_ci: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> ServiceNowIncidentPublisher:
        """Create a publisher using API values first, then environment variables."""
        return cls(
            instance_url=instance_url or os.getenv("SERVICENOW_INSTANCE_URL"),
            username=username or os.getenv("SERVICENOW_USERNAME"),
            password=password or os.getenv("SERVICENOW_PASSWORD"),
            bearer_token=(
                bearer_token
                or os.getenv("SERVICENOW_BEARER_TOKEN")
                or os.getenv("SERVICENOW_ACCESS_TOKEN")
            ),
            impact=impact or os.getenv("SERVICENOW_INCIDENT_IMPACT") or DEFAULT_IMPACT,
            urgency=urgency or os.getenv("SERVICENOW_INCIDENT_URGENCY") or DEFAULT_URGENCY,
            category=category or os.getenv("SERVICENOW_INCIDENT_CATEGORY") or DEFAULT_CATEGORY,
            subcategory=(
                subcategory
                if subcategory is not None
                else os.getenv("SERVICENOW_INCIDENT_SUBCATEGORY")
            ),
            contact_type=(
                contact_type
                or os.getenv("SERVICENOW_INCIDENT_CONTACT_TYPE")
                or DEFAULT_CONTACT_TYPE
            ),
            assignment_group=(
                assignment_group
                if assignment_group is not None
                else os.getenv("SERVICENOW_ASSIGNMENT_GROUP")
            ),
            caller_id=caller_id if caller_id is not None else os.getenv("SERVICENOW_CALLER_ID"),
            cmdb_ci=cmdb_ci if cmdb_ci is not None else os.getenv("SERVICENOW_CMDB_CI"),
            timeout=timeout,
            client=client,
        )

    @property
    def incident_endpoint(self) -> str:
        """Return the ServiceNow Table API endpoint used for Incident creation."""
        if not self.instance_url:
            return "/api/now/table/incident"
        return f"{self.instance_url}/api/now/table/incident"

    def build_incident_payload(self, tact_spec: dict[str, Any]) -> ServiceNowIncidentPayload:
        """Convert a generated TactSpec preview into a ServiceNow incident payload."""
        _validate_tact_spec(tact_spec)
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")
        quality = _dict_value(tact_spec, "quality")
        evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}

        source_type = str(source.get("type") or "idea")
        source_id = source.get("design_brief_id") or source.get("idea_id")
        metadata = {
            "publisher": "max.servicenow_incidents",
            "source_system": source.get("system", "max"),
            "source_type": source_type,
            "source_id": source_id,
            "idea_id": source.get("idea_id"),
            "design_brief_id": source.get("design_brief_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "impact": self.impact,
            "urgency": self.urgency,
        }

        return ServiceNowIncidentPayload(
            short_description=_incident_short_description(project.get("title"), source_id),
            description=_tact_spec_description(tact_spec, metadata),
            impact=self.impact,
            urgency=self.urgency,
            category=self.category,
            subcategory=self.subcategory,
            contact_type=self.contact_type,
            assignment_group=self.assignment_group,
            caller_id=self.caller_id,
            cmdb_ci=self.cmdb_ci,
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
    ) -> ServiceNowIncidentPayload:
        """Convert a persisted design brief into a ServiceNow incident payload."""
        brief = _brief_payload(design_brief)
        brief_id = _optional_text(brief.get("id"))
        source_idea_ids = _string_list(brief.get("source_idea_ids"))
        metadata = {
            "publisher": "max.servicenow_incidents",
            "source_system": "max",
            "source_type": "design_brief",
            "source_id": brief_id,
            "design_brief_id": brief_id,
            "lead_idea_id": brief.get("lead_idea_id"),
            "source_idea_ids": source_idea_ids,
            "schema_version": design_brief.get("schema_version") or "max.blueprint.source_brief.v1",
            "impact": self.impact,
            "urgency": self.urgency,
        }

        return ServiceNowIncidentPayload(
            short_description=_incident_short_description(
                title or brief.get("title"),
                brief_id,
            ),
            description=_design_brief_description(design_brief, markdown=markdown, metadata=metadata),
            impact=self.impact,
            urgency=self.urgency,
            category=self.category,
            subcategory=self.subcategory,
            contact_type=self.contact_type,
            assignment_group=self.assignment_group,
            caller_id=self.caller_id,
            cmdb_ci=self.cmdb_ci,
            metadata=metadata,
        )

    def publish(
        self,
        tact_spec: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> ServiceNowIncidentPublishResult:
        """Build the incident payload and optionally create it in ServiceNow."""
        return self._publish_payload(self.build_incident_payload(tact_spec).to_dict(), dry_run=dry_run)

    def publish_design_brief(
        self,
        design_brief: dict[str, Any],
        *,
        markdown: str | None = None,
        title: str | None = None,
        dry_run: bool = True,
    ) -> ServiceNowIncidentPublishResult:
        """Build a design brief incident payload and optionally create it in ServiceNow."""
        payload = self.build_design_brief_payload(
            design_brief,
            markdown=markdown,
            title=title,
        ).to_dict()
        return self._publish_payload(payload, dry_run=dry_run)

    def incident_url(self, sys_id: object, number: object | None = None) -> str:
        """Return a ServiceNow UI URL for the created incident."""
        if not self.instance_url:
            return f"/incident.do?sys_id={sys_id}"
        if number:
            return f"{self.instance_url}/nav_to.do?uri=incident.do?sysparm_query=number={number}"
        return f"{self.instance_url}/incident.do?sys_id={sys_id}"

    def _publish_payload(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool,
    ) -> ServiceNowIncidentPublishResult:
        if dry_run:
            return ServiceNowIncidentPublishResult(
                status_code=None,
                sys_id=None,
                number=None,
                incident_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self.instance_url:
            raise ServiceNowIncidentPublishError(
                "SERVICENOW_INSTANCE_URL is required for live ServiceNow incident publishing; "
                "use dry_run to preview",
                secrets=self._secrets,
            )
        if not self._has_auth:
            raise ServiceNowIncidentPublishError(
                "SERVICENOW_BEARER_TOKEN or SERVICENOW_USERNAME and SERVICENOW_PASSWORD are "
                "required for live ServiceNow incident publishing; use dry_run to preview",
                secrets=self._secrets,
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.incident_endpoint,
                    json=_servicenow_incident_request(payload),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                message = _redact_text(str(exc), secrets=self._secrets)
                raise ServiceNowIncidentPublishError(
                    f"ServiceNow incident publish failed for "
                    f"{_redact_url(self.incident_endpoint)}: {message}",
                    secrets=self._secrets,
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise ServiceNowIncidentPublishError(
                f"ServiceNow incident publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response, secrets=self._secrets)}",
                status_code=response.status_code,
                secrets=self._secrets,
            )

        body = _json_response(response, secrets=self._secrets)
        incident = body.get("result") if isinstance(body.get("result"), dict) else body
        sys_id = _optional_text(incident.get("sys_id"))
        if not sys_id:
            raise ServiceNowIncidentPublishError(
                "ServiceNow incident publish failed: response did not include incident sys_id",
                status_code=response.status_code,
                secrets=self._secrets,
            )
        number = _optional_text(incident.get("number"))
        incident_url = _optional_text(incident.get("link")) or self.incident_url(sys_id, number)
        metadata = {
            **payload["metadata"],
            "servicenow_incident_sys_id": sys_id,
            "servicenow_incident_url": incident_url,
        }
        if number:
            metadata["servicenow_incident_number"] = number

        return ServiceNowIncidentPublishResult(
            status_code=response.status_code,
            sys_id=sys_id,
            number=number,
            incident_url=incident_url,
            dry_run=False,
            payload={**payload, "metadata": metadata},
        )

    @property
    def _has_auth(self) -> bool:
        return bool(self.bearer_token or (self.username and self.password))

    @property
    def _secrets(self) -> list[str | None]:
        return [self.bearer_token, self.username, self.password]

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "max-servicenow-incidents-publisher/1",
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
            return headers
        assert self.username is not None and self.password is not None
        credentials = f"{self.username}:{self.password}".encode("utf-8")
        headers["Authorization"] = f"Basic {base64.b64encode(credentials).decode('ascii')}"
        return headers


ServiceNowIncidentsPublisher = ServiceNowIncidentPublisher


def _servicenow_incident_request(payload: dict[str, Any]) -> dict[str, Any]:
    request = {
        "short_description": payload["short_description"],
        "description": payload["description"],
        "impact": payload["impact"],
        "urgency": payload["urgency"],
        "category": payload["category"],
        "contact_type": payload["contact_type"],
    }
    for key in ("assignment_group", "caller_id", "cmdb_ci", "subcategory"):
        if payload.get(key):
            request[key] = payload[key]
    return request


def _validate_tact_spec(tact_spec: dict[str, Any]) -> None:
    if not isinstance(tact_spec, dict):
        raise ServiceNowIncidentPublishError(
            "ServiceNow incident publishing requires a TactSpec dict"
        )
    project = _dict_value(tact_spec, "project")
    source = _dict_value(tact_spec, "source")
    if not _optional_text(project.get("title")) and not (
        _optional_text(source.get("idea_id")) or _optional_text(source.get("design_brief_id"))
    ):
        raise ServiceNowIncidentPublishError(
            "ServiceNow incident publishing requires project.title or a source id"
        )
    if not _optional_text(tact_spec.get("schema_version")):
        raise ServiceNowIncidentPublishError(
            "ServiceNow incident publishing requires schema_version in the TactSpec payload"
        )


def _incident_short_description(title: object, source_id: object) -> str:
    base = str(title).strip() if title else str(source_id or "Generated TactSpec").strip()
    return f"[Max] {base}"[:160]


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
        f"- Source ideas: {_join_strings(evidence.get('source_idea_ids')) or 'None'}",
        "",
        "## Validation Plan",
        _text_or_placeholder(execution.get("validation_plan")),
        "",
        "## MVP Scope",
    ]
    lines.extend(_bullet_list(execution.get("mvp_scope")))
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
        raise ServiceNowIncidentPublishError(
            "ServiceNow incident publishing requires a design brief dict"
        )
    if not _optional_text(brief.get("title")) and not _optional_text(brief.get("id")):
        raise ServiceNowIncidentPublishError(
            "ServiceNow design brief incident publishing requires design_brief.title or id"
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


def _bullet_list(items: object) -> list[str]:
    if not isinstance(items, list) or not items:
        return ["- None"]
    return [f"- {item}" for item in items if item] or ["- None"]


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


def _normalize_instance_url(instance_url: str | None) -> str | None:
    raw = _optional_text(instance_url)
    if not raw:
        return None
    if "://" not in raw:
        raw = f"https://{raw}"
    raw = raw.rstrip("/")
    if raw.endswith("/api/now/table/incident"):
        raw = raw[: -len("/api/now/table/incident")]
    parts = urlsplit(raw)
    if not parts.scheme or not parts.netloc:
        raise ServiceNowIncidentPublishError(
            "ServiceNow instance_url must be an absolute URL or instance host"
        )
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value else ""
    if not text:
        raise ServiceNowIncidentPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


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
        raise ServiceNowIncidentPublishError(
            "ServiceNow incident publish failed: response was not valid JSON",
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
        r"(?i)\b(token|api_token|api_key|password|secret|authorization)\b"
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
