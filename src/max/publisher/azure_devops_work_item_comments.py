"""Azure DevOps work item comment publisher for generated artifacts."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from max.publisher.azure_devops_work_items import (
    DEFAULT_TIMEOUT_SECONDS,
)


DEFAULT_AZURE_DEVOPS_COMMENTS_API_VERSION = "7.1-preview.4"


class AzureDevOpsWorkItemCommentPublishError(RuntimeError):
    """Raised when an Azure DevOps work item comment publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class AzureDevOpsWorkItemCommentPayload:
    """Azure DevOps work item comment payload plus Max-specific metadata."""

    text: str
    organization_url: str
    project: str
    work_item_id: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable work item comment payload preview."""
        return {
            "text": self.text,
            "organization_url": self.organization_url,
            "project": self.project,
            "work_item_id": self.work_item_id,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class AzureDevOpsWorkItemCommentPublishResult:
    """Summary of an Azure DevOps work item comment publish or dry run."""

    status_code: int | None
    organization_url: str
    project: str
    work_item_id: str
    comment_id: str | None
    comment_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class AzureDevOpsWorkItemCommentPublisher:
    """Build and optionally append generated artifacts to existing Azure DevOps work items."""

    def __init__(
        self,
        organization_url: str | None = None,
        project: str | None = None,
        work_item_id: str | int | None = None,
        *,
        organization: str | None = None,
        personal_access_token: str | None = None,
        api_version: str = DEFAULT_AZURE_DEVOPS_COMMENTS_API_VERSION,
        artifact_title: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.organization_url = _organization_url(organization_url or organization)
        self.project = _required_text(project, "Azure DevOps project is required")
        self.work_item_id = _required_text(work_item_id, "Azure DevOps work_item_id is required")
        self.personal_access_token = _optional_text(personal_access_token)
        self.api_version = _optional_text(api_version) or DEFAULT_AZURE_DEVOPS_COMMENTS_API_VERSION
        self.artifact_title = _optional_text(artifact_title)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        organization_url: str | None = None,
        project: str | None = None,
        work_item_id: str | int | None = None,
        personal_access_token: str | None = None,
        api_version: str | None = None,
        artifact_title: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> AzureDevOpsWorkItemCommentPublisher:
        """Create a publisher using API values first, then environment variables."""
        resolved_organization_url = (
            organization_url
            or os.getenv("AZURE_DEVOPS_ORGANIZATION_URL")
            or os.getenv("AZURE_DEVOPS_ORGANIZATION")
        )
        if not resolved_organization_url:
            raise AzureDevOpsWorkItemCommentPublishError(
                "Azure DevOps organization_url is required; pass organization_url or set "
                "AZURE_DEVOPS_ORGANIZATION_URL"
            )
        resolved_project = project or os.getenv("AZURE_DEVOPS_PROJECT")
        if not resolved_project:
            raise AzureDevOpsWorkItemCommentPublishError(
                "Azure DevOps project is required; pass project or set AZURE_DEVOPS_PROJECT"
            )
        resolved_work_item_id = work_item_id or os.getenv("AZURE_DEVOPS_WORK_ITEM_ID")
        if not resolved_work_item_id:
            raise AzureDevOpsWorkItemCommentPublishError(
                "Azure DevOps work_item_id is required; pass work_item_id or set "
                "AZURE_DEVOPS_WORK_ITEM_ID"
            )
        return cls(
            resolved_organization_url,
            resolved_project,
            resolved_work_item_id,
            personal_access_token=(
                personal_access_token
                or os.getenv("AZURE_DEVOPS_PERSONAL_ACCESS_TOKEN")
                or os.getenv("AZURE_DEVOPS_PAT")
            ),
            api_version=api_version
            or os.getenv(
                "AZURE_DEVOPS_COMMENTS_API_VERSION",
                DEFAULT_AZURE_DEVOPS_COMMENTS_API_VERSION,
            ),
            artifact_title=artifact_title or os.getenv("AZURE_DEVOPS_ARTIFACT_TITLE"),
            timeout=timeout,
            client=client,
        )

    def comment_endpoint(self, work_item_id: str | int | None = None) -> str:
        """Return the Azure DevOps REST endpoint used for work item comment creation."""
        resolved_work_item_id = _required_text(
            work_item_id or self.work_item_id,
            "Azure DevOps work_item_id is required",
        )
        return (
            f"{self.organization_url}/{quote(self.project, safe='')}/_apis/wit/workItems/"
            f"{quote(resolved_work_item_id, safe='')}/comments?"
            f"api-version={quote(self.api_version, safe='.-')}"
        )

    @property
    def has_auth(self) -> bool:
        """Return whether live Azure DevOps work item comment publishing has credentials."""
        return bool(self.personal_access_token)

    def build_comment_payload(
        self,
        artifact: dict[str, Any] | str,
        *,
        body: str | None = None,
        markdown: str | None = None,
        artifact_title: str | None = None,
    ) -> AzureDevOpsWorkItemCommentPayload:
        """Convert generated text or an artifact dictionary into an Azure DevOps comment payload."""
        return AzureDevOpsWorkItemCommentPayload(
            text=_comment_text(
                artifact,
                body=body,
                markdown=markdown,
                artifact_title=artifact_title or self.artifact_title,
            ),
            organization_url=self.organization_url,
            project=self.project,
            work_item_id=self.work_item_id,
            metadata=_metadata(
                artifact,
                organization_url=self.organization_url,
                project=self.project,
                work_item_id=self.work_item_id,
            ),
        )

    def publish(
        self,
        artifact: dict[str, Any] | str,
        *,
        dry_run: bool = True,
        body: str | None = None,
        markdown: str | None = None,
        artifact_title: str | None = None,
    ) -> AzureDevOpsWorkItemCommentPublishResult:
        """Build the comment payload and optionally append it to an Azure DevOps work item."""
        payload = self.build_comment_payload(
            artifact,
            body=body,
            markdown=markdown,
            artifact_title=artifact_title,
        ).to_dict()
        return self.publish_comment_payload(payload, dry_run=dry_run)

    def publish_comment_payload(
        self,
        payload: AzureDevOpsWorkItemCommentPayload | dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> AzureDevOpsWorkItemCommentPublishResult:
        """Publish a caller-rendered Azure DevOps work item comment payload."""
        payload_dict = (
            payload.to_dict()
            if isinstance(payload, AzureDevOpsWorkItemCommentPayload)
            else dict(payload)
        )
        work_item_id = _required_text(
            payload_dict.get("work_item_id") or self.work_item_id,
            "Azure DevOps work_item_id is required",
        )
        comment_payload = {
            **payload_dict,
            "text": _required_text(
                payload_dict.get("text"), "Azure DevOps work item comment text is required"
            ),
            "organization_url": self.organization_url,
            "project": self.project,
            "work_item_id": work_item_id,
            "metadata": payload_dict.get("metadata") or {},
        }
        request_json = {"text": comment_payload["text"]}
        endpoint = self.comment_endpoint(work_item_id)

        if dry_run:
            return AzureDevOpsWorkItemCommentPublishResult(
                status_code=None,
                organization_url=self.organization_url,
                project=self.project,
                work_item_id=work_item_id,
                comment_id=None,
                comment_url=None,
                dry_run=True,
                payload={
                    **comment_payload,
                    "request": {
                        "method": "POST",
                        "url": endpoint,
                        "headers": _redacted_headers_preview(),
                        "json": request_json,
                    },
                },
            )

        if not self.has_auth:
            raise AzureDevOpsWorkItemCommentPublishError(
                "AZURE_DEVOPS_PAT or AZURE_DEVOPS_PERSONAL_ACCESS_TOKEN is required for live "
                "Azure DevOps work item comment publishing; use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    endpoint,
                    json=request_json,
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise AzureDevOpsWorkItemCommentPublishError(
                    f"Azure DevOps work item comment publish failed for {endpoint}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise AzureDevOpsWorkItemCommentPublishError(
                f"Azure DevOps work item comment publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response, self.personal_access_token)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        comment_id = _optional_text(body.get("id"))
        if not comment_id:
            raise AzureDevOpsWorkItemCommentPublishError(
                "Azure DevOps work item comment publish failed: response did not include "
                "created comment id",
                status_code=response.status_code,
            )
        comment_url = _optional_text(body.get("url")) or self.comment_url(work_item_id, comment_id)
        return AzureDevOpsWorkItemCommentPublishResult(
            status_code=response.status_code,
            organization_url=self.organization_url,
            project=self.project,
            work_item_id=work_item_id,
            comment_id=comment_id,
            comment_url=comment_url,
            dry_run=False,
            payload={
                **comment_payload,
                "metadata": {
                    **comment_payload["metadata"],
                    "azure_devops_work_item_comment_id": comment_id,
                    "azure_devops_work_item_comment_url": comment_url,
                },
            },
        )

    def comment_url(self, work_item_id: str, comment_id: str) -> str:
        """Return a browsable Azure DevOps URL focused near the work item discussion."""
        return (
            f"{self.organization_url}/{quote(self.project, safe='')}/_workitems/edit/"
            f"{quote(work_item_id, safe='')}?discussionId={quote(comment_id, safe='')}"
        )

    def _headers(self) -> dict[str, str]:
        assert self.personal_access_token is not None
        credentials = f":{self.personal_access_token}".encode("utf-8")
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Basic {base64.b64encode(credentials).decode('ascii')}",
            "User-Agent": "max-azure-devops-work-item-comments-publisher/1",
        }


AzureDevOpsWorkItemCommentsPublisher = AzureDevOpsWorkItemCommentPublisher


def _comment_text(
    artifact: dict[str, Any] | str,
    *,
    body: str | None,
    markdown: str | None,
    artifact_title: str | None,
) -> str:
    explicit = _optional_text(body) or _optional_text(markdown)
    if explicit:
        return _escape(explicit)
    if isinstance(artifact, str):
        return _escape(_required_text(artifact, "Azure DevOps work item comment text is required"))
    title = _optional_text(artifact_title) or _artifact_title(artifact)
    return "\n".join([f"## {_escape(title)}", "", _artifact_summary(artifact)])


def _artifact_title(artifact: dict[str, Any]) -> str:
    project = _dict_value(artifact, "project")
    source = _dict_value(artifact, "source")
    return _text_or_placeholder(
        project.get("title")
        or artifact.get("title")
        or source.get("idea_id")
        or source.get("design_brief_id")
        or "Generated Artifact"
    )


def _artifact_summary(artifact: dict[str, Any]) -> str:
    project = _dict_value(artifact, "project")
    source = _dict_value(artifact, "source")
    lines = [
        _escape(_text_or_placeholder(project.get("summary") or artifact.get("summary"))),
        "",
        f"- Kind: {_escape(_text_or_placeholder(artifact.get('kind')))}",
        f"- Schema version: {_escape(_text_or_placeholder(artifact.get('schema_version')))}",
    ]
    if source.get("idea_id"):
        lines.append(f"- Idea ID: {_escape(source['idea_id'])}")
    if source.get("design_brief_id"):
        lines.append(f"- Design brief ID: {_escape(source['design_brief_id'])}")
    return "\n".join(lines)


def _metadata(
    artifact: dict[str, Any] | str,
    *,
    organization_url: str,
    project: str,
    work_item_id: str,
) -> dict[str, Any]:
    base = {
        "publisher": "max.azure_devops_work_item_comments",
        "organization_url": organization_url,
        "project": project,
        "work_item_id": work_item_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if not isinstance(artifact, dict):
        return {
            **base,
            "source_system": "max",
            "source_type": "text",
        }
    source = _dict_value(artifact, "source")
    return {
        **base,
        "source_system": source.get("system", "max"),
        "source_type": source.get("type", "artifact"),
        "idea_id": source.get("idea_id"),
        "design_brief_id": source.get("design_brief_id"),
        "schema_version": artifact.get("schema_version"),
        "kind": artifact.get("kind"),
    }


def _organization_url(value: object) -> str:
    raw = _required_text(value, "Azure DevOps organization_url is required").rstrip("/")
    if raw.startswith(("http://", "https://")):
        parts = urlsplit(raw)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise AzureDevOpsWorkItemCommentPublishError(
                "Azure DevOps organization_url must be an absolute http(s) URL"
            )
        return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))
    return f"https://dev.azure.com/{quote(raw, safe='')}"


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise AzureDevOpsWorkItemCommentPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _text_or_placeholder(value: object) -> str:
    text = str(value).strip() if value is not None else ""
    return text or "Not specified"


def _escape(value: object) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _redacted_headers_preview() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": "[REDACTED]",
        "User-Agent": "max-azure-devops-work-item-comments-publisher/1",
    }


def _response_body_preview(
    response: httpx.Response,
    personal_access_token: str | None,
    *,
    limit: int = 500,
) -> str:
    try:
        body = response.json()
    except ValueError:
        text = response.text.strip()
    else:
        text = json.dumps(body, sort_keys=True)
    text = _redact_text(text, personal_access_token)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise AzureDevOpsWorkItemCommentPublishError(
            "Azure DevOps work item comment publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    return body if isinstance(body, dict) else {}


def _redact_text(text: str, personal_access_token: str | None) -> str:
    secret = _optional_text(personal_access_token)
    if not secret:
        return text
    return text.replace(secret, "[REDACTED]")
