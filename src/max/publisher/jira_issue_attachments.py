"""Jira issue attachment publisher for generated Markdown or JSON artifacts."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

DEFAULT_TIMEOUT_SECONDS = 10.0


class JiraIssueAttachmentPublishError(RuntimeError):
    """Raised when a Jira issue attachment publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class JiraIssueAttachmentPayload:
    issue_key: str
    filename: str
    content: bytes
    content_type: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_key": self.issue_key,
            "filename": self.filename,
            "content": self.content.decode("utf-8", errors="replace"),
            "content_type": self.content_type,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class JiraIssueAttachmentPublishResult:
    status_code: int | None
    issue_key: str
    filename: str
    attachment_id: str | None
    attachment_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class JiraIssueAttachmentPublisher:
    """Build and optionally upload an attachment to an existing Jira issue."""

    def __init__(
        self,
        base_url: str,
        *,
        issue_key: str | None = None,
        auth_email: str | None = None,
        api_token: str | None = None,
        bearer_token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = _required_url(base_url)
        self.issue_key = _optional(issue_key)
        self.auth_email = _optional(auth_email)
        self.api_token = _optional(api_token)
        self.bearer_token = _optional(bearer_token)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        base_url: str | None = None,
        issue_key: str | None = None,
        auth_email: str | None = None,
        api_token: str | None = None,
        bearer_token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> JiraIssueAttachmentPublisher:
        resolved_base_url = base_url or os.getenv("JIRA_SITE_URL") or os.getenv("JIRA_BASE_URL")
        if not resolved_base_url:
            raise JiraIssueAttachmentPublishError("Jira base_url is required; pass base_url or set JIRA_SITE_URL")
        return cls(
            resolved_base_url,
            issue_key=issue_key or os.getenv("JIRA_ISSUE_KEY"),
            auth_email=auth_email or os.getenv("JIRA_EMAIL"),
            api_token=api_token or os.getenv("JIRA_API_TOKEN"),
            bearer_token=bearer_token or os.getenv("JIRA_BEARER_TOKEN"),
            timeout=timeout,
            client=client,
        )

    def attachment_endpoint(self, issue_key: str | None = None) -> str:
        return f"{self.base_url}/rest/api/3/issue/{self._resolve_issue_key(issue_key)}/attachments"

    def build_attachment_payload(
        self,
        artifact: dict[str, Any] | str | bytes,
        *,
        issue_key: str | None = None,
        filename: str = "max-artifact.md",
        content: str | bytes | None = None,
        content_type: str | None = None,
    ) -> JiraIssueAttachmentPayload:
        resolved_issue_key = self._resolve_issue_key(issue_key)
        resolved_filename = _required(filename, "Jira attachment filename is required")
        rendered = _attachment_content(artifact, content=content, filename=resolved_filename)
        resolved_content_type = content_type or ("application/json" if resolved_filename.endswith(".json") else "text/markdown")
        return JiraIssueAttachmentPayload(
            issue_key=resolved_issue_key,
            filename=resolved_filename,
            content=rendered,
            content_type=resolved_content_type,
            metadata=_metadata(artifact, issue_key=resolved_issue_key, filename=resolved_filename),
        )

    def publish(
        self,
        artifact: dict[str, Any] | str | bytes,
        *,
        dry_run: bool = True,
        issue_key: str | None = None,
        filename: str = "max-artifact.md",
        content: str | bytes | None = None,
        content_type: str | None = None,
    ) -> JiraIssueAttachmentPublishResult:
        payload = self.build_attachment_payload(
            artifact,
            issue_key=issue_key,
            filename=filename,
            content=content,
            content_type=content_type,
        )
        if dry_run:
            data = payload.to_dict()
            data["content_preview"] = data.pop("content")[:500]
            data["content_bytes"] = len(payload.content)
            return JiraIssueAttachmentPublishResult(None, payload.issue_key, payload.filename, None, None, True, data)

        if not self._has_auth:
            raise JiraIssueAttachmentPublishError("Jira auth_email/api_token or bearer_token is required for live attachment publishing")

        endpoint = self.attachment_endpoint(payload.issue_key)
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(
                endpoint,
                headers=self._headers(),
                files={"file": (payload.filename, payload.content, payload.content_type)},
                timeout=self.timeout,
            )
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise JiraIssueAttachmentPublishError(f"Jira issue attachment publish failed for {endpoint}: {exc}") from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise JiraIssueAttachmentPublishError(
                f"Jira issue attachment publish failed with HTTP {response.status_code}: {_preview(response)}",
                status_code=response.status_code,
            )
        body = _json_response(response)
        attachment = body[0] if isinstance(body, list) and body and isinstance(body[0], dict) else body if isinstance(body, dict) else {}
        attachment_id = _optional(attachment.get("id"))
        attachment_url = _optional(attachment.get("content") or attachment.get("self"))
        return JiraIssueAttachmentPublishResult(
            response.status_code,
            payload.issue_key,
            payload.filename,
            attachment_id,
            attachment_url,
            False,
            {**payload.to_dict(), "metadata": {**payload.metadata, "jira_attachment_id": attachment_id, "jira_attachment_url": attachment_url}},
        )

    @property
    def _has_auth(self) -> bool:
        return bool(self.bearer_token or (self.auth_email and self.api_token))

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "X-Atlassian-Token": "no-check", "User-Agent": "max-jira-issue-attachments-publisher/1"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        else:
            assert self.auth_email and self.api_token
            headers["Authorization"] = f"Basic {base64.b64encode(f'{self.auth_email}:{self.api_token}'.encode()).decode('ascii')}"
        return headers

    def _resolve_issue_key(self, issue_key: str | None = None) -> str:
        return _required(issue_key or self.issue_key, "Jira issue_key is required; pass issue_key or set JIRA_ISSUE_KEY")


JiraIssueAttachmentsPublisher = JiraIssueAttachmentPublisher


def _attachment_content(artifact: dict[str, Any] | str | bytes, *, content: str | bytes | None, filename: str) -> bytes:
    if content is not None:
        return content if isinstance(content, bytes) else content.encode("utf-8")
    if isinstance(artifact, bytes):
        return artifact
    if isinstance(artifact, str):
        return artifact.encode("utf-8")
    if filename.endswith(".json"):
        return json.dumps(artifact, indent=2, sort_keys=True).encode("utf-8")
    title = _artifact_title(artifact)
    summary = _dict(artifact.get("project")).get("summary") or _dict(artifact.get("design_brief")).get("summary") or artifact.get("summary") or ""
    source = _dict(artifact.get("source"))
    lines = [f"# {title}", "", str(summary).strip(), "", "## Source", f"- Idea ID: {_text(source.get('idea_id') or source.get('id'))}", f"- Kind: {_text(artifact.get('kind'))}"]
    return "\n".join(lines).encode("utf-8")


def _artifact_title(artifact: dict[str, Any]) -> str:
    return _text(_dict(artifact.get("project")).get("title") or _dict(artifact.get("design_brief")).get("title") or artifact.get("title") or "Max Artifact")


def _metadata(artifact: dict[str, Any] | str | bytes, *, issue_key: str, filename: str) -> dict[str, Any]:
    source = _dict(artifact.get("source")) if isinstance(artifact, dict) else {}
    return {"publisher": "max.jira_issue_attachments", "issue_key": issue_key, "filename": filename, "source_system": source.get("system", "max"), "source_type": source.get("type", "artifact"), "idea_id": source.get("idea_id")}


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _required(value: object, message: str) -> str:
    text = _text(value)
    if not text:
        raise JiraIssueAttachmentPublishError(message)
    return text


def _optional(value: object) -> str | None:
    return _text(value) or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _required_url(value: object) -> str:
    raw = _required(value, "Jira base_url is required").rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise JiraIssueAttachmentPublishError("Jira base_url must be an absolute http(s) URL")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    return text if len(text) <= limit else text[:limit] + "..."


def _json_response(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise JiraIssueAttachmentPublishError("Jira issue attachment publish failed: response was not valid JSON", status_code=response.status_code) from exc
