"""Azure DevOps work item publisher for generated TactSpecs."""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from max.types.buildable_unit import BuildableUnit


DEFAULT_AZURE_DEVOPS_API_VERSION = "7.1"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_WORK_ITEM_TYPE = "User Story"
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class AzureDevOpsWorkItemPublishError(RuntimeError):
    """Raised when an Azure DevOps work item publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class AzureDevOpsWorkItemPayload:
    """Azure DevOps JSON Patch payload plus Max-specific metadata."""

    organization: str
    project: str
    work_item_type: str
    operations: list[dict[str, Any]]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable work item payload preview."""
        return {
            "organization": self.organization,
            "project": self.project,
            "work_item_type": self.work_item_type,
            "operations": self.operations,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class AzureDevOpsWorkItemPublishResult:
    """Summary of an Azure DevOps work item publish or dry run."""

    status_code: int | None
    organization: str
    project: str
    work_item_type: str
    work_item_id: str | None
    work_item_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class AzureDevOpsWorkItemPublisher:
    """Build and optionally create Azure DevOps work items from approved ideas."""

    def __init__(
        self,
        organization: str,
        project: str,
        *,
        personal_access_token: str | None = None,
        work_item_type: str = DEFAULT_WORK_ITEM_TYPE,
        area_path: str | None = None,
        iteration_path: str | None = None,
        tags: list[str] | None = None,
        api_version: str = DEFAULT_AZURE_DEVOPS_API_VERSION,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = 0.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.organization = _required_text(
            organization, "Azure DevOps organization is required"
        )
        self.project = _required_text(project, "Azure DevOps project is required")
        self.personal_access_token = _optional_text(personal_access_token)
        self.work_item_type = _optional_text(work_item_type) or DEFAULT_WORK_ITEM_TYPE
        self.area_path = _optional_text(area_path)
        self.iteration_path = _optional_text(iteration_path)
        self.tags = [_required_text(tag, "Azure DevOps tags must be non-empty") for tag in tags or []]
        self.api_version = _optional_text(api_version) or DEFAULT_AZURE_DEVOPS_API_VERSION
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.retry_backoff = max(0.0, retry_backoff)
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        organization: str | None = None,
        project: str | None = None,
        personal_access_token: str | None = None,
        work_item_type: str | None = None,
        area_path: str | None = None,
        iteration_path: str | None = None,
        tags: list[str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        client: httpx.Client | None = None,
    ) -> AzureDevOpsWorkItemPublisher:
        """Create a publisher using API values first, then environment variables."""
        resolved_organization = organization or os.getenv("AZURE_DEVOPS_ORGANIZATION")
        if not resolved_organization:
            raise AzureDevOpsWorkItemPublishError(
                "Azure DevOps organization is required; pass organization or set AZURE_DEVOPS_ORGANIZATION"
            )
        resolved_project = project or os.getenv("AZURE_DEVOPS_PROJECT")
        if not resolved_project:
            raise AzureDevOpsWorkItemPublishError(
                "Azure DevOps project is required; pass project or set AZURE_DEVOPS_PROJECT"
            )
        return cls(
            resolved_organization,
            resolved_project,
            personal_access_token=(
                personal_access_token or os.getenv("AZURE_DEVOPS_PERSONAL_ACCESS_TOKEN")
                or os.getenv("AZURE_DEVOPS_PAT")
            ),
            work_item_type=work_item_type
            or os.getenv("AZURE_DEVOPS_WORK_ITEM_TYPE", DEFAULT_WORK_ITEM_TYPE),
            area_path=area_path or os.getenv("AZURE_DEVOPS_AREA_PATH"),
            iteration_path=iteration_path or os.getenv("AZURE_DEVOPS_ITERATION_PATH"),
            tags=tags if tags is not None else _string_list_env("AZURE_DEVOPS_TAGS"),
            timeout=timeout,
            max_retries=max_retries,
            client=client,
        )

    @property
    def work_item_endpoint(self) -> str:
        """Return the Azure DevOps REST endpoint used for work item creation."""
        org = quote(self.organization, safe="")
        project = quote(self.project, safe="")
        work_item_type = quote(f"${self.work_item_type}", safe="$")
        return (
            f"https://dev.azure.com/{org}/{project}/_apis/wit/workitems/"
            f"{work_item_type}?api-version={quote(self.api_version, safe='.')}"
        )

    @property
    def has_auth(self) -> bool:
        """Return whether live Azure DevOps work item publishing has credentials."""
        return bool(self.personal_access_token)

    def build_work_item_payload(
        self,
        idea_or_spec: BuildableUnit | dict[str, Any],
        spec_preview: dict[str, Any] | None = None,
    ) -> AzureDevOpsWorkItemPayload:
        """Convert a BuildableUnit or generated TactSpec preview into JSON Patch operations."""
        tact_spec = _coerce_tact_spec(idea_or_spec, spec_preview)
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")
        quality = _dict_value(tact_spec, "quality")
        evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}

        metadata = {
            "publisher": "max.azure_devops_work_items",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "idea"),
            "idea_id": source.get("idea_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "organization": self.organization,
            "project": self.project,
            "work_item_type": self.work_item_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        tags = _merge_tags(
            _work_item_tags(source=source, quality=quality, evaluation=evaluation),
            self.tags,
        )
        operations = [
            _add_field("/fields/System.Title", _work_item_title(project.get("title"), source.get("idea_id"))),
            _add_field("/fields/System.Description", _html_description(tact_spec, metadata)),
        ]
        if self.area_path:
            operations.append(_add_field("/fields/System.AreaPath", self.area_path))
        if self.iteration_path:
            operations.append(_add_field("/fields/System.IterationPath", self.iteration_path))
        if tags:
            operations.append(_add_field("/fields/System.Tags", "; ".join(tags)))

        return AzureDevOpsWorkItemPayload(
            organization=self.organization,
            project=self.project,
            work_item_type=self.work_item_type,
            operations=operations,
            metadata=metadata,
        )

    def publish(
        self,
        idea_or_spec: BuildableUnit | dict[str, Any],
        *,
        spec_preview: dict[str, Any] | None = None,
        dry_run: bool = True,
    ) -> AzureDevOpsWorkItemPublishResult:
        """Build the JSON Patch payload and optionally create it in Azure DevOps."""
        payload = self.build_work_item_payload(idea_or_spec, spec_preview).to_dict()
        if dry_run:
            return AzureDevOpsWorkItemPublishResult(
                status_code=None,
                organization=self.organization,
                project=self.project,
                work_item_type=self.work_item_type,
                work_item_id=None,
                work_item_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self.has_auth:
            raise AzureDevOpsWorkItemPublishError(
                "AZURE_DEVOPS_PAT or AZURE_DEVOPS_PERSONAL_ACCESS_TOKEN is required for live "
                "Azure DevOps work item publishing; use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = self._post_with_retries(client, payload)
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise AzureDevOpsWorkItemPublishError(
                f"Azure DevOps work item publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        work_item_id = body.get("id")
        if work_item_id is None:
            raise AzureDevOpsWorkItemPublishError(
                "Azure DevOps work item publish failed: response did not include created work item id",
                status_code=response.status_code,
            )
        work_item_url = self.work_item_url(str(work_item_id))
        return AzureDevOpsWorkItemPublishResult(
            status_code=response.status_code,
            organization=self.organization,
            project=self.project,
            work_item_type=self.work_item_type,
            work_item_id=str(work_item_id),
            work_item_url=work_item_url,
            dry_run=False,
            payload={
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "azure_devops_work_item_id": str(work_item_id),
                    "azure_devops_work_item_url": work_item_url,
                },
            },
        )

    def work_item_url(self, work_item_id: str) -> str:
        """Return the Azure DevOps browser URL for a work item."""
        return (
            f"https://dev.azure.com/{quote(self.organization, safe='')}/"
            f"{quote(self.project, safe='')}/_workitems/edit/{quote(work_item_id, safe='')}"
        )

    def _post_with_retries(
        self,
        client: httpx.Client,
        payload: dict[str, Any],
    ) -> httpx.Response:
        last_response: httpx.Response | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = client.post(
                    self.work_item_endpoint,
                    json=payload["operations"],
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise AzureDevOpsWorkItemPublishError(
                    f"Azure DevOps work item publish failed for {self.work_item_endpoint}: {exc}"
                ) from exc

            last_response = response
            if response.status_code not in TRANSIENT_STATUS_CODES or attempt >= self.max_retries:
                return response
            if self.retry_backoff:
                time.sleep(self.retry_backoff * (attempt + 1))

        return last_response

    def _headers(self) -> dict[str, str]:
        assert self.personal_access_token is not None
        credentials = f":{self.personal_access_token}".encode("utf-8")
        return {
            "Accept": "application/json",
            "Content-Type": "application/json-patch+json",
            "Authorization": f"Basic {base64.b64encode(credentials).decode('ascii')}",
            "User-Agent": "max-azure-devops-work-items-publisher/1",
        }


AzureDevOpsWorkItemsPublisher = AzureDevOpsWorkItemPublisher


def _add_field(path: str, value: Any) -> dict[str, Any]:
    return {"op": "add", "path": path, "value": value}


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


def _work_item_title(title: object, idea_id: object) -> str:
    base = str(title).strip() if title else str(idea_id or "Generated TactSpec").strip()
    if base.startswith("[Max]"):
        return base[:255]
    return f"[Max] {base}"[:255]


def _html_description(tact_spec: dict[str, Any], metadata: dict[str, Any]) -> str:
    project = _dict_value(tact_spec, "project")
    problem = _dict_value(tact_spec, "problem")
    solution = _dict_value(tact_spec, "solution")
    execution = _dict_value(tact_spec, "execution")
    evidence = _dict_value(tact_spec, "evidence")
    evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}

    parts = [
        f"<h2>{_escape(project.get('title') or 'Max idea')}</h2>",
        f"<p>{_escape(project.get('summary'))}</p>",
        "<h3>Problem</h3>",
        f"<p>{_escape(problem.get('statement'))}</p>",
        "<h3>Solution</h3>",
        f"<p>{_escape(solution.get('approach'))}</p>",
        "<h3>Execution</h3>",
        _html_list(_list_value(execution.get("mvp_scope"))),
        f"<p><strong>Validation plan:</strong> {_escape(execution.get('validation_plan'))}</p>",
        "<h3>Evidence</h3>",
        f"<p>{_escape(evidence.get('rationale'))}</p>",
    ]
    if evaluation:
        parts.extend(
            [
                "<h3>Evaluation</h3>",
                f"<p><strong>Overall score:</strong> {_escape(evaluation.get('overall_score'))}</p>",
                f"<p><strong>Recommendation:</strong> {_escape(evaluation.get('recommendation'))}</p>",
            ]
        )
    parts.extend(
        [
            "<h3>Max Metadata</h3>",
            "<pre>",
            _escape(json.dumps(metadata, sort_keys=True, indent=2)),
            "</pre>",
        ]
    )
    return "\n".join(part for part in parts if part)


def _html_list(items: list[Any]) -> str:
    if not items:
        return ""
    return "<ul>" + "".join(f"<li>{_escape(item)}</li>" for item in items) + "</ul>"


def _escape(value: object) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _work_item_tags(
    *,
    source: dict[str, Any],
    quality: dict[str, Any],
    evaluation: dict[str, Any],
) -> list[str]:
    tags = ["max"]
    if source.get("domain"):
        tags.append(str(source["domain"]))
    if evaluation.get("recommendation"):
        tags.append(f"recommendation-{evaluation['recommendation']}")
    if quality.get("quality_score") is not None:
        tags.append("quality-scored")
    return tags


def _merge_tags(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for tag in group:
            normalized = str(tag).strip()
            key = normalized.lower()
            if normalized and key not in seen:
                merged.append(normalized)
                seen.add(key)
    return merged


def _dict_value(mapping: dict[str, Any], key: str) -> dict[str, Any]:
    value = mapping.get(key)
    return value if isinstance(value, dict) else {}


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _required_text(value: str | None, message: str) -> str:
    if value is None or not str(value).strip():
        raise AzureDevOpsWorkItemPublishError(message)
    return str(value).strip()


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list_env(name: str) -> list[str]:
    value = os.getenv(name)
    if not value:
        return []
    return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    try:
        body = response.json()
    except ValueError:
        text = response.text
    else:
        text = json.dumps(body, sort_keys=True)
    return text[:limit]


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise AzureDevOpsWorkItemPublishError(
            "Azure DevOps work item publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    if not isinstance(body, dict):
        raise AzureDevOpsWorkItemPublishError(
            "Azure DevOps work item publish failed: response JSON was not an object",
            status_code=response.status_code,
        )
    return body
