"""GitLab note publisher for Max ideas and design briefs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, dict_value, join_list, optional_text, redact_text, required_text, required_url, score_text, source_id, text_or_placeholder, title

DEFAULT_API_URL = "https://gitlab.com/api/v4"


class GitLabNotePublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class GitLabNotePublishResult:
    status_code: int | None
    note_id: str | None
    dry_run: bool
    endpoint: str
    body: str
    response: dict[str, Any] | None = None


class GitLabNotePublisher:
    def __init__(
        self,
        *,
        project_id: str | None = None,
        resource_type: str = "issue",
        resource_iid: str | None = None,
        token: str | None = None,
        api_url: str = DEFAULT_API_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.project_id = optional_text(project_id)
        self.resource_type = optional_text(resource_type) or "issue"
        self.resource_iid = optional_text(resource_iid)
        self.token = optional_text(token)
        self.api_url = required_url(api_url, "GitLab api_url must be an absolute http(s) URL")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> GitLabNotePublisher:
        return cls(
            project_id=kwargs.pop("project_id", None) or os.getenv("GITLAB_PROJECT_ID"),
            resource_type=kwargs.pop("resource_type", None) or os.getenv("GITLAB_RESOURCE_TYPE", "issue"),
            resource_iid=kwargs.pop("resource_iid", None) or os.getenv("GITLAB_RESOURCE_IID") or os.getenv("GITLAB_RESOURCE_ID"),
            token=kwargs.pop("token", None) or os.getenv("GITLAB_PRIVATE_TOKEN"),
            api_url=kwargs.pop("api_url", None) or os.getenv("GITLAB_API_URL", DEFAULT_API_URL),
            **kwargs,
        )

    def notes_endpoint(self) -> str:
        project = required_text(self.project_id, "GITLAB_PROJECT_ID is required for GitLab note publishing")
        iid = required_text(self.resource_iid, "GITLAB_RESOURCE_IID is required for GitLab note publishing")
        encoded_project = quote(project, safe="")
        encoded_iid = quote(iid, safe="")
        if self.resource_type == "issue":
            return f"{self.api_url}/projects/{encoded_project}/issues/{encoded_iid}/notes"
        if self.resource_type == "merge_request":
            return f"{self.api_url}/projects/{encoded_project}/merge_requests/{encoded_iid}/notes"
        if self.resource_type == "epic":
            return f"{self.api_url}/groups/{encoded_project}/epics/{encoded_iid}/notes"
        raise GitLabNotePublishError("GitLab resource_type must be one of issue, merge_request, or epic", token=self.token)

    def build_body(self, payload: dict[str, Any]) -> str:
        return _render_body(payload)

    def publish(self, payload: dict[str, Any], *, dry_run: bool = True) -> GitLabNotePublishResult:
        endpoint = self.notes_endpoint()
        body = self.build_body(payload)
        if dry_run:
            return GitLabNotePublishResult(None, None, True, endpoint, body)
        if not self.token:
            raise GitLabNotePublishError("GITLAB_PRIVATE_TOKEN is required for live GitLab note publishing; use dry_run to preview")
        response = self._post(endpoint, body)
        try:
            response_body = response.json()
        except ValueError:
            response_body = {}
        return GitLabNotePublishResult(response.status_code, optional_text(response_body.get("id")) if isinstance(response_body, dict) else None, False, endpoint, body, response_body if isinstance(response_body, dict) else {})

    def _post(self, endpoint: str, body: str) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(endpoint, json={"body": body}, headers=self._headers(), timeout=self.timeout)
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise GitLabNotePublishError(f"GitLab note publish failed with HTTP {response.status_code}: {redact_text(response.text, secrets=[self.token])}", status_code=response.status_code, token=self.token)
        return response

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {"Accept": "application/json", "PRIVATE-TOKEN": self.token, "Content-Type": "application/json", "User-Agent": "max-gitlab-notes-publisher/1"}


GitLabNotesPublisher = GitLabNotePublisher


def publish_gitlab_note(payload: dict[str, Any], **kwargs: Any) -> GitLabNotePublishResult:
    publisher = GitLabNotePublisher.from_env(**{key: value for key, value in kwargs.items() if key != "dry_run"})
    return publisher.publish(payload, dry_run=kwargs.get("dry_run", True))


def _render_body(payload: dict[str, Any]) -> str:
    if "design_brief" in payload:
        brief = dict_value(payload, "design_brief")
        return "\n".join([f"## {optional_text(brief.get('title')) or 'Max design brief'}", "", f"- Brief ID: {text_or_placeholder(brief.get('id'))}", f"- Readiness score: {score_text(brief.get('readiness_score'))}", f"- Recommendation: {text_or_placeholder(brief.get('recommendation'))}", f"- Source ideas: {join_list(brief.get('source_idea_ids'))}", "", text_or_placeholder(brief.get("markdown") or brief.get("summary"))])
    source = dict_value(payload, "source")
    project = dict_value(payload, "project")
    evaluation = dict_value(payload, "evaluation")
    evidence = dict_value(payload, "evidence")
    return "\n".join([f"## {title(payload, fallback='Max idea')}", "", text_or_placeholder(project.get("summary")), "", f"- Source ID: {text_or_placeholder(source_id(source))}", f"- Score: {score_text(evaluation.get('overall_score'))}", f"- Recommendation: {text_or_placeholder(evaluation.get('recommendation'))}", f"- Evidence: insights={join_list(evidence.get('insight_ids'))}; signals={join_list(evidence.get('signal_ids'))}"])
