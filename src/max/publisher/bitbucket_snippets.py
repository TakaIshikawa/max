"""Bitbucket Cloud snippet publisher for generated TactSpec payloads."""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx


DEFAULT_BITBUCKET_API_URL = "https://api.bitbucket.org/2.0"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_VISIBILITY = "private"
BITBUCKET_SNIPPET_VISIBILITIES = {"private", "public"}


class BitbucketSnippetPublishError(RuntimeError):
    """Raised when a Bitbucket snippet publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class BitbucketSnippetPayload:
    """Bitbucket snippet creation payload plus Max-specific metadata."""

    title: str
    workspace: str
    visibility: str
    files: dict[str, dict[str, str]]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable snippet payload preview."""
        return {
            "title": self.title,
            "workspace": self.workspace,
            "visibility": self.visibility,
            "files": self.files,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class BitbucketSnippetPublishResult:
    """Summary of a Bitbucket snippet publish or dry run."""

    status_code: int | None
    workspace: str
    snippet_id: str | None
    snippet_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class BitbucketSnippetPublisher:
    """Build and optionally create Bitbucket Cloud snippets from TactSpec previews."""

    def __init__(
        self,
        workspace: str,
        *,
        username: str | None = None,
        app_password: str | None = None,
        token: str | None = None,
        api_url: str = DEFAULT_BITBUCKET_API_URL,
        visibility: str = DEFAULT_VISIBILITY,
        title: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.workspace = _required_slug(workspace, "Bitbucket workspace is required")
        self.username = _optional_text(username)
        self.app_password = _optional_text(app_password)
        self.token = _optional_text(token)
        self.api_url = _required_url(api_url)
        self.visibility = _visibility(visibility)
        self.title = _optional_text(title)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        workspace: str | None = None,
        username: str | None = None,
        app_password: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        visibility: str | None = None,
        title: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> BitbucketSnippetPublisher:
        """Create a publisher using API values first, then environment variables."""
        resolved_workspace = workspace or os.getenv("BITBUCKET_WORKSPACE")
        if not resolved_workspace:
            raise BitbucketSnippetPublishError(
                "Bitbucket workspace is required; pass workspace or set BITBUCKET_WORKSPACE"
            )
        return cls(
            resolved_workspace,
            username=username or os.getenv("BITBUCKET_USERNAME"),
            app_password=app_password or os.getenv("BITBUCKET_APP_PASSWORD"),
            token=token or os.getenv("BITBUCKET_TOKEN") or os.getenv("BITBUCKET_ACCESS_TOKEN"),
            api_url=api_url or os.getenv("BITBUCKET_API_URL", DEFAULT_BITBUCKET_API_URL),
            visibility=visibility or os.getenv("BITBUCKET_SNIPPET_VISIBILITY", DEFAULT_VISIBILITY),
            title=title,
            timeout=timeout,
            client=client,
        )

    @property
    def snippet_endpoint(self) -> str:
        """Return the Bitbucket Cloud REST endpoint used for snippet creation."""
        return f"{self.api_url}/snippets/{quote(self.workspace, safe='')}"

    def build_snippet_payload(
        self,
        tact_spec: dict[str, Any],
        *,
        title: str | None = None,
        visibility: str | None = None,
    ) -> BitbucketSnippetPayload:
        """Convert a generated TactSpec preview into a Bitbucket snippet payload."""
        source = _dict_value(tact_spec, "source")
        project = _dict_value(tact_spec, "project")
        resolved_visibility = _visibility(visibility or self.visibility)
        resolved_title = _snippet_title(title or self.title, project.get("title"), source.get("idea_id"))
        base_filename = _base_filename(source.get("idea_id"), project.get("title"))
        files = {
            f"{base_filename}.md": {
                "content": _snippet_markdown(tact_spec),
                "content_type": "text/markdown",
            },
            f"{base_filename}.json": {
                "content": json.dumps(tact_spec, indent=2, sort_keys=True),
                "content_type": "application/json",
            },
        }
        metadata = {
            "publisher": "max.bitbucket_snippets",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "idea"),
            "idea_id": source.get("idea_id"),
            "design_brief_id": source.get("design_brief_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "workspace": self.workspace,
            "visibility": resolved_visibility,
            "filenames": sorted(files),
        }
        return BitbucketSnippetPayload(
            title=resolved_title,
            workspace=self.workspace,
            visibility=resolved_visibility,
            files=files,
            metadata=metadata,
        )

    def publish(
        self,
        tact_spec: dict[str, Any],
        *,
        title: str | None = None,
        visibility: str | None = None,
        dry_run: bool = True,
    ) -> BitbucketSnippetPublishResult:
        """Build the snippet payload and optionally create it in Bitbucket Cloud."""
        snippet_payload = self.build_snippet_payload(
            tact_spec,
            title=title,
            visibility=visibility,
        )
        return self.publish_payload(snippet_payload, dry_run=dry_run)

    def publish_payload(
        self,
        snippet_payload: BitbucketSnippetPayload,
        *,
        dry_run: bool = True,
    ) -> BitbucketSnippetPublishResult:
        """Optionally create an already-built snippet payload in Bitbucket Cloud."""
        payload = snippet_payload.to_dict()
        if dry_run:
            return BitbucketSnippetPublishResult(
                status_code=None,
                workspace=self.workspace,
                snippet_id=None,
                snippet_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self._has_auth:
            raise BitbucketSnippetPublishError(
                "BITBUCKET_TOKEN or BITBUCKET_USERNAME and BITBUCKET_APP_PASSWORD are "
                "required for live Bitbucket snippet publishing; use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.snippet_endpoint,
                    data={
                        "title": payload["title"],
                        "is_private": "true" if payload["visibility"] == "private" else "false",
                    },
                    files=_bitbucket_snippet_files(payload),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise BitbucketSnippetPublishError(
                    f"Bitbucket snippet publish failed for {self.snippet_endpoint}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise BitbucketSnippetPublishError(
                f"Bitbucket snippet publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        snippet_id = _snippet_id(body)
        snippet_url = _snippet_url(body)
        if not snippet_id or not snippet_url:
            raise BitbucketSnippetPublishError(
                "Bitbucket snippet publish failed: response did not include snippet id and html link",
                status_code=response.status_code,
            )

        return BitbucketSnippetPublishResult(
            status_code=response.status_code,
            workspace=self.workspace,
            snippet_id=snippet_id,
            snippet_url=snippet_url,
            dry_run=False,
            payload={
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "bitbucket_snippet_id": snippet_id,
                    "bitbucket_snippet_url": snippet_url,
                },
            },
        )

    @property
    def _has_auth(self) -> bool:
        return bool(self.token or (self.username and self.app_password))

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "max-bitbucket-snippets-publisher/1",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
            return headers
        assert self.username is not None and self.app_password is not None
        credentials = f"{self.username}:{self.app_password}".encode("utf-8")
        headers["Authorization"] = f"Basic {base64.b64encode(credentials).decode('ascii')}"
        return headers


BitbucketSnippetsPublisher = BitbucketSnippetPublisher


def _bitbucket_snippet_files(payload: dict[str, Any]) -> dict[str, tuple[str, str, str]]:
    files: dict[str, tuple[str, str, str]] = {}
    for filename, file_payload in payload["files"].items():
        files[f"files/{filename}"] = (
            filename,
            file_payload["content"],
            file_payload.get("content_type") or "text/plain",
        )
    return files


def _snippet_title(custom_title: object, project_title: object, idea_id: object) -> str:
    base = _optional_text(custom_title) or _optional_text(project_title) or _optional_text(idea_id)
    return f"Max TactSpec: {base or 'Generated TactSpec'}"[:255]


def _base_filename(idea_id: object, project_title: object) -> str:
    base = _optional_text(idea_id) or _optional_text(project_title) or "generated-tact-spec"
    slug = re.sub(r"[^a-z0-9._-]+", "-", base.lower()).strip(".-_")
    return slug or "generated-tact-spec"


def _snippet_markdown(tact_spec: dict[str, Any]) -> str:
    project = _dict_value(tact_spec, "project")
    problem = _dict_value(tact_spec, "problem")
    solution = _dict_value(tact_spec, "solution")
    execution = _dict_value(tact_spec, "execution")
    evidence = _dict_value(tact_spec, "evidence")
    source = _dict_value(tact_spec, "source")
    evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}

    lines = [
        f"# {project.get('title') or source.get('idea_id') or 'Generated TactSpec'}",
        "",
        _text_or_placeholder(project.get("summary")),
        "",
        "## Source",
        f"- Idea ID: {_text_or_placeholder(source.get('idea_id'))}",
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
        ]
    )
    return "\n".join(lines) + "\n"


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
        raise BitbucketSnippetPublishError(message)
    return text


def _required_slug(value: object, message: str) -> str:
    text = _required_text(value, message)
    if "/" in text:
        raise BitbucketSnippetPublishError(f"{message}; use the slug without a slash")
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _required_url(value: object) -> str:
    raw = _required_text(value, "Bitbucket api_url is required").rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise BitbucketSnippetPublishError("Bitbucket api_url must be an absolute http(s) URL")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _visibility(value: object) -> str:
    text = _required_text(value, "Bitbucket snippet visibility is required").lower()
    if text not in BITBUCKET_SNIPPET_VISIBILITIES:
        raise BitbucketSnippetPublishError("Bitbucket snippet visibility must be private or public")
    return text


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise BitbucketSnippetPublishError(
            "Bitbucket snippet publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    if not isinstance(body, dict):
        raise BitbucketSnippetPublishError(
            "Bitbucket snippet publish failed: response JSON was not an object",
            status_code=response.status_code,
        )
    return body


def _snippet_id(body: dict[str, Any]) -> str | None:
    snippet_id = body.get("id")
    return str(snippet_id) if snippet_id else None


def _snippet_url(body: dict[str, Any]) -> str | None:
    links = body.get("links")
    if isinstance(links, dict):
        html = links.get("html")
        if isinstance(html, dict) and html.get("href"):
            return str(html["href"])
    url = body.get("html_url")
    return str(url) if url else None
