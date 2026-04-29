"""GitHub Gist publisher for generated idea summaries."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx


DEFAULT_GITHUB_API_URL = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_FILENAME = "idea.md"


class GitHubGistPublishError(RuntimeError):
    """Raised when a GitHub Gist publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GitHubGistPayload:
    """GitHub Gist creation payload plus Max-specific metadata."""

    description: str
    public: bool
    files: dict[str, dict[str, str]]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable Gist payload."""
        return {
            "description": self.description,
            "public": self.public,
            "files": self.files,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class GitHubGistPublishResult:
    """Summary of a GitHub Gist publish or dry run."""

    status_code: int | None
    gist_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class GitHubGistPublisher:
    """Build and optionally create GitHub Gists from idea TactSpec previews."""

    def __init__(
        self,
        *,
        token: str | None = None,
        api_url: str = DEFAULT_GITHUB_API_URL,
        public: bool = False,
        filename: str = DEFAULT_FILENAME,
        description: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.token = token
        self.api_url = api_url.rstrip("/")
        self.public = public
        self.filename = _validate_filename(filename)
        self.description = description
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        token: str | None = None,
        api_url: str | None = None,
        public: bool = False,
        filename: str = DEFAULT_FILENAME,
        description: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> GitHubGistPublisher:
        """Create a publisher using API values first, then environment variables."""
        return cls(
            token=token or os.getenv("GITHUB_TOKEN"),
            api_url=api_url or os.getenv("GITHUB_API_URL", DEFAULT_GITHUB_API_URL),
            public=public,
            filename=filename,
            description=description,
            timeout=timeout,
            client=client,
        )

    @property
    def gist_endpoint(self) -> str:
        """Return the GitHub API endpoint used for Gist creation."""
        return f"{self.api_url}/gists"

    def build_gist_payload(
        self,
        tact_spec: dict[str, Any],
        *,
        evidence_links: list[str] | None = None,
    ) -> GitHubGistPayload:
        """Convert a generated TactSpec preview into a GitHub Gist payload."""
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")
        description = self.description or _gist_description(
            project.get("title"),
            source.get("idea_id"),
        )
        metadata = {
            "publisher": "max.github_gists",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "idea"),
            "idea_id": source.get("idea_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "public": self.public,
            "filename": self.filename,
        }
        return GitHubGistPayload(
            description=description,
            public=self.public,
            files={
                self.filename: {
                    "content": _gist_markdown(tact_spec, evidence_links=evidence_links),
                }
            },
            metadata=metadata,
        )

    def publish(
        self,
        tact_spec: dict[str, Any],
        *,
        dry_run: bool = True,
        evidence_links: list[str] | None = None,
    ) -> GitHubGistPublishResult:
        """Build the Gist payload and optionally create it in GitHub."""
        gist_payload = self.build_gist_payload(
            tact_spec,
            evidence_links=evidence_links,
        )
        return self.publish_payload(gist_payload, dry_run=dry_run)

    def build_design_brief_payload(
        self,
        design_brief: dict[str, Any],
        *,
        markdown: str,
    ) -> GitHubGistPayload:
        """Convert a persisted design brief Markdown export into a GitHub Gist payload."""
        brief_id = design_brief.get("id")
        title = design_brief.get("title") or brief_id or "Design Brief"
        description = self.description or f"Max design brief: {str(title).strip()}"
        metadata = {
            "publisher": "max.github_gists",
            "source_system": "max",
            "source_type": "design_brief",
            "design_brief_id": brief_id,
            "domain": design_brief.get("domain"),
            "theme": design_brief.get("theme"),
            "lead_idea_id": design_brief.get("lead_idea_id"),
            "source_idea_ids": _source_idea_ids(design_brief.get("source_idea_ids")),
            "public": self.public,
            "filename": self.filename,
        }
        return GitHubGistPayload(
            description=description,
            public=self.public,
            files={self.filename: {"content": markdown}},
            metadata=metadata,
        )

    def publish_design_brief(
        self,
        design_brief: dict[str, Any],
        *,
        markdown: str,
        dry_run: bool = True,
    ) -> GitHubGistPublishResult:
        """Build the design brief Gist payload and optionally create it in GitHub."""
        return self.publish_payload(
            self.build_design_brief_payload(design_brief, markdown=markdown),
            dry_run=dry_run,
        )

    def publish_payload(
        self,
        gist_payload: GitHubGistPayload,
        *,
        dry_run: bool = True,
    ) -> GitHubGistPublishResult:
        """Optionally create an already-built Gist payload in GitHub."""
        payload = gist_payload.to_dict()
        if dry_run:
            return GitHubGistPublishResult(
                status_code=None,
                gist_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self.token:
            raise GitHubGistPublishError(
                "GITHUB_TOKEN is required for live GitHub Gist publishing; use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.gist_endpoint,
                    json={
                        "description": payload["description"],
                        "public": payload["public"],
                        "files": payload["files"],
                    },
                    headers={
                        "Accept": "application/vnd.github+json",
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                        "User-Agent": "max-github-gists-publisher/1",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise GitHubGistPublishError(
                    f"GitHub Gist publish failed for {self.gist_endpoint}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise GitHubGistPublishError(
                f"GitHub Gist publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        gist_url = _gist_url(response)
        return GitHubGistPublishResult(
            status_code=response.status_code,
            gist_url=gist_url,
            dry_run=False,
            payload={
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "github_gist_url": gist_url,
                    "github_gist_id": _gist_id(response),
                },
            },
        )


GitHubGistsPublisher = GitHubGistPublisher


def _gist_description(title: object, idea_id: object) -> str:
    base = str(title).strip() if title else str(idea_id or "Generated idea").strip()
    return f"Max idea: {base}"


def _gist_markdown(
    tact_spec: dict[str, Any],
    *,
    evidence_links: list[str] | None = None,
) -> str:
    project = _dict_value(tact_spec, "project")
    problem = _dict_value(tact_spec, "problem")
    solution = _dict_value(tact_spec, "solution")
    execution = _dict_value(tact_spec, "execution")
    evidence = _dict_value(tact_spec, "evidence")
    source = _dict_value(tact_spec, "source")
    evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}
    links = _evidence_links(evidence, evidence_links)

    lines = [
        f"# {project.get('title') or source.get('idea_id') or 'Generated Idea'}",
        "",
        _text_or_placeholder(project.get("summary")),
        "",
        "## Source",
        f"- Idea ID: {source.get('idea_id', '')}",
        f"- Status: {source.get('status', '')}",
        f"- Domain: {source.get('domain', '')}",
        f"- Category: {source.get('category', '')}",
        "",
        "## Problem",
        _text_or_placeholder(problem.get("statement")),
        "",
        "## Solution",
        _text_or_placeholder(solution.get("approach")),
        "",
        "## Execution",
        f"- Target users: {_text_or_placeholder(project.get('target_users'))}",
        f"- Specific user: {_text_or_placeholder(project.get('specific_user'))}",
        f"- Buyer: {_text_or_placeholder(project.get('buyer'))}",
        f"- Workflow context: {_text_or_placeholder(project.get('workflow_context'))}",
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
        ]
    )
    if links:
        lines.extend(["", "## Evidence Links"])
        lines.extend(f"- {link}" for link in links)
    lines.extend(
        [
            "",
            "## Evaluation",
            f"- Recommendation: {_text_or_placeholder(evaluation.get('recommendation'))}",
            f"- Overall score: {_score_text(evaluation.get('overall_score'))}",
            "",
            "## TactSpec Preview",
            "```json",
            json.dumps(tact_spec, indent=2, sort_keys=True),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _evidence_links(evidence: dict[str, Any], links: list[str] | None) -> list[str]:
    values: list[str] = []
    for candidate in links or evidence.get("links") or []:
        text = str(candidate).strip()
        if text and text not in values:
            values.append(text)
    return values


def _source_idea_ids(value: object) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, list | tuple | set):
        return []

    values: list[str] = []
    for candidate in value:
        text = candidate.strip() if isinstance(candidate, str) else ""
        if text and text not in values:
            values.append(text)
    return values


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


def _validate_filename(filename: str) -> str:
    value = filename.strip()
    if not value or "/" in value or "\\" in value:
        raise GitHubGistPublishError("GitHub Gist filename must be a single file name")
    return value


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _gist_url(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        url = body.get("html_url")
        return str(url) if url else None
    return None


def _gist_id(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        gist_id = body.get("id")
        return str(gist_id) if gist_id else None
    return None
