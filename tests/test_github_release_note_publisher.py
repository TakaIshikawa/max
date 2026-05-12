from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.github_release_notes import GitHubReleaseNotePublishError, GitHubReleaseNotePublisher
from tests.test_zoom_chat_webhook_publisher import _idea_payload


def test_dry_run_returns_endpoint_redacted_headers_and_release_payload_without_token() -> None:
    publisher = GitHubReleaseNotePublisher("owner/repo", tag_name="v1.2.3", target_commitish="main")

    result = publisher.publish(_idea_payload(), dry_run=True)

    assert result.dry_run is True
    assert result.endpoint == "https://api.github.com/repos/owner/repo/releases"
    assert "Authorization" not in result.headers
    assert result.payload["tag_name"] == "v1.2.3"
    assert result.payload["name"] == "Zoom Chat Publisher"
    assert result.payload["target_commitish"] == "main"
    assert result.payload["draft"] is True
    assert result.payload["prerelease"] is False
    assert "Idea ID: bu-zoom001" in result.payload["body"]
    assert result.payload["metadata"]["publisher"] == "max.github_release_notes"


def test_from_env_reads_github_release_note_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "env-owner/env-repo")
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    monkeypatch.setenv("GITHUB_RELEASE_TAG", "v2.0.0")
    monkeypatch.setenv("GITHUB_RELEASE_NAME", "Env release")
    monkeypatch.setenv("GITHUB_TARGET_COMMITISH", "main")

    publisher = GitHubReleaseNotePublisher.from_env()

    assert publisher.repository == "env-owner/env-repo"
    assert publisher.token == "env-token"
    assert publisher.tag_name == "v2.0.0"
    assert publisher.release_name == "Env release"
    assert publisher.target_commitish == "main"


def test_live_publish_posts_release_request_and_returns_fields() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": 123, "html_url": "https://github.com/owner/repo/releases/tag/v1.2.3"})

    publisher = GitHubReleaseNotePublisher(owner="owner", repo="repo", token="gh-token", tag_name="v1.2.3", release_name="Release v1.2.3", target_commitish="abc123", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.release_id == "123"
    assert result.release_url == "https://github.com/owner/repo/releases/tag/v1.2.3"
    assert result.headers["Authorization"] == "Bearer [REDACTED]"
    assert requests[0].headers["Authorization"] == "Bearer gh-token"
    assert _json_from_request(requests[0]) == {
        "tag_name": "v1.2.3",
        "name": "Release v1.2.3",
        "body": result.payload["body"],
        "draft": True,
        "prerelease": False,
        "target_commitish": "abc123",
    }


def test_live_publish_requires_token_repository_and_tag_before_http() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("configuration validation should fail before HTTP")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(GitHubReleaseNotePublishError, match="GITHUB_REPOSITORY"):
        GitHubReleaseNotePublisher(None, tag_name="v1.0.0", client=client)
    with pytest.raises(GitHubReleaseNotePublishError, match="GITHUB_TOKEN"):
        GitHubReleaseNotePublisher("owner/repo", tag_name="v1.0.0", client=client).publish(_idea_payload(), dry_run=False)
    with pytest.raises(ValueError, match="GITHUB_RELEASE_TAG"):
        GitHubReleaseNotePublisher("owner/repo", token="gh-token", client=client).publish(_idea_payload(), dry_run=False)


def test_live_publish_error_redacts_token() -> None:
    publisher = GitHubReleaseNotePublisher("owner/repo", token="gh-token", tag_name="v1.0.0", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403, text="bad gh-token"))))

    with pytest.raises(GitHubReleaseNotePublishError) as exc:
        publisher.publish(_idea_payload(), dry_run=False)

    assert exc.value.status_code == 403
    assert "HTTP 403" in str(exc.value)
    assert "gh-token" not in str(exc.value)


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
