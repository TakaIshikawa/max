"""GitHub release note publisher for Max summaries."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._summary_payloads import summary_markdown, summary_metadata, summary_title
from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, quote_path, redact_text, required_text, required_url, response_json, response_preview

DEFAULT_GITHUB_API_URL = "https://api.github.com"


class GitHubReleaseNotePublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class GitHubReleaseNotePublishResult:
    status_code: int | None
    release_id: str | None
    release_url: str | None
    dry_run: bool
    endpoint: str
    headers: dict[str, str]
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class GitHubReleaseNotePublisher:
    def __init__(self, repository: str | None = None, *, owner: str | None = None, repo: str | None = None, token: str | None = None, tag_name: str | None = None, release_name: str | None = None, target_commitish: str | None = None, draft: bool = True, prerelease: bool = False, api_url: str = DEFAULT_GITHUB_API_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.repository = _resolve_repository(repository, owner=owner, repo=repo)
        self.owner, self.repo = self.repository.split("/", 1)
        self.token = optional_text(token)
        self.tag_name = optional_text(tag_name)
        self.release_name = optional_text(release_name)
        self.target_commitish = optional_text(target_commitish)
        self.draft = bool(draft)
        self.prerelease = bool(prerelease)
        self.api_url = required_url(api_url, "GitHub API URL must be an absolute http(s) URL")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> GitHubReleaseNotePublisher:
        return cls(
            repository=kwargs.pop("repository", None) or os.getenv("GITHUB_REPOSITORY"),
            owner=kwargs.pop("owner", None),
            repo=kwargs.pop("repo", None),
            token=kwargs.pop("token", None) or os.getenv("GITHUB_TOKEN"),
            tag_name=kwargs.pop("tag_name", None) or os.getenv("GITHUB_RELEASE_TAG"),
            release_name=kwargs.pop("release_name", None) or os.getenv("GITHUB_RELEASE_NAME"),
            target_commitish=kwargs.pop("target_commitish", None) or os.getenv("GITHUB_TARGET_COMMITISH"),
            api_url=kwargs.pop("api_url", None) or os.getenv("GITHUB_API_URL", DEFAULT_GITHUB_API_URL),
            **kwargs,
        )

    @property
    def endpoint(self) -> str:
        return f"{self.api_url}/repos/{quote_path(self.owner)}/{quote_path(self.repo)}/releases"

    def build_release_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        release_payload: dict[str, Any] = {
            "tag_name": required_text(self.tag_name, "GITHUB_RELEASE_TAG is required for GitHub release note publishing"),
            "name": self.release_name or summary_title(payload),
            "body": summary_markdown(payload),
            "draft": self.draft,
            "prerelease": self.prerelease,
            "metadata": summary_metadata(payload, publisher="max.github_release_notes", extra={"repository": self.repository}),
        }
        if self.target_commitish:
            release_payload["target_commitish"] = self.target_commitish
        return release_payload

    def publish(self, payload: dict[str, Any], *, dry_run: bool = True) -> GitHubReleaseNotePublishResult:
        request_payload = self.build_release_payload(payload)
        if dry_run:
            return GitHubReleaseNotePublishResult(None, None, None, True, self.endpoint, self._headers(redacted=True), request_payload)
        if not self.token:
            raise GitHubReleaseNotePublishError("GITHUB_TOKEN is required for live GitHub release note publishing; use dry_run to preview")
        response = self._post(request_payload)
        body = response_json(response, GitHubReleaseNotePublishError, "GitHub release note publish failed: response was not valid JSON")
        return GitHubReleaseNotePublishResult(response.status_code, _first_text(body, "id"), _first_text(body, "html_url", "url"), False, self.endpoint, self._headers(redacted=True), request_payload, body)

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.endpoint, json=_request_payload(payload), headers=self._headers(), timeout=self.timeout)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise GitHubReleaseNotePublishError(f"GitHub release note publish failed for {self.endpoint}: {exc}", token=self.token) from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise GitHubReleaseNotePublishError(f"GitHub release note publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.token])}", status_code=response.status_code, token=self.token)
        return response

    def _headers(self, *, redacted: bool = False) -> dict[str, str]:
        token = "[REDACTED]" if redacted and self.token else self.token
        headers = {"Accept": "application/vnd.github+json", "Content-Type": "application/json", "User-Agent": "max-github-release-notes-publisher/1", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers


GitHubReleaseNotesPublisher = GitHubReleaseNotePublisher


def publish_github_release_note(payload: dict[str, Any], **kwargs: Any) -> GitHubReleaseNotePublishResult:
    return GitHubReleaseNotePublisher.from_env(**{key: value for key, value in kwargs.items() if key != "dry_run"}).publish(payload, dry_run=kwargs.get("dry_run", True))


def _request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    request = {key: payload[key] for key in ("tag_name", "name", "body", "draft", "prerelease")}
    if payload.get("target_commitish"):
        request["target_commitish"] = payload["target_commitish"]
    return request


def _resolve_repository(repository: str | None, *, owner: str | None, repo: str | None) -> str:
    if repository and (owner or repo):
        raise GitHubReleaseNotePublishError("Pass either repository or owner/repo, not both")
    if repository:
        return _validate_repository(repository)
    owner_text = optional_text(owner)
    repo_text = optional_text(repo)
    if owner_text and repo_text:
        return _validate_repository(f"{owner_text}/{repo_text}")
    raise GitHubReleaseNotePublishError("GITHUB_REPOSITORY is required for GitHub release note publishing; pass repository or owner/repo")


def _validate_repository(repository: str) -> str:
    value = repository.strip()
    if value.count("/") != 1 or any(not part for part in value.split("/", 1)):
        raise GitHubReleaseNotePublishError("GitHub repository must be in owner/repo format")
    return value


def _first_text(body: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = body.get(key)
        if value:
            return str(value)
    return None
