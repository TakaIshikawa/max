"""GitLab Releases publisher for generated specs and buildable units."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import httpx

from max.types.buildable_unit import BuildableUnit


DEFAULT_GITLAB_BASE_URL = "https://gitlab.com"
DEFAULT_TIMEOUT_SECONDS = 10.0
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


class GitLabReleasePublishError(RuntimeError):
    """Raised when a GitLab release publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(_redact_text(message))
        self.status_code = status_code


@dataclass(frozen=True)
class GitLabReleasePayload:
    """GitLab release creation payload plus Max-specific metadata."""

    project: str
    tag_name: str
    name: str
    description: str
    metadata: dict[str, Any]
    ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable release payload preview."""
        payload: dict[str, Any] = {
            "project": self.project,
            "tag_name": self.tag_name,
            "name": self.name,
            "description": self.description,
            "metadata": self.metadata,
        }
        if self.ref:
            payload["ref"] = self.ref
        return payload


@dataclass(frozen=True)
class GitLabReleasePublishResult:
    """Summary of a GitLab release publish or dry run."""

    status_code: int | None
    project: str
    endpoint: str
    release_tag: str | None
    release_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class GitLabReleasePublisher:
    """Build and optionally create GitLab project releases from Max artifacts."""

    def __init__(
        self,
        project: str | None = None,
        *,
        project_id: str | None = None,
        project_path: str | None = None,
        token: str | None = None,
        base_url: str = DEFAULT_GITLAB_BASE_URL,
        tag_name: str | None = None,
        release_name: str | None = None,
        description: str | None = None,
        ref: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.project = _required_text(
            project or project_id or project_path,
            "GitLab project ID/path is required",
        )
        self.token = _optional_text(token)
        self.base_url = _required_url(base_url)
        self.tag_name = _validate_tag_name(tag_name) if tag_name is not None else None
        self.release_name = _optional_text(release_name)
        self.description = _optional_text(description)
        self.ref = _optional_text(ref)
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
        tag_name: str | None = None,
        release_name: str | None = None,
        description: str | None = None,
        ref: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> GitLabReleasePublisher:
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
            raise GitLabReleasePublishError(
                "GitLab project ID/path is required; pass project_id/project_path or "
                "set GITLAB_PROJECT_ID or GITLAB_PROJECT_PATH"
            )
        return cls(
            resolved_project,
            token=token or os.getenv("GITLAB_TOKEN"),
            base_url=base_url or os.getenv("GITLAB_BASE_URL", DEFAULT_GITLAB_BASE_URL),
            tag_name=tag_name or os.getenv("GITLAB_RELEASE_TAG"),
            release_name=release_name or os.getenv("GITLAB_RELEASE_NAME"),
            description=description,
            ref=ref or os.getenv("GITLAB_RELEASE_REF"),
            timeout=timeout,
            client=client,
        )

    @property
    def release_endpoint(self) -> str:
        """Return the GitLab REST endpoint used for release creation."""
        return f"{self.base_url}/api/v4/projects/{quote(self.project, safe='')}/releases"

    def build_release_payload(
        self,
        artifact: BuildableUnit | dict[str, Any],
        *,
        tag_name: str | None = None,
        release_name: str | None = None,
        description: str | None = None,
        ref: str | None = None,
    ) -> GitLabReleasePayload:
        """Convert a BuildableUnit or generated artifact into a GitLab release payload."""
        source_artifact = _coerce_artifact(artifact)
        source = _dict_value(source_artifact, "source")
        resolved_tag = _validate_tag_name(tag_name or self.tag_name)
        resolved_name = _release_name(
            source_artifact,
            explicit_name=release_name or self.release_name,
        )
        resolved_ref = _optional_text(ref) or self.ref
        metadata = {
            "publisher": "max.gitlab_releases",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "artifact"),
            "idea_id": source.get("idea_id"),
            "design_brief_id": source.get("design_brief_id"),
            "schema_version": source_artifact.get("schema_version"),
            "kind": source_artifact.get("kind"),
            "project": self.project,
            "tag_name": resolved_tag,
            "release_name": resolved_name,
        }
        if resolved_ref:
            metadata["ref"] = resolved_ref

        return GitLabReleasePayload(
            project=self.project,
            tag_name=resolved_tag,
            name=resolved_name,
            description=(
                _required_text(description, "GitLab release description is required")
                if description is not None
                else self.description
                or _release_description(source_artifact, title=resolved_name)
            ),
            ref=resolved_ref,
            metadata=metadata,
        )

    def publish(
        self,
        artifact: BuildableUnit | dict[str, Any],
        *,
        dry_run: bool = True,
        tag_name: str | None = None,
        release_name: str | None = None,
        description: str | None = None,
        ref: str | None = None,
    ) -> GitLabReleasePublishResult:
        """Build the release payload and optionally create it in GitLab."""
        payload = self.build_release_payload(
            artifact,
            tag_name=tag_name,
            release_name=release_name,
            description=description,
            ref=ref,
        ).to_dict()
        return self.publish_release_payload(payload, dry_run=dry_run)

    def publish_release_payload(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> GitLabReleasePublishResult:
        """Publish a pre-rendered GitLab release payload."""
        payload = {**payload, "tag_name": _validate_tag_name(payload.get("tag_name"))}
        if dry_run:
            return GitLabReleasePublishResult(
                status_code=None,
                project=self.project,
                endpoint=self.release_endpoint,
                release_tag=None,
                release_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self.token:
            raise GitLabReleasePublishError(
                "GITLAB_TOKEN is required for live GitLab release publishing; "
                "use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.release_endpoint,
                    json=_gitlab_release_request(payload),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                message = _redact_text(str(exc))
                raise GitLabReleasePublishError(
                    f"GitLab release publish failed for {_redact_url(self.release_endpoint)}: "
                    f"{message}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            if _is_duplicate_release_response(response):
                raise GitLabReleasePublishError(
                    f"GitLab release already exists for tag {payload['tag_name']}",
                    status_code=response.status_code,
                )
            raise GitLabReleasePublishError(
                f"GitLab release publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        release_tag = _optional_text(body.get("tag_name")) or payload["tag_name"]
        release_url = _release_url(body)
        return GitLabReleasePublishResult(
            status_code=response.status_code,
            project=self.project,
            endpoint=self.release_endpoint,
            release_tag=release_tag,
            release_url=release_url,
            dry_run=False,
            payload={
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "gitlab_release_tag": release_tag,
                    "gitlab_release_url": release_url,
                },
            },
        )

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "max-gitlab-releases-publisher/1",
        }


GitLabReleasesPublisher = GitLabReleasePublisher


def _gitlab_release_request(payload: dict[str, Any]) -> dict[str, Any]:
    request_payload: dict[str, Any] = {
        "tag_name": _validate_tag_name(payload.get("tag_name")),
        "name": _required_text(payload.get("name"), "GitLab release name is required"),
        "description": _required_text(
            payload.get("description"),
            "GitLab release description is required",
        ),
    }
    if payload.get("ref"):
        request_payload["ref"] = _required_text(
            payload.get("ref"),
            "GitLab release ref is required",
        )
    return request_payload


def _coerce_artifact(artifact: BuildableUnit | dict[str, Any]) -> dict[str, Any]:
    if isinstance(artifact, BuildableUnit):
        return {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {
                "system": "max",
                "type": "idea",
                "idea_id": artifact.id,
                "status": artifact.status,
                "domain": artifact.domain,
                "category": artifact.category,
                "created_at": artifact.created_at.isoformat(),
                "updated_at": artifact.updated_at.isoformat(),
            },
            "project": {
                "title": artifact.title,
                "summary": artifact.one_liner,
                "target_users": artifact.target_users,
                "specific_user": artifact.specific_user,
                "buyer": artifact.buyer,
                "workflow_context": artifact.workflow_context,
            },
            "problem": {"statement": artifact.problem},
            "solution": {"approach": artifact.solution},
            "execution": {
                "mvp_scope": [artifact.value_proposition],
                "validation_plan": artifact.validation_plan,
            },
            "evidence": {
                "rationale": artifact.evidence_rationale,
                "insight_ids": artifact.inspiring_insights,
                "signal_ids": artifact.evidence_signals,
                "source_idea_ids": artifact.source_idea_ids,
            },
            "quality": {
                "quality_score": artifact.quality_score,
                "novelty_score": artifact.novelty_score,
                "usefulness_score": artifact.usefulness_score,
                "rejection_tags": artifact.rejection_tags,
            },
        }
    return artifact


def _release_name(artifact: dict[str, Any], *, explicit_name: str | None) -> str:
    if explicit_name:
        return explicit_name
    project = _dict_value(artifact, "project")
    source = _dict_value(artifact, "source")
    return _text_or_placeholder(
        project.get("title")
        or artifact.get("title")
        or source.get("design_brief_id")
        or source.get("idea_id")
        or "Generated Release"
    )


def _release_description(artifact: dict[str, Any], *, title: str) -> str:
    project = _dict_value(artifact, "project")
    problem = _dict_value(artifact, "problem")
    solution = _dict_value(artifact, "solution")
    execution = _dict_value(artifact, "execution")
    evidence = _dict_value(artifact, "evidence")
    source = _dict_value(artifact, "source")
    evaluation = artifact.get("evaluation") if isinstance(artifact.get("evaluation"), dict) else {}

    lines = [
        f"## {title}",
        "",
        _text_or_placeholder(project.get("summary") or artifact.get("summary")),
        "",
        "### Source",
        f"- Idea ID: {_text_or_placeholder(source.get('idea_id'))}",
        f"- Design brief ID: {_text_or_placeholder(source.get('design_brief_id'))}",
        f"- Status: {_text_or_placeholder(source.get('status'))}",
        f"- Domain: {_text_or_placeholder(source.get('domain'))}",
        f"- Category: {_text_or_placeholder(source.get('category'))}",
        "",
        "### Problem",
        _text_or_placeholder(problem.get("statement")),
        "",
        "### Solution",
        _text_or_placeholder(solution.get("approach")),
        "",
        "### Execution",
        f"- Target users: {_text_or_placeholder(project.get('target_users'))}",
        f"- Specific user: {_text_or_placeholder(project.get('specific_user'))}",
        f"- Buyer: {_text_or_placeholder(project.get('buyer'))}",
        f"- Workflow context: {_text_or_placeholder(project.get('workflow_context'))}",
        "",
        "### MVP Scope",
    ]
    lines.extend(_bullet_list(execution.get("mvp_scope")))
    lines.extend(
        [
            "",
            "### Validation",
            _text_or_placeholder(execution.get("validation_plan")),
            "",
            "### Evidence",
            f"- Rationale: {_text_or_placeholder(evidence.get('rationale'))}",
            f"- Insights: {', '.join(evidence.get('insight_ids') or []) or 'None'}",
            f"- Signals: {', '.join(evidence.get('signal_ids') or []) or 'None'}",
            "",
            "### Evaluation",
            f"- Recommendation: {_text_or_placeholder(evaluation.get('recommendation'))}",
            f"- Overall score: {_score_text(evaluation.get('overall_score'))}",
            "",
            "### Artifact Preview",
            "```json",
            json.dumps(artifact, indent=2, sort_keys=True),
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


def _is_duplicate_release_response(response: httpx.Response) -> bool:
    if response.status_code != 409:
        return False
    return "already exists" in response.text.lower()


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise GitLabReleasePublishError(
            "GitLab release publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    if not isinstance(body, dict):
        raise GitLabReleasePublishError(
            "GitLab release publish failed: response JSON was not an object",
            status_code=response.status_code,
        )
    return body


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


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


def _release_url(body: dict[str, Any]) -> str | None:
    links = body.get("_links")
    if isinstance(links, dict):
        value = links.get("self")
        if value:
            return str(value)
    value = body.get("url")
    return str(value) if value else None


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value else ""
    if not text:
        raise GitLabReleasePublishError(message)
    return text


def _required_url(value: object) -> str:
    raw = _required_text(value, "GitLab base_url is required").rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise GitLabReleasePublishError("GitLab base_url must be an absolute http(s) URL")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = _redact_text(response.text.strip())
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _score_text(value: object) -> str:
    if isinstance(value, int | float):
        return f"{value:.1f}"
    return _text_or_placeholder(value)


def _text_or_placeholder(value: object) -> str:
    text = str(value).strip() if value else ""
    return text or "Not specified"


def _validate_tag_name(tag_name: object) -> str:
    value = _required_text(tag_name, "GitLab release tag name is required")
    if len(value) > 255 or value.startswith("-"):
        raise GitLabReleasePublishError("GitLab release tag name is invalid")
    if any(char.isspace() for char in value):
        raise GitLabReleasePublishError("GitLab release tag name must not contain whitespace")
    if value.endswith(".") or ".." in value or "@{" in value:
        raise GitLabReleasePublishError("GitLab release tag name is invalid")
    if value.endswith(".lock") or value.startswith("/") or value.endswith("/"):
        raise GitLabReleasePublishError("GitLab release tag name is invalid")
    if "//" in value or re.search(r"[\000-\037\177~^:?*\\[]", value):
        raise GitLabReleasePublishError("GitLab release tag name is invalid")
    return value
