"""Airtable record publisher for Max ideas and design briefs."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from max.types.buildable_unit import BuildableUnit


DEFAULT_AIRTABLE_API_URL = "https://api.airtable.com"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 2
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
REDACTED = "[REDACTED]"


class AirtableRecordPublishError(RuntimeError):
    """Raised when an Airtable record publish cannot be completed."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(_redact_text(message, api_key=api_key))
        self.status_code = status_code


@dataclass(frozen=True)
class AirtableRecordPayload:
    """Airtable record creation payload plus Max-specific metadata."""

    fields: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable Airtable record payload preview."""
        return {
            "fields": self.fields,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class AirtableRecordPublishResult:
    """Summary of an Airtable record publish or dry run."""

    status_code: int | None
    base_id: str
    table: str
    record_id: str | None
    record_url: str | None
    dry_run: bool
    payload: dict[str, Any]
    attempts: list[dict[str, Any]]


class AirtableRecordPublisher:
    """Build and optionally create Airtable records from Max ideas or design briefs."""

    def __init__(
        self,
        base_id: str,
        table: str,
        *,
        api_key: str | None = None,
        api_url: str = DEFAULT_AIRTABLE_API_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = 0.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_id = _required_text(
            base_id,
            "Airtable base_id is required",
            api_key=api_key,
        )
        self.table = _required_text(
            table,
            "Airtable table is required",
            api_key=api_key,
        )
        self.api_key = _optional_text(api_key)
        self.api_url = _required_url(api_url, api_key=api_key)
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.retry_backoff = max(0.0, retry_backoff)
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        base_id: str | None = None,
        table: str | None = None,
        api_key: str | None = None,
        api_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        client: httpx.Client | None = None,
    ) -> AirtableRecordPublisher:
        """Create a publisher using explicit values first, then environment variables."""
        resolved_base_id = base_id or os.getenv("AIRTABLE_BASE_ID")
        if not resolved_base_id:
            raise AirtableRecordPublishError(
                "Airtable base_id is required; pass base_id or set AIRTABLE_BASE_ID",
                api_key=api_key,
            )
        resolved_table = table or os.getenv("AIRTABLE_TABLE") or os.getenv("AIRTABLE_TABLE_ID")
        if not resolved_table:
            raise AirtableRecordPublishError(
                "Airtable table is required; pass table or set AIRTABLE_TABLE",
                api_key=api_key,
            )
        return cls(
            resolved_base_id,
            resolved_table,
            api_key=api_key or os.getenv("AIRTABLE_API_KEY") or os.getenv("AIRTABLE_TOKEN"),
            api_url=api_url or os.getenv("AIRTABLE_API_URL", DEFAULT_AIRTABLE_API_URL),
            timeout=timeout,
            max_retries=max_retries,
            client=client,
        )

    @property
    def records_endpoint(self) -> str:
        """Return the Airtable records REST endpoint."""
        base_id = quote(self.base_id, safe="")
        table = quote(self.table, safe="")
        return f"{self.api_url}/v0/{base_id}/{table}"

    @property
    def has_auth(self) -> bool:
        """Return whether live Airtable publishing has credentials."""
        return bool(self.api_key)

    def record_url(self, record_id: str) -> str:
        """Return an Airtable UI URL for a created record."""
        base_id = quote(self.base_id, safe="")
        table = quote(self.table, safe="")
        record = quote(record_id, safe="")
        return f"https://airtable.com/{base_id}/{table}/{record}"

    def build_idea_payload(
        self,
        idea_or_spec: BuildableUnit | dict[str, Any],
        spec_preview: dict[str, Any] | None = None,
    ) -> AirtableRecordPayload:
        """Convert a BuildableUnit or generated TactSpec preview into Airtable fields."""
        tact_spec = _coerce_tact_spec(idea_or_spec, spec_preview)
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")
        problem = _dict_value(tact_spec, "problem")
        solution = _dict_value(tact_spec, "solution")
        execution = _dict_value(tact_spec, "execution")
        evidence = _dict_value(tact_spec, "evidence")
        quality = _dict_value(tact_spec, "quality")
        evaluation = (
            tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}
        )

        source_id = _optional_text(source.get("idea_id"))
        fields = _clean_fields(
            {
                "Record Type": "Idea",
                "Title": _title(project.get("title"), source_id),
                "Source ID": source_id,
                "Source Type": _optional_text(source.get("type")) or "idea",
                "Status": _optional_text(source.get("status")),
                "Domain": _optional_text(source.get("domain")),
                "Category": _optional_text(source.get("category")),
                "Summary": _optional_text(project.get("summary")),
                "Problem": _optional_text(problem.get("statement")),
                "Solution": _optional_text(solution.get("approach")),
                "Target Users": _optional_text(project.get("target_users")),
                "Validation Plan": _optional_text(execution.get("validation_plan")),
                "Recommendation": _optional_text(evaluation.get("recommendation")),
                "Overall Score": _number_or_text(evaluation.get("overall_score")),
                "Quality Score": _number_or_text(quality.get("quality_score")),
                "Novelty Score": _number_or_text(quality.get("novelty_score")),
                "Usefulness Score": _number_or_text(quality.get("usefulness_score")),
                "Source Idea IDs": _join_strings(evidence.get("source_idea_ids")),
            }
        )
        metadata = {
            "publisher": "max.airtable_records",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "idea"),
            "idea_id": source_id,
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "base_id": self.base_id,
            "table": self.table,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return AirtableRecordPayload(fields=fields, metadata=metadata)

    def build_design_brief_payload(
        self,
        design_brief: dict[str, Any],
        *,
        markdown: str | None = None,
        title: str | None = None,
    ) -> AirtableRecordPayload:
        """Convert a persisted design brief into Airtable fields."""
        brief = _brief_payload(design_brief)
        source_ideas = _source_ideas(design_brief)
        brief_id = _optional_text(brief.get("id"))
        source_ids = _string_list(brief.get("source_idea_ids"))
        readiness_score = _number_or_text(brief.get("readiness_score"))

        fields = _clean_fields(
            {
                "Record Type": "Design Brief",
                "Title": _title(title, brief.get("title"), brief_id, "Design Brief"),
                "Source ID": brief_id,
                "Source Type": "design_brief",
                "Status": _optional_text(brief.get("design_status") or brief.get("status")),
                "Domain": _optional_text(brief.get("domain")),
                "Theme": _optional_text(brief.get("theme")),
                "Summary": _optional_text(
                    brief.get("merged_product_concept")
                    or brief.get("synthesis_rationale")
                    or brief.get("why_this_now")
                ),
                "Problem": _optional_text(_lead_source_value(source_ideas, "problem")),
                "Solution": _optional_text(
                    _lead_source_value(source_ideas, "solution")
                    or brief.get("merged_product_concept")
                ),
                "Lead Idea ID": _optional_text(brief.get("lead_idea_id")),
                "Source Idea IDs": ", ".join(source_ids) or None,
                "Readiness Score": readiness_score,
                "Validation Plan": _optional_text(brief.get("validation_plan")),
                "Markdown": _optional_text(markdown),
            }
        )
        metadata = {
            "publisher": "max.airtable_records",
            "source_system": "max",
            "source_type": "design_brief",
            "design_brief_id": brief_id,
            "lead_idea_id": brief.get("lead_idea_id"),
            "source_idea_ids": source_ids,
            "schema_version": design_brief.get("schema_version") or "max.blueprint.source_brief.v1",
            "base_id": self.base_id,
            "table": self.table,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return AirtableRecordPayload(fields=fields, metadata=metadata)

    def publish(
        self,
        idea_or_spec: BuildableUnit | dict[str, Any],
        *,
        spec_preview: dict[str, Any] | None = None,
        dry_run: bool = True,
    ) -> AirtableRecordPublishResult:
        """Build the idea record payload and optionally create it in Airtable."""
        payload = self.build_idea_payload(idea_or_spec, spec_preview).to_dict()
        return self.publish_payload(payload, dry_run=dry_run)

    def publish_design_brief(
        self,
        design_brief: dict[str, Any],
        *,
        markdown: str | None = None,
        title: str | None = None,
        dry_run: bool = True,
    ) -> AirtableRecordPublishResult:
        """Build the design brief record payload and optionally create it in Airtable."""
        payload = self.build_design_brief_payload(
            design_brief,
            markdown=markdown,
            title=title,
        ).to_dict()
        return self.publish_payload(payload, dry_run=dry_run)

    def publish_payload(
        self,
        payload: AirtableRecordPayload | dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> AirtableRecordPublishResult:
        """Create an Airtable record from a prebuilt payload."""
        payload_dict = (
            payload.to_dict() if isinstance(payload, AirtableRecordPayload) else dict(payload)
        )
        if dry_run:
            return AirtableRecordPublishResult(
                status_code=None,
                base_id=self.base_id,
                table=self.table,
                record_id=None,
                record_url=None,
                dry_run=True,
                payload=payload_dict,
                attempts=[],
            )

        if not self.api_key:
            raise AirtableRecordPublishError(
                "AIRTABLE_API_KEY is required for live Airtable record publishing; "
                "use dry_run to preview",
                api_key=self.api_key,
            )

        attempts: list[dict[str, Any]] = []
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = self._post_with_retries(client, payload_dict, attempts)
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise AirtableRecordPublishError(
                f"Airtable record publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response, api_key=self.api_key)}",
                status_code=response.status_code,
                api_key=self.api_key,
            )

        body = _json_response(response, api_key=self.api_key)
        record_id = _optional_text(body.get("id"))
        if not record_id:
            raise AirtableRecordPublishError(
                "Airtable record publish failed: response did not include created record id",
                status_code=response.status_code,
                api_key=self.api_key,
            )

        record_url = self.record_url(record_id)
        return AirtableRecordPublishResult(
            status_code=response.status_code,
            base_id=self.base_id,
            table=self.table,
            record_id=record_id,
            record_url=record_url,
            dry_run=False,
            payload={
                **payload_dict,
                "metadata": {
                    **(payload_dict.get("metadata") or {}),
                    "airtable_record_id": record_id,
                    "airtable_record_url": record_url,
                    "airtable_created_time": body.get("createdTime"),
                },
            },
            attempts=attempts,
        )

    def _post_with_retries(
        self,
        client: httpx.Client,
        payload: dict[str, Any],
        attempts: list[dict[str, Any]],
    ) -> httpx.Response:
        last_response: httpx.Response | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = client.post(
                    self.records_endpoint,
                    json={"fields": payload["fields"]},
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "User-Agent": "max-airtable-records-publisher/1",
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                attempts.append(
                    _attempt(self.records_endpoint, error=str(exc), api_key=self.api_key)
                )
                raise AirtableRecordPublishError(
                    "Airtable record publish failed for "
                    f"{_redact_url(self.records_endpoint)}: {exc}",
                    api_key=self.api_key,
                ) from exc

            attempts.append(_attempt(self.records_endpoint, status_code=response.status_code))
            last_response = response
            if response.status_code not in TRANSIENT_STATUS_CODES or attempt >= self.max_retries:
                return response
            if self.retry_backoff:
                time.sleep(self.retry_backoff * (attempt + 1))

        return last_response


AirtableRecordsPublisher = AirtableRecordPublisher


def _coerce_tact_spec(
    idea_or_spec: BuildableUnit | dict[str, Any],
    spec_preview: dict[str, Any] | None,
) -> dict[str, Any]:
    if spec_preview is not None:
        return spec_preview
    if isinstance(idea_or_spec, BuildableUnit):
        return {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {
                "system": "max",
                "type": "idea",
                "idea_id": idea_or_spec.id,
                "status": idea_or_spec.status,
                "domain": idea_or_spec.domain,
                "category": idea_or_spec.category,
                "created_at": idea_or_spec.created_at.isoformat(),
                "updated_at": idea_or_spec.updated_at.isoformat(),
            },
            "project": {
                "title": idea_or_spec.title,
                "summary": idea_or_spec.one_liner,
                "target_users": idea_or_spec.target_users,
                "specific_user": idea_or_spec.specific_user,
                "buyer": idea_or_spec.buyer,
                "workflow_context": idea_or_spec.workflow_context,
            },
            "problem": {"statement": idea_or_spec.problem},
            "solution": {"approach": idea_or_spec.solution},
            "execution": {
                "mvp_scope": [idea_or_spec.value_proposition],
                "validation_plan": idea_or_spec.validation_plan,
            },
            "evidence": {
                "rationale": idea_or_spec.evidence_rationale,
                "insight_ids": idea_or_spec.inspiring_insights,
                "signal_ids": idea_or_spec.evidence_signals,
                "source_idea_ids": idea_or_spec.source_idea_ids,
            },
            "quality": {
                "quality_score": idea_or_spec.quality_score,
                "novelty_score": idea_or_spec.novelty_score,
                "usefulness_score": idea_or_spec.usefulness_score,
                "rejection_tags": idea_or_spec.rejection_tags,
            },
        }
    return idea_or_spec


def _brief_payload(payload: dict[str, Any]) -> dict[str, Any]:
    brief = (
        payload.get("design_brief") if isinstance(payload.get("design_brief"), dict) else payload
    )
    return brief if isinstance(brief, dict) else {}


def _source_ideas(payload: dict[str, Any]) -> list[dict[str, Any]]:
    source_ideas = payload.get("source_ideas")
    if not isinstance(source_ideas, list):
        return []
    return [item for item in source_ideas if isinstance(item, dict)]


def _lead_source_value(source_ideas: list[dict[str, Any]], key: str) -> Any:
    if not source_ideas:
        return None
    lead = next((item for item in source_ideas if item.get("role") == "lead"), source_ideas[0])
    return lead.get(key)


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _clean_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value not in (None, "", [], {})}


def _title(*values: object) -> str:
    for value in values:
        text = _optional_text(value)
        if text:
            return text[:1000]
    return "Untitled"


def _join_strings(value: object) -> str | None:
    text = ", ".join(_string_list(value))
    return text or None


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, list | tuple | set):
        return []
    values: list[str] = []
    for item in value:
        text = str(item).strip() if item is not None else ""
        if text and text not in values:
            values.append(text)
    return values


def _number_or_text(value: object) -> int | float | str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return text
    return int(number) if number.is_integer() else number


def _required_text(
    value: object,
    message: str,
    *,
    api_key: str | None = None,
) -> str:
    text = _optional_text(value)
    if not text:
        raise AirtableRecordPublishError(message, api_key=api_key)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _required_url(value: object, *, api_key: str | None = None) -> str:
    raw = _required_text(value, "Airtable api_url is required", api_key=api_key).rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise AirtableRecordPublishError("Airtable api_url must be an absolute http(s) URL")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _response_body_preview(
    response: httpx.Response,
    *,
    api_key: str | None = None,
    limit: int = 500,
) -> str:
    text = _redact_text(response.text.strip(), api_key=api_key)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(response: httpx.Response, *, api_key: str | None = None) -> dict[str, Any]:
    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        raise AirtableRecordPublishError(
            "Airtable record publish failed: response was not valid JSON",
            status_code=response.status_code,
            api_key=api_key,
        ) from exc
    if not isinstance(body, dict):
        raise AirtableRecordPublishError(
            "Airtable record publish failed: response JSON was not an object",
            status_code=response.status_code,
            api_key=api_key,
        )
    return body


def _attempt(
    url: str,
    *,
    status_code: int | None = None,
    error: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    attempt: dict[str, Any] = {
        "method": "POST",
        "url": _redact_url(url),
    }
    if status_code is not None:
        attempt["status_code"] = status_code
    if error:
        attempt["error"] = _redact_text(error, api_key=api_key)
    return attempt


def _redact_text(text: str, *, api_key: str | None = None) -> str:
    redacted = text
    token = _optional_text(api_key)
    if token:
        redacted = redacted.replace(token, REDACTED)
    redacted = re.sub(
        r"(?i)(authorization:\s*bearer\s+)[^\s,;)}\]]+",
        rf"\1{REDACTED}",
        redacted,
    )
    redacted = re.sub(r"(?i)(bearer\s+)[^\s,;)}\]]+", rf"\1{REDACTED}", redacted)
    redacted = re.sub(r"(?i)(api[_-]?key[\"'\s:=]+)[^\"'\s,;)}\]]+", rf"\1{REDACTED}", redacted)
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
    netloc = parts.hostname or ""
    if parts.username or parts.password:
        netloc = f"***@{netloc}"
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", parts.fragment))
