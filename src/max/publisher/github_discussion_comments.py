"""GitHub Discussion comment publisher for Max summaries."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._summary_payloads import summary_markdown
from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, redact_text, required_text, required_url, response_json, response_preview

DEFAULT_GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
ADD_DISCUSSION_COMMENT_MUTATION = "mutation AddDiscussionComment($discussionId: ID!, $body: String!) { addDiscussionComment(input: {discussionId: $discussionId, body: $body}) { comment { id url } } }"


class GitHubDiscussionCommentPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class GitHubDiscussionCommentPublishResult:
    status_code: int | None
    comment_id: str | None
    comment_url: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class GitHubDiscussionCommentPublisher:
    def __init__(self, *, token: str | None = None, discussion_id: str | None = None, graphql_url: str = DEFAULT_GITHUB_GRAPHQL_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.token = optional_text(token)
        self.discussion_id = optional_text(discussion_id)
        self.graphql_url = required_url(graphql_url, "GitHub GraphQL URL must be an absolute http(s) URL")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> GitHubDiscussionCommentPublisher:
        return cls(token=kwargs.pop("token", None) or os.getenv("GITHUB_TOKEN"), discussion_id=kwargs.pop("discussion_id", None) or os.getenv("GITHUB_DISCUSSION_ID"), graphql_url=kwargs.pop("graphql_url", None) or os.getenv("GITHUB_GRAPHQL_URL", DEFAULT_GITHUB_GRAPHQL_URL), **kwargs)

    def build_comment_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        discussion_id = required_text(self.discussion_id, "GITHUB_DISCUSSION_ID is required for GitHub discussion comment publishing")
        return {"query": ADD_DISCUSSION_COMMENT_MUTATION, "variables": {"discussionId": discussion_id, "body": summary_markdown(payload)}}

    def publish(self, payload: dict[str, Any], *, dry_run: bool = True) -> GitHubDiscussionCommentPublishResult:
        request_payload = self.build_comment_payload(payload)
        if dry_run:
            return GitHubDiscussionCommentPublishResult(None, None, None, True, self.graphql_url, request_payload)
        if not self.token:
            raise GitHubDiscussionCommentPublishError("GITHUB_TOKEN is required for live GitHub discussion comment publishing; use dry_run to preview")
        response = self._post(request_payload)
        body = response_json(response, GitHubDiscussionCommentPublishError, "GitHub discussion comment publish failed: response was not valid JSON")
        if body.get("errors"):
            raise GitHubDiscussionCommentPublishError(f"GitHub discussion comment publish failed: {body['errors']}", status_code=response.status_code, token=self.token)
        comment = (((body.get("data") or {}).get("addDiscussionComment") or {}).get("comment") or {})
        return GitHubDiscussionCommentPublishResult(response.status_code, _text(comment.get("id")), _text(comment.get("url")), False, self.graphql_url, request_payload, body)

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.graphql_url, json=payload, headers=self._headers(), timeout=self.timeout)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise GitHubDiscussionCommentPublishError(f"GitHub discussion comment publish failed for {self.graphql_url}: {exc}", token=self.token) from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise GitHubDiscussionCommentPublishError(f"GitHub discussion comment publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.token])}", status_code=response.status_code, token=self.token)
        return response

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {"Accept": "application/json", "Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "User-Agent": "max-github-discussion-comments-publisher/1"}


def _text(value: object) -> str | None:
    return str(value) if value else None
