"""Salesforce Case publisher for generated TactSpecs."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx


DEFAULT_API_VERSION = "v60.0"
DEFAULT_CASE_ORIGIN = "Max"
DEFAULT_CASE_PRIORITY = "Medium"
DEFAULT_CASE_STATUS = "New"
DEFAULT_TIMEOUT_SECONDS = 10.0
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


class SalesforceCasePublishError(RuntimeError):
    """Raised when a Salesforce Case publish cannot be completed."""

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
class SalesforceCasePayload:
    """Salesforce Case creation payload plus Max-specific metadata."""

    subject: str
    description: str
    origin: str
    priority: str
    status: str
    metadata: dict[str, Any]
    account_id: str | None = None
    contact_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable Salesforce Case payload preview."""
        payload: dict[str, Any] = {
            "Subject": self.subject,
            "Description": self.description,
            "Origin": self.origin,
            "Priority": self.priority,
            "Status": self.status,
            "metadata": self.metadata,
        }
        if self.account_id:
            payload["AccountId"] = self.account_id
        if self.contact_id:
            payload["ContactId"] = self.contact_id
        return payload


@dataclass(frozen=True)
class SalesforceCasePublishResult:
    """Summary of a Salesforce Case publish or dry run."""

    status_code: int | None
    case_id: str | None
    case_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class SalesforceCasePublisher:
    """Build and optionally create Salesforce Cases from TactSpec previews."""

    def __init__(
        self,
        *,
        instance_url: str | None = None,
        access_token: str | None = None,
        api_version: str = DEFAULT_API_VERSION,
        origin: str = DEFAULT_CASE_ORIGIN,
        priority: str = DEFAULT_CASE_PRIORITY,
        status: str = DEFAULT_CASE_STATUS,
        account_id: str | None = None,
        contact_id: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.instance_url = _normalize_instance_url(instance_url)
        self.access_token = _optional_text(access_token)
        self.api_version = _normalize_api_version(api_version)
        self.origin = _required_text(origin, "Salesforce Case origin is required")
        self.priority = _required_text(priority, "Salesforce Case priority is required")
        self.status = _required_text(status, "Salesforce Case status is required")
        self.account_id = _optional_text(account_id)
        self.contact_id = _optional_text(contact_id)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        instance_url: str | None = None,
        access_token: str | None = None,
        api_version: str | None = None,
        origin: str | None = None,
        priority: str | None = None,
        status: str | None = None,
        account_id: str | None = None,
        contact_id: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> SalesforceCasePublisher:
        """Create a publisher using API values first, then environment variables."""
        return cls(
            instance_url=instance_url or os.getenv("SALESFORCE_INSTANCE_URL"),
            access_token=access_token or os.getenv("SALESFORCE_ACCESS_TOKEN"),
            api_version=api_version or os.getenv("SALESFORCE_API_VERSION") or DEFAULT_API_VERSION,
            origin=origin or os.getenv("SALESFORCE_CASE_ORIGIN") or DEFAULT_CASE_ORIGIN,
            priority=priority or os.getenv("SALESFORCE_CASE_PRIORITY") or DEFAULT_CASE_PRIORITY,
            status=status or os.getenv("SALESFORCE_CASE_STATUS") or DEFAULT_CASE_STATUS,
            account_id=account_id if account_id is not None else os.getenv("SALESFORCE_ACCOUNT_ID"),
            contact_id=contact_id if contact_id is not None else os.getenv("SALESFORCE_CONTACT_ID"),
            timeout=timeout,
            client=client,
        )

    @property
    def case_endpoint(self) -> str:
        """Return the Salesforce REST endpoint used for Case creation."""
        if not self.instance_url:
            return f"/services/data/{self.api_version}/sobjects/Case"
        return f"{self.instance_url}/services/data/{self.api_version}/sobjects/Case"

    def build_case_payload(self, tact_spec: dict[str, Any]) -> SalesforceCasePayload:
        """Convert a generated TactSpec preview into a Salesforce Case payload."""
        _validate_tact_spec(tact_spec)
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")

        source_type = str(source.get("type") or "idea")
        source_id = source.get("design_brief_id") or source.get("idea_id")
        metadata = {
            "publisher": "max.salesforce_cases",
            "source_system": source.get("system", "max"),
            "source_type": source_type,
            "source_id": source_id,
            "idea_id": source.get("idea_id"),
            "design_brief_id": source.get("design_brief_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "account_id": self.account_id,
            "contact_id": self.contact_id,
        }

        return SalesforceCasePayload(
            subject=_case_subject(project.get("title"), source_id),
            description=_case_description(tact_spec, metadata),
            origin=self.origin,
            priority=self.priority,
            status=self.status,
            account_id=self.account_id,
            contact_id=self.contact_id,
            metadata=metadata,
        )

    def publish(
        self,
        tact_spec: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> SalesforceCasePublishResult:
        """Build the Case payload and optionally create it in Salesforce."""
        payload = self.build_case_payload(tact_spec).to_dict()
        if dry_run:
            return SalesforceCasePublishResult(
                status_code=None,
                case_id=None,
                case_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self.instance_url or not self.access_token:
            raise SalesforceCasePublishError(
                "SALESFORCE_INSTANCE_URL and SALESFORCE_ACCESS_TOKEN are required for live "
                "Salesforce Case publishing; use dry_run to preview",
                secrets=self._secrets,
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.case_endpoint,
                    json=_salesforce_case_request(payload),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                message = _redact_text(str(exc), secrets=self._secrets)
                raise SalesforceCasePublishError(
                    f"Salesforce Case publish failed for "
                    f"{_redact_url(self.case_endpoint)}: {message}",
                    secrets=self._secrets,
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise SalesforceCasePublishError(
                f"Salesforce Case publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response, secrets=self._secrets)}",
                status_code=response.status_code,
                secrets=self._secrets,
            )

        body = _json_response(response, secrets=self._secrets)
        case_id = _case_id_from_response(body)
        case_url = self.case_url(case_id) if case_id else None
        metadata = dict(payload["metadata"])
        if case_id:
            metadata["salesforce_case_id"] = case_id
        if case_url:
            metadata["salesforce_case_url"] = case_url
        return SalesforceCasePublishResult(
            status_code=response.status_code,
            case_id=case_id,
            case_url=case_url,
            dry_run=False,
            payload={**payload, "metadata": metadata},
        )

    def case_url(self, case_id: object) -> str:
        """Return the Salesforce UI URL for a Case id."""
        if not self.instance_url:
            return f"/{case_id}"
        return f"{self.instance_url}/{case_id}"

    @property
    def _secrets(self) -> list[str | None]:
        return [self.access_token]

    def _headers(self) -> dict[str, str]:
        assert self.access_token is not None
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "max-salesforce-cases-publisher/1",
        }


SalesforceCasesPublisher = SalesforceCasePublisher


def _salesforce_case_request(payload: dict[str, Any]) -> dict[str, Any]:
    request = {
        "Subject": payload["Subject"],
        "Description": payload["Description"],
        "Origin": payload["Origin"],
        "Priority": payload["Priority"],
        "Status": payload["Status"],
    }
    if payload.get("AccountId"):
        request["AccountId"] = payload["AccountId"]
    if payload.get("ContactId"):
        request["ContactId"] = payload["ContactId"]
    return request


def _validate_tact_spec(tact_spec: dict[str, Any]) -> None:
    if not isinstance(tact_spec, dict):
        raise SalesforceCasePublishError("Salesforce Case publishing requires a TactSpec dict")
    project = _dict_value(tact_spec, "project")
    source = _dict_value(tact_spec, "source")
    if not _optional_text(project.get("title")) and not (
        _optional_text(source.get("idea_id")) or _optional_text(source.get("design_brief_id"))
    ):
        raise SalesforceCasePublishError(
            "Salesforce Case publishing requires project.title or a source id"
        )
    if not _optional_text(tact_spec.get("schema_version")):
        raise SalesforceCasePublishError(
            "Salesforce Case publishing requires schema_version in the TactSpec payload"
        )


def _case_subject(title: object, source_id: object) -> str:
    base = str(title).strip() if title else str(source_id or "Generated TactSpec").strip()
    return f"[Max] Customer ops handoff: {base}"[:255]


def _case_description(tact_spec: dict[str, Any], metadata: dict[str, Any]) -> str:
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
        "## Customer Context",
        f"- Target users: {_text_or_placeholder(project.get('target_users'))}",
        f"- Domain: {_text_or_placeholder(source.get('domain'))}",
        f"- Category: {_text_or_placeholder(source.get('category'))}",
        f"- Status: {_text_or_placeholder(source.get('status'))}",
        "",
        "## Problem",
        _text_or_placeholder(problem.get("statement")),
        "",
        "## Proposed Solution",
        _text_or_placeholder(solution.get("approach")),
        "",
        "## Commercial Handoff",
        f"- Recommendation: {_text_or_placeholder(evaluation.get('recommendation'))}",
        f"- Overall score: {_score_text(evaluation.get('overall_score'))}",
        f"- Validation plan: {_text_or_placeholder(execution.get('validation_plan'))}",
        "",
        "## MVP Scope",
    ]
    lines.extend(_bullet_list(execution.get("mvp_scope")))
    lines.extend(
        [
            "",
            "## Evidence Chain",
            f"- Rationale: {_text_or_placeholder(evidence.get('rationale'))}",
            f"- Insights: {', '.join(evidence.get('insight_ids') or []) or 'None'}",
            f"- Signals: {', '.join(evidence.get('signal_ids') or []) or 'None'}",
            f"- Source ideas: {', '.join(evidence.get('source_idea_ids') or []) or 'None'}",
            "",
            "## Max Metadata",
            "```json",
            json.dumps(metadata, indent=2, sort_keys=True),
            "```",
        ]
    )
    return "\n".join(lines)


def _case_id_from_response(body: dict[str, Any]) -> str | None:
    value = body.get("id") or body.get("Id") or body.get("case_id") or body.get("caseId")
    return str(value) if value is not None else None


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


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value else ""
    if not text:
        raise SalesforceCasePublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _normalize_instance_url(instance_url: str | None) -> str | None:
    raw = _optional_text(instance_url)
    if not raw:
        return None
    if "://" not in raw:
        raw = f"https://{raw}"
    parts = urlsplit(raw.rstrip("/"))
    if not parts.scheme or not parts.netloc:
        raise SalesforceCasePublishError("Salesforce instance_url must be an absolute URL")
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _normalize_api_version(api_version: str | None) -> str:
    version = _required_text(api_version or DEFAULT_API_VERSION, "Salesforce API version is required")
    version = version.strip().strip("/")
    if version.startswith("services/data/"):
        version = version.removeprefix("services/data/").split("/", 1)[0]
    if not version.startswith("v"):
        version = f"v{version}"
    return version


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
    if not response.content:
        return {}
    try:
        body = response.json()
    except ValueError as exc:
        raise SalesforceCasePublishError(
            "Salesforce Case publish failed: response was not valid JSON",
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
        r"(?i)\b(access_token|token|password|secret|authorization|client_secret)\b([=:]\s*)"
        r"[^&\s,'\"}]+",
        r"\1\2<redacted>",
        redacted,
    )
    return _redact_url(redacted)


def _redact_url(text: str) -> str:
    words = text.split()
    return " ".join(_redact_url_word(word) for word in words)


def _redact_url_word(word: str) -> str:
    prefix = ""
    suffix = ""
    while word and word[0] in "([{'\"":
        prefix += word[0]
        word = word[1:]
    while word and word[-1] in ")]}'\",.":
        suffix = word[-1] + suffix
        word = word[:-1]
    if "://" not in word:
        return prefix + word + suffix
    parts = urlsplit(word)
    if not parts.query:
        return prefix + word + suffix
    query = [
        (key, "<redacted>" if key.lower() in SECRET_QUERY_KEYS else value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
    ]
    redacted = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    return prefix + redacted + suffix
