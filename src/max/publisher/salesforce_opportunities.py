"""Salesforce Opportunity publisher for Max ideas and design briefs."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

DEFAULT_API_VERSION = "v60.0"
DEFAULT_STAGE = "Prospecting"
DEFAULT_TIMEOUT_SECONDS = 10.0


class SalesforceOpportunityPublishError(RuntimeError):
    """Raised when a Salesforce Opportunity publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None, secrets: list[str | None] | None = None) -> None:
        super().__init__(_redact_text(message, secrets=secrets))
        self.status_code = status_code


@dataclass(frozen=True)
class SalesforceOpportunityPublishResult:
    """Summary of a Salesforce Opportunity publish or dry run."""

    status_code: int | None
    opportunity_id: str | None
    opportunity_url: str | None
    dry_run: bool
    method: str
    endpoint: str
    payload: dict[str, Any]


class SalesforceOpportunityPublisher:
    """Build and optionally create or upsert Salesforce Opportunities."""

    def __init__(
        self,
        *,
        instance_url: str | None = None,
        access_token: str | None = None,
        api_version: str = DEFAULT_API_VERSION,
        default_stage: str = DEFAULT_STAGE,
        close_date: str | None = None,
        amount: int | float | str | None = None,
        external_id_field: str | None = None,
        external_id_value: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.instance_url = _normalize_instance_url(instance_url)
        self.access_token = _optional_text(access_token)
        self.api_version = _normalize_api_version(api_version)
        self.default_stage = _required_text(default_stage, "Salesforce Opportunity stage is required")
        self.close_date = _optional_text(close_date)
        self.amount = _amount_value(amount)
        self.external_id_field = _optional_text(external_id_field)
        self.external_id_value = _optional_text(external_id_value)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        instance_url: str | None = None,
        access_token: str | None = None,
        api_version: str | None = None,
        default_stage: str | None = None,
        close_date: str | None = None,
        amount: int | float | str | None = None,
        external_id_field: str | None = None,
        external_id_value: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> SalesforceOpportunityPublisher:
        return cls(
            instance_url=instance_url or os.getenv("SALESFORCE_INSTANCE_URL"),
            access_token=access_token or os.getenv("SALESFORCE_ACCESS_TOKEN"),
            api_version=api_version or os.getenv("SALESFORCE_API_VERSION") or DEFAULT_API_VERSION,
            default_stage=default_stage or os.getenv("SALESFORCE_OPPORTUNITY_STAGE") or DEFAULT_STAGE,
            close_date=close_date or os.getenv("SALESFORCE_OPPORTUNITY_CLOSE_DATE"),
            amount=amount if amount is not None else os.getenv("SALESFORCE_OPPORTUNITY_AMOUNT"),
            external_id_field=external_id_field or os.getenv("SALESFORCE_OPPORTUNITY_EXTERNAL_ID_FIELD"),
            external_id_value=external_id_value or os.getenv("SALESFORCE_OPPORTUNITY_EXTERNAL_ID_VALUE"),
            timeout=timeout,
            client=client,
        )

    @property
    def create_endpoint(self) -> str:
        return f"{self._base_endpoint}/sobjects/Opportunity"

    def upsert_endpoint(self, field: str, value: str) -> str:
        return f"{self.create_endpoint}/{quote(field)}/{quote(value)}"

    def build_opportunity_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if _is_design_brief_payload(payload):
            fields = _design_brief_fields(payload)
        else:
            fields = _idea_fields(payload)
        fields["StageName"] = fields.get("StageName") or self.default_stage
        fields["CloseDate"] = fields.get("CloseDate") or self.close_date or _default_close_date()
        if self.amount is not None:
            fields["Amount"] = self.amount
        return fields

    def publish(self, payload: dict[str, Any], *, dry_run: bool = True) -> SalesforceOpportunityPublishResult:
        opportunity_payload = self.build_opportunity_payload(payload)
        method, endpoint = self._method_and_endpoint(payload)
        if dry_run:
            return SalesforceOpportunityPublishResult(None, None, None, True, method, endpoint, opportunity_payload)
        if not self.instance_url or not self.access_token:
            raise SalesforceOpportunityPublishError(
                "SALESFORCE_INSTANCE_URL and SALESFORCE_ACCESS_TOKEN are required for live Salesforce Opportunity publishing; use dry_run to preview",
                secrets=self._secrets,
            )
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.request(
                method,
                endpoint,
                json=opportunity_payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise SalesforceOpportunityPublishError(f"Salesforce Opportunity publish failed for {_redact_url(endpoint)}: {exc}", secrets=self._secrets) from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise SalesforceOpportunityPublishError(
                f"Salesforce Opportunity publish failed with HTTP {response.status_code}: {_response_body_preview(response, secrets=self._secrets)}",
                status_code=response.status_code,
                secrets=self._secrets,
            )
        body = _json_response(response, secrets=self._secrets)
        opportunity_id = _opportunity_id(body)
        return SalesforceOpportunityPublishResult(
            response.status_code,
            opportunity_id,
            self.opportunity_url(opportunity_id) if opportunity_id else None,
            False,
            method,
            endpoint,
            opportunity_payload,
        )

    def opportunity_url(self, opportunity_id: object) -> str:
        if not self.instance_url:
            return f"/{opportunity_id}"
        return f"{self.instance_url}/{opportunity_id}"

    def _method_and_endpoint(self, payload: dict[str, Any]) -> tuple[str, str]:
        field = self.external_id_field
        value = self.external_id_value or _source_id(payload)
        if field and value:
            return "PATCH", self.upsert_endpoint(field, value)
        return "POST", self.create_endpoint

    @property
    def _base_endpoint(self) -> str:
        if not self.instance_url:
            return f"/services/data/{self.api_version}"
        return f"{self.instance_url}/services/data/{self.api_version}"

    @property
    def _secrets(self) -> list[str | None]:
        return [self.access_token]

    def _headers(self) -> dict[str, str]:
        assert self.access_token is not None
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "max-salesforce-opportunities-publisher/1",
        }


def publish_salesforce_opportunity(
    payload: dict[str, Any],
    *,
    instance_url: str | None = None,
    access_token: str | None = None,
    api_version: str | None = None,
    default_stage: str | None = None,
    close_date: str | None = None,
    amount: int | float | str | None = None,
    external_id_field: str | None = None,
    external_id_value: str | None = None,
    dry_run: bool = True,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    client: httpx.Client | None = None,
) -> SalesforceOpportunityPublishResult:
    """Create or upsert a Salesforce Opportunity from a Max payload."""
    return SalesforceOpportunityPublisher.from_env(
        instance_url=instance_url,
        access_token=access_token,
        api_version=api_version,
        default_stage=default_stage,
        close_date=close_date,
        amount=amount,
        external_id_field=external_id_field,
        external_id_value=external_id_value,
        timeout=timeout,
        client=client,
    ).publish(payload, dry_run=dry_run)


def _idea_fields(payload: dict[str, Any]) -> dict[str, Any]:
    source = _dict_value(payload, "source")
    project = _dict_value(payload, "project")
    return {
        "Name": _truncate(_text(project.get("title"), source.get("idea_id"), "Max Idea Opportunity"), 120),
        "Description": _render_idea_description(payload),
    }


def _design_brief_fields(payload: dict[str, Any]) -> dict[str, Any]:
    brief = _dict_value(payload, "design_brief")
    return {
        "Name": _truncate(_text(brief.get("title"), brief.get("id"), "Max Design Brief Opportunity"), 120),
        "Description": _render_design_brief_description(payload),
    }


def _render_idea_description(payload: dict[str, Any]) -> str:
    source = _dict_value(payload, "source")
    project = _dict_value(payload, "project")
    problem = _dict_value(payload, "problem")
    solution = _dict_value(payload, "solution")
    evidence = _dict_value(payload, "evidence")
    evaluation = _dict_value(payload, "evaluation")
    return "\n".join(
        [
            _text(project.get("summary"), "No summary provided."),
            "",
            f"Idea ID: {_text(source.get('idea_id'), 'Not specified')}",
            f"Score: {_score_text(evaluation.get('overall_score'))}",
            f"Recommendation: {_text(evaluation.get('recommendation'), 'Not specified')}",
            "",
            f"Problem: {_text(problem.get('statement'), 'Not specified')}",
            f"Solution: {_text(solution.get('approach'), 'Not specified')}",
            f"Evidence: {_text(evidence.get('rationale'), 'Not specified')}",
            f"Signals: {_comma_list(_string_list(evidence.get('signal_ids')))}",
        ]
    )


def _render_design_brief_description(payload: dict[str, Any]) -> str:
    brief = _dict_value(payload, "design_brief")
    evidence_refs = _dict_value(payload, "evidence_refs")
    return "\n".join(
        [
            _text(brief.get("summary"), brief.get("merged_product_concept"), "No concept provided."),
            "",
            f"Brief ID: {_text(brief.get('id'), 'Not specified')}",
            f"Readiness score: {_score_text(brief.get('readiness_score'))}",
            f"Recommendation: {_text(brief.get('recommendation') or brief.get('status_recommendation'), 'Not specified')}",
            f"Source idea ids: {_comma_list(_string_list(brief.get('source_idea_ids')))}",
            f"Insight ids: {_comma_list(_string_list(evidence_refs.get('insight_ids')))}",
            f"Signal ids: {_comma_list(_string_list(evidence_refs.get('signal_ids')))}",
            "",
            _text(brief.get("validation_plan"), "No validation plan provided."),
        ]
    )


def _source_id(payload: dict[str, Any]) -> str | None:
    if _is_design_brief_payload(payload):
        brief = _dict_value(payload, "design_brief")
        return _optional_text(brief.get("id"))
    source = _dict_value(payload, "source")
    return _optional_text(source.get("idea_id"))


def _is_design_brief_payload(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("design_brief"), dict)


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _string_list(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    return [_text(item, "") for item in items if _text(item, "")]


def _comma_list(items: list[str]) -> str:
    return ", ".join(items) if items else "None"


def _text(*values: object) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _required_text(value: object, message: str) -> str:
    text = _text(value)
    if not text:
        raise SalesforceOpportunityPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = _text(value)
    return text or None


def _score_text(value: object) -> str:
    if isinstance(value, int | float):
        return f"{value:.1f}"
    return _text(value, "Not specified")


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _amount_value(value: int | float | str | None) -> int | float | None:
    if value is None or value == "":
        return None
    if isinstance(value, int | float):
        return value
    number = float(str(value))
    return int(number) if number.is_integer() else number


def _default_close_date() -> str:
    return (date.today() + timedelta(days=30)).isoformat()


def _normalize_instance_url(instance_url: str | None) -> str | None:
    raw = _optional_text(instance_url)
    if not raw:
        return None
    if "://" not in raw:
        raw = f"https://{raw}"
    parts = urlsplit(raw.rstrip("/"))
    if not parts.scheme or not parts.netloc:
        raise SalesforceOpportunityPublishError("Salesforce instance_url must be an absolute URL")
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _normalize_api_version(api_version: str | None) -> str:
    version = _required_text(api_version or DEFAULT_API_VERSION, "Salesforce API version is required").strip("/")
    if version.startswith("services/data/"):
        version = version.removeprefix("services/data/").split("/", 1)[0]
    if not version.startswith("v"):
        version = f"v{version}"
    return version


def _opportunity_id(body: dict[str, Any]) -> str | None:
    value = body.get("id") or body.get("Id") or body.get("opportunity_id") or body.get("opportunityId")
    return str(value) if value is not None else None


def _json_response(response: httpx.Response, *, secrets: list[str | None]) -> dict[str, Any]:
    if not response.content:
        return {}
    try:
        body = response.json()
    except ValueError as exc:
        raise SalesforceOpportunityPublishError("Salesforce Opportunity response was not valid JSON", status_code=response.status_code, secrets=secrets) from exc
    return body if isinstance(body, dict) else {}


def _response_body_preview(response: httpx.Response, *, secrets: list[str | None], limit: int = 500) -> str:
    text = _redact_text(response.text.strip(), secrets=secrets)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _redact_text(text: str, *, secrets: list[str | None] | None = None) -> str:
    redacted = text
    for secret in secrets or []:
        if secret:
            redacted = redacted.replace(secret, "<redacted>")
    return re.sub(r"(?i)\b(access_token|token|password|authorization|client_secret)\b([=:]\s*)[^&\s,'\"}]+", r"\1\2<redacted>", _redact_url(redacted))


def _redact_url(text: str) -> str:
    words = text.split()
    return " ".join(_redact_url_word(word) for word in words)


def _redact_url_word(word: str) -> str:
    if "://" not in word:
        return word
    parts = urlsplit(word)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
