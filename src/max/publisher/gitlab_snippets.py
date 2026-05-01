"""GitLab snippet publisher for generated handoff artifacts."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import httpx


DEFAULT_GITLAB_BASE_URL = "https://gitlab.com"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_VISIBILITY = "private"
DEFAULT_FILE_NAME = "max-handoff.md"
GITLAB_SNIPPET_VISIBILITIES = {"private", "internal", "public"}
SECRET_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "client_secret",
    "key",
    "password",
    "private_token",
    "secret",
    "sig",
    "signature",
    "token",
}


class GitLabSnippetPublishError(RuntimeError):
    """Raised when a GitLab snippet publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(_redact_text(message))
        self.status_code = status_code


@dataclass(frozen=True)
class GitLabSnippetPayload:
    """GitLab snippet creation payload plus Max-specific metadata."""

    title: str
    description: str
    file_name: str
    content: str
    visibility: str
    project: str
    metadata: dict[str, Any]
    source_artifact: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable snippet payload preview."""
        return {
            "title": self.title,
            "description": self.description,
            "file_name": self.file_name,
            "content": self.content,
            "visibility": self.visibility,
            "project": self.project,
            "metadata": self.metadata,
            "source_artifact": self.source_artifact,
        }


@dataclass(frozen=True)
class GitLabSnippetPublishResult:
    """Summary of a GitLab snippet publish or dry run."""

    status_code: int | None
    project: str
    snippet_id: int | None
    snippet_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class GitLabSnippetPublisher:
    """Build and optionally create GitLab project snippets from Max artifacts."""

    def __init__(
        self,
        project: str,
        *,
        token: str | None = None,
        base_url: str = DEFAULT_GITLAB_BASE_URL,
        visibility: str = DEFAULT_VISIBILITY,
        file_name: str = DEFAULT_FILE_NAME,
        title: str | None = None,
        dry_run: bool = True,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.project = _required_text(project, "GitLab project ID/path is required")
        self.token = _optional_text(token)
        self.base_url = _required_url(base_url)
        self.visibility = _visibility(visibility)
        self.file_name = _file_name(file_name)
        self.title = _optional_text(title)
        self.dry_run = dry_run
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        project: str | None = None,
        project_id: str | None = None,
        project_path: str | None = None,
        token: str | None = None,
        base_url: str | None = None,
        visibility: str | None = None,
        file_name: str | None = None,
        title: str | None = None,
        dry_run: bool | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> GitLabSnippetPublisher:
        """Create a publisher using API values first, then environment variables."""
        resolved_project = (
            project
            or project_id
            or project_path
            or os.getenv("GITLAB_PROJECT_ID")
            or os.getenv("GITLAB_PROJECT_PATH")
            or os.getenv("GITLAB_PROJECT")
        )
        if not resolved_project:
            raise GitLabSnippetPublishError(
                "GitLab project ID/path is required; pass project_id/project_path or "
                "set GITLAB_PROJECT_ID or GITLAB_PROJECT_PATH"
            )
        return cls(
            resolved_project,
            token=token or os.getenv("GITLAB_TOKEN"),
            base_url=base_url or os.getenv("GITLAB_BASE_URL", DEFAULT_GITLAB_BASE_URL),
            visibility=visibility or os.getenv("GITLAB_SNIPPET_VISIBILITY", DEFAULT_VISIBILITY),
            file_name=file_name or os.getenv("GITLAB_SNIPPET_FILE_NAME", DEFAULT_FILE_NAME),
            title=title or os.getenv("GITLAB_SNIPPET_TITLE"),
            dry_run=_env_bool("GITLAB_SNIPPET_DRY_RUN", True) if dry_run is None else dry_run,
            timeout=timeout,
            client=client,
        )

    @property
    def snippet_endpoint(self) -> str:
        """Return the GitLab REST endpoint used for project snippet creation."""
        return f"{self.base_url}/api/v4/projects/{quote(self.project, safe='')}/snippets"

    def build_snippet_payload(
        self,
        artifact: dict[str, Any] | str,
        *,
        title: str | None = None,
        visibility: str | None = None,
        file_name: str | None = None,
    ) -> GitLabSnippetPayload:
        """Convert a generated spec or text artifact into a GitLab snippet payload."""
        resolved_visibility = _visibility(visibility or self.visibility)
        resolved_file_name = _file_name(file_name or self.file_name)
        source_artifact = _source_artifact(artifact)
        metadata = _metadata(
            source_artifact,
            project=self.project,
            visibility=resolved_visibility,
            file_name=resolved_file_name,
        )
        resolved_title = _snippet_title(
            title or self.title,
            source_artifact=source_artifact,
        )
        content = _artifact_markdown(
            artifact,
            title=resolved_title,
            source_artifact=source_artifact,
        )

        return GitLabSnippetPayload(
            title=resolved_title,
            description=_snippet_description(source_artifact),
            file_name=resolved_file_name,
            content=content,
            visibility=resolved_visibility,
            project=self.project,
            metadata=metadata,
            source_artifact=source_artifact,
        )

    def build_text_snippet_payload(
        self,
        content: str,
        *,
        title: str | None = None,
        visibility: str | None = None,
        file_name: str | None = None,
    ) -> GitLabSnippetPayload:
        """Convert a plain text or Markdown artifact into a GitLab snippet payload."""
        return self.build_snippet_payload(
            content,
            title=title,
            visibility=visibility,
            file_name=file_name,
        )

    def publish(
        self,
        artifact: dict[str, Any] | str,
        *,
        title: str | None = None,
        visibility: str | None = None,
        file_name: str | None = None,
        dry_run: bool | None = None,
    ) -> GitLabSnippetPublishResult:
        """Build the snippet payload and optionally create it in GitLab."""
        snippet_payload = self.build_snippet_payload(
            artifact,
            title=title,
            visibility=visibility,
            file_name=file_name,
        )
        return self.publish_payload(
            snippet_payload,
            dry_run=self.dry_run if dry_run is None else dry_run,
        )

    def publish_payload(
        self,
        snippet_payload: GitLabSnippetPayload,
        *,
        dry_run: bool | None = None,
    ) -> GitLabSnippetPublishResult:
        """Optionally create an already-built snippet payload in GitLab."""
        payload = snippet_payload.to_dict()
        resolved_dry_run = self.dry_run if dry_run is None else dry_run
        if resolved_dry_run:
            return GitLabSnippetPublishResult(
                status_code=None,
                project=self.project,
                snippet_id=None,
                snippet_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self.token:
            raise GitLabSnippetPublishError(
                "GITLAB_TOKEN is required for live GitLab snippet publishing; "
                "use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.snippet_endpoint,
                    json=_gitlab_snippet_request(payload),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                message = _redact_text(str(exc))
                raise GitLabSnippetPublishError(
                    f"GitLab snippet publish failed for {_redact_url(self.snippet_endpoint)}: "
                    f"{message}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise GitLabSnippetPublishError(
                f"GitLab snippet publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        snippet_id = _int_or_none(body.get("id"))
        snippet_url = _optional_text(body.get("web_url"))
        if snippet_id is None or not snippet_url:
            raise GitLabSnippetPublishError(
                "GitLab snippet publish failed: response did not include snippet id and web_url",
                status_code=response.status_code,
            )

        return GitLabSnippetPublishResult(
            status_code=response.status_code,
            project=self.project,
            snippet_id=snippet_id,
            snippet_url=snippet_url,
            dry_run=False,
            payload={
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "gitlab_snippet_id": snippet_id,
                    "gitlab_snippet_url": snippet_url,
                },
            },
        )

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "max-gitlab-snippets-publisher/1",
        }


GitLabSnippetsPublisher = GitLabSnippetPublisher


def _gitlab_snippet_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": payload["title"],
        "description": payload["description"],
        "file_name": payload["file_name"],
        "content": payload["content"],
        "visibility": payload["visibility"],
    }


def _source_artifact(artifact: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(artifact, dict):
        source = _dict_value(artifact, "source")
        project = _dict_value(artifact, "project")
        return {
            "type": _optional_text(source.get("type"))
            or _optional_text(source.get("entity_type"))
            or "artifact",
            "idea_id": source.get("idea_id"),
            "design_brief_id": source.get("design_brief_id") or source.get("id"),
            "schema_version": artifact.get("schema_version"),
            "kind": artifact.get("kind"),
            "title": project.get("title") or artifact.get("title"),
            "summary": project.get("summary") or artifact.get("summary"),
            "payload": artifact,
        }
    return {
        "type": "text_artifact",
        "idea_id": None,
        "design_brief_id": None,
        "schema_version": None,
        "kind": "text/markdown",
        "title": None,
        "summary": None,
        "content": str(artifact),
    }


def _metadata(
    source_artifact: dict[str, Any],
    *,
    project: str,
    visibility: str,
    file_name: str,
) -> dict[str, Any]:
    return {
        "publisher": "max.gitlab_snippets",
        "source_system": "max",
        "source_type": source_artifact["type"],
        "idea_id": source_artifact.get("idea_id"),
        "design_brief_id": source_artifact.get("design_brief_id"),
        "schema_version": source_artifact.get("schema_version"),
        "kind": source_artifact.get("kind"),
        "project": project,
        "visibility": visibility,
        "file_name": file_name,
    }


def _snippet_title(custom_title: object, *, source_artifact: dict[str, Any]) -> str:
    base = (
        _optional_text(custom_title)
        or _optional_text(source_artifact.get("title"))
        or _optional_text(source_artifact.get("design_brief_id"))
        or _optional_text(source_artifact.get("idea_id"))
        or "Generated artifact"
    )
    return f"Max GitLab Snippet: {base}"[:255]


def _snippet_description(source_artifact: dict[str, Any]) -> str:
    summary = _optional_text(source_artifact.get("summary"))
    if summary:
        return summary[:1024]
    artifact_type = source_artifact.get("type") or "artifact"
    return f"Generated Max {artifact_type} handoff artifact"


def _artifact_markdown(
    artifact: dict[str, Any] | str,
    *,
    title: str,
    source_artifact: dict[str, Any],
) -> str:
    if isinstance(artifact, str):
        text = artifact.strip()
        return text + ("\n" if text else "")

    payload = source_artifact["payload"]
    project = _dict_value(payload, "project")
    problem = _dict_value(payload, "problem")
    solution = _dict_value(payload, "solution")
    execution = _dict_value(payload, "execution")
    evidence = _dict_value(payload, "evidence")
    evaluation = payload.get("evaluation") if isinstance(payload.get("evaluation"), dict) else {}

    lines = [
        f"# {project.get('title') or title}",
        "",
        _text_or_placeholder(project.get("summary")),
        "",
        "## Source",
        f"- Type: {_text_or_placeholder(source_artifact.get('type'))}",
        f"- Idea ID: {_text_or_placeholder(source_artifact.get('idea_id'))}",
        f"- Design brief ID: {_text_or_placeholder(source_artifact.get('design_brief_id'))}",
        f"- Kind: {_text_or_placeholder(source_artifact.get('kind'))}",
        "",
        "## Problem",
        _text_or_placeholder(problem.get("statement")),
        "",
        "## Solution",
        _text_or_placeholder(solution.get("approach")),
        "",
        "## MVP Scope",
    ]
    lines.extend(_bullet_list(execution.get("mvp_scope")))
    lines.extend(
        [
            "",
            "## Validation",
            _text_or_placeholder(execution.get("validation_plan")),
            "",
            "## Evidence",
            f"- Rationale: {_text_or_placeholder(evidence.get('rationale'))}",
            f"- Insights: {', '.join(evidence.get('insight_ids') or []) or 'None'}",
            f"- Signals: {', '.join(evidence.get('signal_ids') or []) or 'None'}",
            "",
            "## Evaluation",
            f"- Recommendation: {_text_or_placeholder(evaluation.get('recommendation'))}",
            f"- Overall score: {_score_text(evaluation.get('overall_score'))}",
            "",
            "## Source Artifact",
            "```json",
            json.dumps(payload, indent=2, sort_keys=True),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


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
        raise GitLabSnippetPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _required_url(value: object) -> str:
    raw = _required_text(value, "GitLab base_url is required").rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise GitLabSnippetPublishError("GitLab base_url must be an absolute http(s) URL")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _visibility(value: object) -> str:
    text = _required_text(value, "GitLab snippet visibility is required").lower()
    if text not in GITLAB_SNIPPET_VISIBILITIES:
        raise GitLabSnippetPublishError("GitLab snippet visibility must be private, internal, or public")
    return text


def _file_name(value: object) -> str:
    text = _required_text(value, "GitLab snippet file name is required")
    if "/" in text or "\\" in text:
        raise GitLabSnippetPublishError("GitLab snippet file name must not contain path separators")
    return text


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = _redact_text(response.text.strip())
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise GitLabSnippetPublishError(
            "GitLab snippet publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    if not isinstance(body, dict):
        raise GitLabSnippetPublishError(
            "GitLab snippet publish failed: response JSON was not an object",
            status_code=response.status_code,
        )
    return body


def _redact_text(text: str) -> str:
    redacted = re.sub(
        r"(?i)\b(token|api_token|password|private_token|secret|authorization)\b([=:]\s*)"
        r"[^&\s,'\"}]+",
        r"\1\2<redacted>",
        text,
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
