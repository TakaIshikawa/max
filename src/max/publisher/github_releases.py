"""GitHub Releases publisher for generated specs and design briefs."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx


DEFAULT_GITHUB_API_URL = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS = 10.0


class GitHubReleasePublishError(RuntimeError):
    """Raised when a GitHub release publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GitHubReleasePayload:
    """GitHub release creation payload plus Max-specific metadata."""

    owner: str
    repo: str
    repository: str
    tag_name: str
    name: str
    body: str
    draft: bool
    prerelease: bool
    metadata: dict[str, Any]
    target_commitish: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable release payload."""
        payload: dict[str, Any] = {
            "owner": self.owner,
            "repo": self.repo,
            "repository": self.repository,
            "tag_name": self.tag_name,
            "name": self.name,
            "body": self.body,
            "draft": self.draft,
            "prerelease": self.prerelease,
            "metadata": self.metadata,
        }
        if self.target_commitish:
            payload["target_commitish"] = self.target_commitish
        return payload


@dataclass(frozen=True)
class GitHubReleasePublishResult:
    """Summary of a GitHub release publish or dry run."""

    status_code: int | None
    owner: str
    repo: str
    repository: str
    endpoint: str
    release_id: str | None
    release_url: str | None
    upload_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class GitHubReleasePublisher:
    """Create draft GitHub releases from Max artifacts."""

    def __init__(
        self,
        repository: str | None = None,
        *,
        owner: str | None = None,
        repo: str | None = None,
        token: str | None = None,
        api_url: str = DEFAULT_GITHUB_API_URL,
        tag_name: str | None = None,
        release_name: str | None = None,
        body: str | None = None,
        target_commitish: str | None = None,
        draft: bool = True,
        prerelease: bool = False,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.repository = _resolve_repository(repository, owner=owner, repo=repo)
        self.owner, self.repo = self.repository.split("/", 1)
        self.token = _optional_text(token)
        self.api_url = api_url.rstrip("/")
        self.tag_name = _validate_tag_name(tag_name) if tag_name is not None else None
        self.release_name = _optional_text(release_name)
        self.body = _optional_text(body)
        self.target_commitish = _optional_text(target_commitish)
        self.draft = bool(draft)
        self.prerelease = bool(prerelease)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        repository: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        tag_name: str | None = None,
        release_name: str | None = None,
        body: str | None = None,
        target_commitish: str | None = None,
        draft: bool = True,
        prerelease: bool = False,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> GitHubReleasePublisher:
        """Create a publisher using CLI values first, then environment variables."""
        resolved_repository = repository or os.getenv("GITHUB_REPOSITORY")
        if not resolved_repository and (owner or repo):
            resolved_repository = None
        if not resolved_repository and not (owner and repo):
            raise GitHubReleasePublishError(
                "GitHub repository is required; pass repository, pass owner/repo, "
                "or set GITHUB_REPOSITORY"
            )
        return cls(
            resolved_repository,
            owner=owner,
            repo=repo,
            token=token or os.getenv("GITHUB_TOKEN"),
            api_url=api_url or os.getenv("GITHUB_API_URL", DEFAULT_GITHUB_API_URL),
            tag_name=tag_name or os.getenv("GITHUB_RELEASE_TAG"),
            release_name=release_name or os.getenv("GITHUB_RELEASE_NAME"),
            body=body,
            target_commitish=target_commitish or os.getenv("GITHUB_TARGET_COMMITISH"),
            draft=draft,
            prerelease=prerelease,
            timeout=timeout,
            client=client,
        )

    @property
    def release_endpoint(self) -> str:
        """Return the GitHub API endpoint used for release creation."""
        return f"{self.api_url}/repos/{self.owner}/{self.repo}/releases"

    def build_release_payload(
        self,
        artifact: dict[str, Any],
        *,
        tag_name: str | None = None,
        release_name: str | None = None,
        body: str | None = None,
        target_commitish: str | None = None,
        draft: bool | None = None,
        prerelease: bool | None = None,
    ) -> GitHubReleasePayload:
        """Convert a generated spec or artifact into a GitHub release payload."""
        source = _dict_value(artifact, "source")
        resolved_tag = _validate_tag_name(tag_name or self.tag_name)
        resolved_name = _release_name(artifact, explicit_name=release_name or self.release_name)
        metadata = {
            "publisher": "max.github_releases",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "artifact"),
            "idea_id": source.get("idea_id"),
            "design_brief_id": source.get("design_brief_id"),
            "schema_version": artifact.get("schema_version"),
            "kind": artifact.get("kind"),
            "repository": self.repository,
            "tag_name": resolved_tag,
            "release_name": resolved_name,
        }
        return GitHubReleasePayload(
            owner=self.owner,
            repo=self.repo,
            repository=self.repository,
            tag_name=resolved_tag,
            name=resolved_name,
            body=(
                _required_text(body, "GitHub release body is required")
                if body is not None
                else self.body or _release_body(artifact, title=resolved_name)
            ),
            target_commitish=_optional_text(target_commitish) or self.target_commitish,
            draft=self.draft if draft is None else bool(draft),
            prerelease=self.prerelease if prerelease is None else bool(prerelease),
            metadata=metadata,
        )

    def publish(
        self,
        artifact: dict[str, Any],
        *,
        dry_run: bool = True,
        tag_name: str | None = None,
        release_name: str | None = None,
        body: str | None = None,
        target_commitish: str | None = None,
        draft: bool | None = None,
        prerelease: bool | None = None,
    ) -> GitHubReleasePublishResult:
        """Build the release payload and optionally create it in GitHub."""
        payload = self.build_release_payload(
            artifact,
            tag_name=tag_name,
            release_name=release_name,
            body=body,
            target_commitish=target_commitish,
            draft=draft,
            prerelease=prerelease,
        ).to_dict()
        return self.publish_release_payload(payload, dry_run=dry_run)

    def build_design_brief_payload(
        self,
        design_brief: dict[str, Any],
        *,
        markdown: str | None = None,
        tag_name: str | None = None,
        release_name: str | None = None,
        body: str | None = None,
        target_commitish: str | None = None,
        draft: bool | None = None,
        prerelease: bool | None = None,
    ) -> GitHubReleasePayload:
        """Convert a persisted design brief into a GitHub release payload."""
        brief = _brief_payload(design_brief)
        brief_id = brief.get("id")
        resolved_tag = _validate_tag_name(tag_name or self.tag_name)
        resolved_name = _text_or_placeholder(
            release_name
            or self.release_name
            or brief.get("title")
            or brief_id
            or "Design Brief Release"
        )
        metadata = {
            "publisher": "max.github_releases",
            "source_system": "max",
            "source_type": "design_brief",
            "design_brief_id": brief_id,
            "domain": brief.get("domain"),
            "theme": brief.get("theme"),
            "lead_idea_id": brief.get("lead_idea_id"),
            "source_idea_ids": _source_idea_ids(brief.get("source_idea_ids")),
            "repository": self.repository,
            "tag_name": resolved_tag,
            "release_name": resolved_name,
        }
        return GitHubReleasePayload(
            owner=self.owner,
            repo=self.repo,
            repository=self.repository,
            tag_name=resolved_tag,
            name=resolved_name,
            body=(
                _required_text(body, "GitHub release body is required")
                if body is not None
                else self.body
                or _design_brief_body(brief, markdown=markdown, title=resolved_name)
            ),
            target_commitish=_optional_text(target_commitish) or self.target_commitish,
            draft=self.draft if draft is None else bool(draft),
            prerelease=self.prerelease if prerelease is None else bool(prerelease),
            metadata=metadata,
        )

    def publish_design_brief(
        self,
        design_brief: dict[str, Any],
        *,
        markdown: str | None = None,
        dry_run: bool = True,
        tag_name: str | None = None,
        release_name: str | None = None,
        body: str | None = None,
        target_commitish: str | None = None,
        draft: bool | None = None,
        prerelease: bool | None = None,
    ) -> GitHubReleasePublishResult:
        """Build the design brief release payload and optionally publish it."""
        payload = self.build_design_brief_payload(
            design_brief,
            markdown=markdown,
            tag_name=tag_name,
            release_name=release_name,
            body=body,
            target_commitish=target_commitish,
            draft=draft,
            prerelease=prerelease,
        ).to_dict()
        return self.publish_release_payload(payload, dry_run=dry_run)

    def publish_release_payload(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> GitHubReleasePublishResult:
        """Publish a pre-rendered GitHub release payload."""
        payload = {**payload, "tag_name": _validate_tag_name(payload.get("tag_name"))}
        if dry_run:
            return GitHubReleasePublishResult(
                status_code=None,
                owner=self.owner,
                repo=self.repo,
                repository=self.repository,
                endpoint=self.release_endpoint,
                release_id=None,
                release_url=None,
                upload_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self.token:
            raise GitHubReleasePublishError(
                "GITHUB_TOKEN is required for live GitHub release publishing; "
                "use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.release_endpoint,
                    json=_github_release_request_payload(payload),
                    headers={
                        "Accept": "application/vnd.github+json",
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                        "User-Agent": "max-github-releases-publisher/1",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise GitHubReleasePublishError(
                    f"GitHub release publish failed for {self.release_endpoint}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            if _is_duplicate_release_response(response):
                raise GitHubReleasePublishError(
                    f"GitHub release already exists for tag {payload['tag_name']}",
                    status_code=response.status_code,
                )
            raise GitHubReleasePublishError(
                f"GitHub release publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        release_id = _release_id(response)
        release_url = _release_url(response)
        upload_url = _upload_url(response)
        return GitHubReleasePublishResult(
            status_code=response.status_code,
            owner=self.owner,
            repo=self.repo,
            repository=self.repository,
            endpoint=self.release_endpoint,
            release_id=release_id,
            release_url=release_url,
            upload_url=upload_url,
            dry_run=False,
            payload={
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "github_release_id": release_id,
                    "github_release_url": release_url,
                    "github_release_upload_url": upload_url,
                },
            },
        )


GitHubReleasesPublisher = GitHubReleasePublisher


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


def _release_body(artifact: dict[str, Any], *, title: str) -> str:
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


def _design_brief_body(
    design_brief: dict[str, Any],
    *,
    markdown: str | None,
    title: str,
) -> str:
    lines = [
        f"## {title}",
        "",
        _text_or_placeholder(
            design_brief.get("merged_product_concept")
            or design_brief.get("summary")
            or design_brief.get("problem")
        ),
        "",
        "### Source",
        f"- Design brief ID: {_text_or_placeholder(design_brief.get('id'))}",
        f"- Lead idea ID: {_text_or_placeholder(design_brief.get('lead_idea_id'))}",
        f"- Source idea IDs: {', '.join(_source_idea_ids(design_brief.get('source_idea_ids'))) or 'None'}",
        f"- Domain: {_text_or_placeholder(design_brief.get('domain'))}",
        f"- Theme: {_text_or_placeholder(design_brief.get('theme'))}",
        "",
        "### Readiness",
        f"- Status: {_text_or_placeholder(design_brief.get('design_status'))}",
        f"- Score: {_score_text(design_brief.get('readiness_score'))}",
        "",
        "### Validation",
        _text_or_placeholder(design_brief.get("validation_plan")),
    ]
    if markdown:
        lines.extend(["", "### Design Brief", markdown.strip(), ""])
    return "\n".join(lines)


def _github_release_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    request_payload: dict[str, Any] = {
        "tag_name": _validate_tag_name(payload.get("tag_name")),
        "name": _required_text(payload.get("name"), "GitHub release name is required"),
        "body": _required_text(payload.get("body"), "GitHub release body is required"),
        "draft": bool(payload.get("draft")),
        "prerelease": bool(payload.get("prerelease")),
    }
    if payload.get("target_commitish"):
        request_payload["target_commitish"] = _required_text(
            payload.get("target_commitish"),
            "GitHub release target_commitish is required",
        )
    return request_payload


def _brief_payload(design_brief: dict[str, Any]) -> dict[str, Any]:
    nested = design_brief.get("design_brief")
    return nested if isinstance(nested, dict) else design_brief


def _bullet_list(items: object) -> list[str]:
    if not isinstance(items, list) or not items:
        return ["- None"]
    return [f"- {item}" for item in items if item] or ["- None"]


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _is_duplicate_release_response(response: httpx.Response) -> bool:
    if response.status_code != 422:
        return False
    try:
        body = response.json()
    except ValueError:
        return "already_exists" in response.text.lower()
    if not isinstance(body, dict):
        return False
    if "already_exists" in str(body.get("message", "")).lower():
        return True
    errors = body.get("errors")
    if not isinstance(errors, list):
        return False
    for error in errors:
        if not isinstance(error, dict):
            continue
        if error.get("code") == "already_exists":
            return True
    return False


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value else ""
    if not text:
        raise GitHubReleasePublishError(message)
    return text


def _resolve_repository(
    repository: str | None,
    *,
    owner: str | None,
    repo: str | None,
) -> str:
    if repository and (owner or repo):
        raise GitHubReleasePublishError(
            "Pass either repository or owner/repo, not both"
        )
    if repository:
        return _validate_repository(repository)
    owner_text = _optional_text(owner)
    repo_text = _optional_text(repo)
    if owner_text and repo_text:
        return _validate_repository(f"{owner_text}/{repo_text}")
    raise GitHubReleasePublishError(
        "GitHub repository is required; pass repository or owner/repo"
    )


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _score_text(value: object) -> str:
    if isinstance(value, int | float):
        return f"{value:.1f}"
    return _text_or_placeholder(value)


def _source_idea_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    unique: list[str] = []
    for item in value:
        text = str(item).strip() if item else ""
        if text and text not in unique:
            unique.append(text)
    return unique


def _text_or_placeholder(value: object) -> str:
    text = str(value).strip() if value else ""
    return text or "Not specified"


def _validate_repository(repository: str | None) -> str:
    value = repository.strip() if repository else ""
    if value.count("/") != 1 or any(not part for part in value.split("/", 1)):
        raise GitHubReleasePublishError(
            "GitHub repository must be in owner/repo format"
        )
    return value


def _validate_tag_name(tag_name: object) -> str:
    value = _required_text(tag_name, "GitHub release tag name is required")
    if len(value) > 255 or value.startswith("-"):
        raise GitHubReleasePublishError("GitHub release tag name is invalid")
    if any(char.isspace() for char in value):
        raise GitHubReleasePublishError("GitHub release tag name must not contain whitespace")
    if value.endswith(".") or ".." in value or "@{" in value:
        raise GitHubReleasePublishError("GitHub release tag name is invalid")
    if value.endswith(".lock") or value.startswith("/") or value.endswith("/"):
        raise GitHubReleasePublishError("GitHub release tag name is invalid")
    if "//" in value or re.search(r"[\000-\037\177~^:?*\\[]", value):
        raise GitHubReleasePublishError("GitHub release tag name is invalid")
    return value


def _release_id(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        release_id = body.get("id")
        return str(release_id) if release_id else None
    return None


def _release_url(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        url = body.get("html_url")
        return str(url) if url else None
    return None


def _upload_url(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        url = body.get("upload_url")
        return str(url) if url else None
    return None
