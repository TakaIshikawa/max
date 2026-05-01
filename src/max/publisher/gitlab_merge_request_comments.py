"""GitLab merge request note publisher for generated review artifacts."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx


DEFAULT_GITLAB_BASE_URL = "https://gitlab.com"
DEFAULT_TIMEOUT_SECONDS = 10.0


class GitLabMergeRequestCommentPublishError(ValueError):
    """Raised when a GitLab merge request comment publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GitLabMergeRequestCommentPayload:
    """GitLab merge request note payload plus target metadata."""

    provider: str
    project: str
    merge_request_iid: int
    body: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable merge request comment payload."""
        return {
            "provider": self.provider,
            "project": self.project,
            "merge_request_iid": self.merge_request_iid,
            "body": self.body,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class GitLabMergeRequestCommentPublishResult:
    """Summary of a GitLab merge request comment publish or dry run."""

    status_code: int | None
    provider: str
    project: str
    merge_request_iid: int
    note_id: str | None
    note_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class GitLabMergeRequestCommentPublisher:
    """Append comments to existing GitLab merge requests."""

    def __init__(
        self,
        project_id_or_path: str | None = None,
        *,
        merge_request_iid: int | str | None = None,
        body: str | None = None,
        token: str | None = None,
        base_url: str = DEFAULT_GITLAB_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.project_id_or_path = _required_text(
            project_id_or_path,
            "GitLab project ID/path is required",
        )
        self.merge_request_iid = (
            _validate_merge_request_iid(merge_request_iid)
            if merge_request_iid is not None
            else None
        )
        self.body = _optional_text(body)
        self.token = _optional_text(token)
        self.base_url = _required_url(base_url)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        project_id_or_path: str | None = None,
        project_id: str | None = None,
        project_path: str | None = None,
        merge_request_iid: int | str | None = None,
        body: str | None = None,
        token: str | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> GitLabMergeRequestCommentPublisher:
        """Create a publisher using API values first, then environment variables."""
        resolved_project = (
            project_id_or_path
            or project_id
            or project_path
            or os.getenv("GITLAB_PROJECT_ID")
            or os.getenv("GITLAB_PROJECT_PATH")
            or os.getenv("GITLAB_PROJECT")
        )
        return cls(
            resolved_project,
            merge_request_iid=merge_request_iid or os.getenv("GITLAB_MERGE_REQUEST_IID"),
            body=body or os.getenv("GITLAB_MERGE_REQUEST_COMMENT_BODY"),
            token=token or os.getenv("GITLAB_TOKEN"),
            base_url=base_url or os.getenv("GITLAB_BASE_URL", DEFAULT_GITLAB_BASE_URL),
            timeout=timeout,
            client=client,
        )

    def comment_endpoint(self, merge_request_iid: int | str | None = None) -> str:
        """Return the GitLab REST endpoint used for merge request note creation."""
        resolved_iid = self._resolve_merge_request_iid(merge_request_iid)
        project = quote(self.project_id_or_path, safe="")
        return (
            f"{self.base_url}/api/v4/projects/{project}/merge_requests/"
            f"{resolved_iid}/notes"
        )

    def build_comment_payload(
        self,
        body: str | None = None,
        *,
        merge_request_iid: int | str | None = None,
    ) -> GitLabMergeRequestCommentPayload:
        """Build a deterministic GitLab merge request comment payload."""
        resolved_body = _required_text(
            body if body is not None else self.body,
            "GitLab merge request comment body is required",
        )
        resolved_iid = self._resolve_merge_request_iid(merge_request_iid)
        return GitLabMergeRequestCommentPayload(
            provider="gitlab",
            project=self.project_id_or_path,
            merge_request_iid=resolved_iid,
            body=resolved_body,
            metadata={
                "publisher": "max.gitlab_merge_request_comments",
                "provider": "gitlab",
                "project": self.project_id_or_path,
                "merge_request_iid": resolved_iid,
            },
        )

    def publish(
        self,
        body: str | None = None,
        *,
        merge_request_iid: int | str | None = None,
        dry_run: bool = True,
    ) -> GitLabMergeRequestCommentPublishResult:
        """Publish or preview a GitLab merge request comment."""
        payload = self.build_comment_payload(
            body,
            merge_request_iid=merge_request_iid,
        ).to_dict()
        if dry_run:
            return GitLabMergeRequestCommentPublishResult(
                status_code=None,
                provider="gitlab",
                project=self.project_id_or_path,
                merge_request_iid=payload["merge_request_iid"],
                note_id=None,
                note_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self.token:
            raise GitLabMergeRequestCommentPublishError(
                "GITLAB_TOKEN is required for live GitLab merge request comment publishing; "
                "use dry_run to preview"
            )

        endpoint = self.comment_endpoint(payload["merge_request_iid"])
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    endpoint,
                    json={"body": payload["body"]},
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise GitLabMergeRequestCommentPublishError(
                    f"GitLab merge request comment publish failed for {endpoint}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise GitLabMergeRequestCommentPublishError(
                f"GitLab merge request comment publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        note_id = _note_id(response)
        note_url = _note_url(response)
        return GitLabMergeRequestCommentPublishResult(
            status_code=response.status_code,
            provider="gitlab",
            project=self.project_id_or_path,
            merge_request_iid=payload["merge_request_iid"],
            note_id=note_id,
            note_url=note_url,
            dry_run=False,
            payload={
                **payload,
                "note_id": note_id,
                "note_url": note_url,
                "metadata": {
                    **payload["metadata"],
                    "gitlab_merge_request_note_id": note_id,
                    "gitlab_merge_request_note_url": note_url,
                },
            },
        )

    def _resolve_merge_request_iid(
        self,
        merge_request_iid: int | str | None = None,
    ) -> int:
        resolved = (
            merge_request_iid
            if merge_request_iid is not None
            else self.merge_request_iid
        )
        if resolved is None:
            raise GitLabMergeRequestCommentPublishError(
                "GitLab merge request iid is required"
            )
        return _validate_merge_request_iid(resolved)

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "PRIVATE-TOKEN": self.token,
            "User-Agent": "max-gitlab-merge-request-comments-publisher/1",
        }


GitLabMergeRequestCommentsPublisher = GitLabMergeRequestCommentPublisher


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise GitLabMergeRequestCommentPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _required_url(value: object) -> str:
    raw = _required_text(value, "GitLab base_url is required").rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise GitLabMergeRequestCommentPublishError(
            "GitLab base_url must be an absolute http(s) URL"
        )
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _validate_merge_request_iid(value: object) -> int:
    try:
        iid = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise GitLabMergeRequestCommentPublishError(
            "GitLab merge request iid must be a positive integer"
        ) from exc
    if iid < 1:
        raise GitLabMergeRequestCommentPublishError(
            "GitLab merge request iid must be a positive integer"
        )
    return iid


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _note_id(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        note_id = body.get("id")
        return str(note_id) if note_id else None
    return None


def _note_url(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        url = body.get("web_url") or body.get("url")
        return str(url) if url else None
    return None
