"""GitHub Actions workflow_dispatch publisher for generated Max artifacts."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx


DEFAULT_GITHUB_API_URL = "https://api.github.com"
DEFAULT_GITHUB_REF = "main"
DEFAULT_TIMEOUT_SECONDS = 10.0
REDACTED = "[redacted]"


class GitHubWorkflowDispatchPublishError(RuntimeError):
    """Raised when a GitHub Actions workflow dispatch cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GitHubWorkflowDispatchPayload:
    """GitHub workflow_dispatch request plus Max-specific metadata."""

    owner: str
    repo: str
    repository: str
    workflow_id: str
    ref: str
    inputs: dict[str, str]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dispatch payload."""
        return {
            "owner": self.owner,
            "repo": self.repo,
            "repository": self.repository,
            "workflow_id": self.workflow_id,
            "ref": self.ref,
            "inputs": self.inputs,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class GitHubWorkflowDispatchPublishResult:
    """Summary of a GitHub workflow_dispatch publish or dry run."""

    status_code: int | None
    owner: str
    repo: str
    repository: str
    workflow_id: str
    endpoint: str
    dry_run: bool
    payload: dict[str, Any]


class GitHubWorkflowDispatchPublisher:
    """Trigger GitHub Actions workflow_dispatch events from Max artifacts."""

    def __init__(
        self,
        repository: str | None = None,
        *,
        owner: str | None = None,
        repo: str | None = None,
        workflow_id: str | None = None,
        token: str | None = None,
        api_url: str = DEFAULT_GITHUB_API_URL,
        ref: str | None = None,
        inputs: dict[str, Any] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.repository = _resolve_repository(repository, owner=owner, repo=repo)
        self.owner, self.repo = self.repository.split("/", 1)
        self.workflow_id = _required_text(
            workflow_id, "GitHub Actions workflow_id is required"
        )
        self.token = _optional_text(token)
        self.api_url = api_url.rstrip("/")
        self.ref = _optional_text(ref) or DEFAULT_GITHUB_REF
        self.inputs = _string_inputs(inputs or {})
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        repository: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
        workflow_id: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        ref: str | None = None,
        inputs: dict[str, Any] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> GitHubWorkflowDispatchPublisher:
        """Create a publisher using explicit values first, then environment variables."""
        resolved_repository = repository or os.getenv("GITHUB_REPOSITORY")
        if not resolved_repository and not (owner and repo):
            raise GitHubWorkflowDispatchPublishError(
                "GitHub repository is required; pass repository, pass owner/repo, "
                "or set GITHUB_REPOSITORY"
            )
        return cls(
            resolved_repository,
            owner=owner,
            repo=repo,
            workflow_id=workflow_id or os.getenv("GITHUB_WORKFLOW_ID"),
            token=token or os.getenv("GITHUB_TOKEN"),
            api_url=api_url or os.getenv("GITHUB_API_URL", DEFAULT_GITHUB_API_URL),
            ref=ref or os.getenv("GITHUB_REF") or os.getenv("GITHUB_WORKFLOW_REF"),
            inputs=inputs,
            timeout=timeout,
            client=client,
        )

    @property
    def dispatch_endpoint(self) -> str:
        """Return the GitHub API endpoint used for workflow dispatch."""
        return (
            f"{self.api_url}/repos/{self.owner}/{self.repo}/actions/workflows/"
            f"{self.workflow_id}/dispatches"
        )

    def build_dispatch_payload(
        self,
        artifact: dict[str, Any],
        *,
        ref: str | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> GitHubWorkflowDispatchPayload:
        """Convert a generated spec or design brief artifact into a dispatch payload."""
        source = _dict_value(artifact, "source")
        brief = _brief_payload(artifact)
        idea_id = source.get("idea_id") or brief.get("lead_idea_id") or artifact.get("idea_id")
        design_brief_id = (
            source.get("design_brief_id") or brief.get("id") or artifact.get("design_brief_id")
        )
        resolved_ref = _optional_text(ref) or self.ref
        resolved_inputs = {
            **self.inputs,
            **_artifact_inputs(
                artifact,
                source=source,
                brief=brief,
                idea_id=idea_id,
                design_brief_id=design_brief_id,
            ),
            **_string_inputs(inputs or {}),
        }
        metadata = {
            "publisher": "max.github_workflow_dispatch",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type") or ("design_brief" if brief else "artifact"),
            "idea_id": idea_id,
            "design_brief_id": design_brief_id,
            "schema_version": artifact.get("schema_version"),
            "kind": artifact.get("kind"),
            "repository": self.repository,
            "workflow_id": self.workflow_id,
            "ref": resolved_ref,
        }
        return GitHubWorkflowDispatchPayload(
            owner=self.owner,
            repo=self.repo,
            repository=self.repository,
            workflow_id=self.workflow_id,
            ref=resolved_ref,
            inputs=resolved_inputs,
            metadata=metadata,
        )

    def publish(
        self,
        artifact: dict[str, Any],
        *,
        dry_run: bool = True,
        ref: str | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> GitHubWorkflowDispatchPublishResult:
        """Build the dispatch payload and optionally trigger the GitHub workflow."""
        payload = self.build_dispatch_payload(artifact, ref=ref, inputs=inputs).to_dict()
        return self.publish_dispatch_payload(payload, dry_run=dry_run)

    def publish_dispatch_payload(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> GitHubWorkflowDispatchPublishResult:
        """Publish a pre-rendered GitHub workflow_dispatch payload."""
        payload = _normalize_payload(payload)
        result_payload = _redact_payload(payload)
        if dry_run:
            return GitHubWorkflowDispatchPublishResult(
                status_code=None,
                owner=self.owner,
                repo=self.repo,
                repository=self.repository,
                workflow_id=self.workflow_id,
                endpoint=self.dispatch_endpoint,
                dry_run=True,
                payload=result_payload,
            )

        if not self.token:
            raise GitHubWorkflowDispatchPublishError(
                "GITHUB_TOKEN is required for live GitHub workflow_dispatch publishing; "
                "use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.dispatch_endpoint,
                    json=_github_dispatch_request_payload(payload),
                    headers={
                        "Accept": "application/vnd.github+json",
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                        "User-Agent": "max-github-workflow-dispatch-publisher/1",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise GitHubWorkflowDispatchPublishError(
                    _redact_text(
                        f"GitHub workflow_dispatch publish failed for "
                        f"{self.dispatch_endpoint}: {exc}",
                        self.token,
                    )
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise GitHubWorkflowDispatchPublishError(
                _redact_text(
                    f"GitHub workflow_dispatch publish failed with HTTP "
                    f"{response.status_code}: {_response_body_preview(response)}",
                    self.token,
                ),
                status_code=response.status_code,
            )

        return GitHubWorkflowDispatchPublishResult(
            status_code=response.status_code,
            owner=self.owner,
            repo=self.repo,
            repository=self.repository,
            workflow_id=self.workflow_id,
            endpoint=self.dispatch_endpoint,
            dry_run=False,
            payload={
                **result_payload,
                "metadata": {
                    **result_payload["metadata"],
                    "github_workflow_dispatch_status_code": response.status_code,
                },
            },
        )


GitHubWorkflowDispatchesPublisher = GitHubWorkflowDispatchPublisher


def _artifact_inputs(
    artifact: dict[str, Any],
    *,
    source: dict[str, Any],
    brief: dict[str, Any],
    idea_id: object,
    design_brief_id: object,
) -> dict[str, str]:
    project = _dict_value(artifact, "project")
    values = {
        "artifact_kind": artifact.get("kind"),
        "schema_version": artifact.get("schema_version"),
        "idea_id": idea_id,
        "design_brief_id": design_brief_id,
        "source_type": source.get("type") or ("design_brief" if brief else "artifact"),
        "title": project.get("title") or brief.get("title") or artifact.get("title"),
    }
    return _string_inputs({key: value for key, value in values.items() if value is not None})


def _brief_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    nested = artifact.get("design_brief")
    return nested if isinstance(nested, dict) else {}


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _github_dispatch_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref": _required_text(payload.get("ref"), "GitHub workflow_dispatch ref is required"),
        "inputs": _string_inputs(payload.get("inputs") or {}),
    }


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(payload)
    redacted["inputs"] = _redact_mapping(_string_inputs(redacted.get("inputs") or {}))
    redacted["metadata"] = _redact_mapping(dict(redacted.get("metadata") or {}))
    return redacted


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["ref"] = _required_text(
        normalized.get("ref"), "GitHub workflow_dispatch ref is required"
    )
    normalized["inputs"] = _string_inputs(normalized.get("inputs") or {})
    normalized["metadata"] = dict(normalized.get("metadata") or {})
    return normalized


def _redact_mapping(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: REDACTED if _is_secret_key(key) else value
        for key, value in values.items()
    }


def _redact_text(text: str, token: str | None) -> str:
    redacted = text
    if token:
        redacted = redacted.replace(token, REDACTED)
    return redacted


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value else ""
    if not text:
        raise GitHubWorkflowDispatchPublishError(message)
    return text


def _resolve_repository(
    repository: str | None,
    *,
    owner: str | None,
    repo: str | None,
) -> str:
    if repository and (owner or repo):
        raise GitHubWorkflowDispatchPublishError(
            "Pass either repository or owner/repo, not both"
        )
    if repository:
        return _validate_repository(repository)
    owner_text = _optional_text(owner)
    repo_text = _optional_text(repo)
    if owner_text and repo_text:
        return _validate_repository(f"{owner_text}/{repo_text}")
    raise GitHubWorkflowDispatchPublishError(
        "GitHub repository is required; pass repository or owner/repo"
    )


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = _sanitize_response_text(response).strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _string_inputs(values: dict[str, Any]) -> dict[str, str]:
    if not isinstance(values, dict):
        raise GitHubWorkflowDispatchPublishError("GitHub workflow inputs must be a mapping")
    converted: dict[str, str] = {}
    for key, value in values.items():
        text_key = _required_text(key, "GitHub workflow input names must be non-empty")
        if value is None:
            continue
        converted[text_key] = str(value)
    return converted


def _is_secret_key(key: str) -> bool:
    normalized = key.lower()
    parts = [part for part in normalized.replace("-", "_").split("_") if part]
    return any(part in {"token", "secret", "password", "pat"} for part in parts)


def _sanitize_response_text(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text
    return json.dumps(_sanitize_response_value(body), separators=(",", ":"))


def _sanitize_response_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                REDACTED
                if _is_secret_key(str(key)) or _looks_secret(value_item)
                else _sanitize_response_value(value_item)
            )
            for key, value_item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_response_value(item) for item in value]
    if _looks_secret(value):
        return REDACTED
    return value


def _looks_secret(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.lower()
    return "token" in normalized or "secret" in normalized


def _validate_repository(repository: str) -> str:
    value = repository.strip()
    if value.count("/") != 1 or any(not part for part in value.split("/", 1)):
        raise GitHubWorkflowDispatchPublishError(
            "GitHub repository must be in owner/repo format"
        )
    return value
