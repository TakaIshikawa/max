"""Tests for GitLab snippet publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher import (
    GitLabSnippetPayload,
    GitLabSnippetPublishError,
    GitLabSnippetPublishResult,
    GitLabSnippetPublisher,
    GitLabSnippetsPublisher,
)


def _artifact() -> dict:
    return {
        "schema_version": "max.design_brief.artifact.v1",
        "kind": "max.design_brief.spec_bundle",
        "source": {
            "system": "max",
            "type": "design_brief",
            "design_brief_id": "dbf-gl-snippet",
            "idea_id": "bu-gl-snippet",
        },
        "project": {
            "title": "GitLab Snippet Handoff",
            "summary": "Publish generated specs as GitLab snippets.",
        },
        "problem": {"statement": "Generated handoff artifacts need a lightweight target."},
        "solution": {"approach": "Create deterministic GitLab snippet payloads."},
        "execution": {
            "mvp_scope": ["Payload builder", "GitLab snippets API publisher"],
            "validation_plan": "Dry run and publish to a test project.",
        },
        "evidence": {
            "rationale": "GitLab snippets are already reviewable by the team.",
            "insight_ids": ["ins-gl-snippet"],
            "signal_ids": ["sig-gl-snippet"],
        },
        "evaluation": {"recommendation": "yes", "overall_score": 86.0},
    }


def test_build_snippet_payload_maps_dict_artifact_content_metadata_and_source() -> None:
    publisher = GitLabSnippetPublisher(
        "group/project",
        visibility="internal",
        file_name="handoff.md",
    )

    payload = publisher.build_snippet_payload(_artifact()).to_dict()

    assert payload["title"] == "Max GitLab Snippet: GitLab Snippet Handoff"
    assert payload["description"] == "Publish generated specs as GitLab snippets."
    assert payload["project"] == "group/project"
    assert payload["visibility"] == "internal"
    assert payload["file_name"] == "handoff.md"
    assert "# GitLab Snippet Handoff" in payload["content"]
    assert "- Design brief ID: dbf-gl-snippet" in payload["content"]
    assert '"kind": "max.design_brief.spec_bundle"' in payload["content"]
    assert payload["metadata"] == {
        "publisher": "max.gitlab_snippets",
        "source_system": "max",
        "source_type": "design_brief",
        "idea_id": "bu-gl-snippet",
        "design_brief_id": "dbf-gl-snippet",
        "schema_version": "max.design_brief.artifact.v1",
        "kind": "max.design_brief.spec_bundle",
        "project": "group/project",
        "visibility": "internal",
        "file_name": "handoff.md",
    }
    assert payload["source_artifact"]["payload"] == _artifact()


def test_build_snippet_payload_supports_text_artifacts() -> None:
    publisher = GitLabSnippetPublisher("123", file_name="brief.md")

    payload = publisher.build_text_snippet_payload(
        "# Design Brief\n\nShip the thing.\n",
        title="Plain Brief",
        visibility="public",
    ).to_dict()

    assert payload["title"] == "Max GitLab Snippet: Plain Brief"
    assert payload["content"] == "# Design Brief\n\nShip the thing.\n"
    assert payload["visibility"] == "public"
    assert payload["metadata"]["source_type"] == "text_artifact"
    assert payload["metadata"]["kind"] == "text/markdown"
    assert payload["source_artifact"]["content"] == "# Design Brief\n\nShip the thing.\n"


def test_dry_run_returns_exact_payload_without_credentials_or_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitLabSnippetPublisher("group/project", client=client)

    result = publisher.publish(_artifact(), dry_run=True)
    expected = publisher.build_snippet_payload(_artifact()).to_dict()

    assert result.dry_run is True
    assert result.status_code is None
    assert result.snippet_id is None
    assert result.snippet_url is None
    assert result.payload == expected


def test_from_env_reads_gitlab_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITLAB_TOKEN", "env-token")
    monkeypatch.setenv("GITLAB_BASE_URL", "https://gitlab.example.com/")
    monkeypatch.setenv("GITLAB_PROJECT_ID", "env-group/env-project")
    monkeypatch.setenv("GITLAB_SNIPPET_VISIBILITY", "public")
    monkeypatch.setenv("GITLAB_SNIPPET_FILE_NAME", "env-handoff.md")
    monkeypatch.setenv("GITLAB_SNIPPET_TITLE", "Env Handoff")
    monkeypatch.setenv("GITLAB_SNIPPET_DRY_RUN", "false")

    publisher = GitLabSnippetPublisher.from_env()

    assert publisher.token == "env-token"
    assert publisher.base_url == "https://gitlab.example.com"
    assert publisher.project == "env-group/env-project"
    assert publisher.visibility == "public"
    assert publisher.file_name == "env-handoff.md"
    assert publisher.title == "Env Handoff"
    assert publisher.dry_run is False


def test_from_env_requires_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITLAB_PROJECT_ID", raising=False)
    monkeypatch.delenv("GITLAB_PROJECT_PATH", raising=False)
    monkeypatch.delenv("GITLAB_PROJECT", raising=False)

    with pytest.raises(GitLabSnippetPublishError, match="GitLab project ID/path"):
        GitLabSnippetPublisher.from_env()


def test_live_publish_posts_expected_gitlab_snippet_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        posted = json.loads(request.read())
        assert posted["title"] == "Max GitLab Snippet: Custom Handoff"
        assert posted["file_name"] == "custom.md"
        assert posted["visibility"] == "public"
        assert "# GitLab Snippet Handoff" in posted["content"]
        assert "metadata" not in posted
        assert "source_artifact" not in posted
        return httpx.Response(
            201,
            json={
                "id": 42,
                "web_url": "https://gitlab.example.com/group/project/-/snippets/42",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitLabSnippetPublisher(
        "group/project",
        token="secret-token",
        base_url="https://gitlab.example.com",
        client=client,
    )

    result = publisher.publish(
        _artifact(),
        title="Custom Handoff",
        visibility="public",
        file_name="custom.md",
        dry_run=False,
    )

    assert result.status_code == 201
    assert result.snippet_id == 42
    assert result.snippet_url == "https://gitlab.example.com/group/project/-/snippets/42"
    assert requests[0].url == "https://gitlab.example.com/api/v4/projects/group%2Fproject/snippets"
    assert requests[0].headers["Authorization"] == "Bearer secret-token"
    assert result.payload["metadata"]["gitlab_snippet_id"] == 42
    assert result.payload["metadata"]["gitlab_snippet_url"] == result.snippet_url


def test_live_publish_requires_token() -> None:
    publisher = GitLabSnippetPublisher("group/project")

    with pytest.raises(GitLabSnippetPublishError, match="GITLAB_TOKEN"):
        publisher.publish(_artifact(), dry_run=False)


def test_live_publish_surfaces_http_error_with_status_code_and_redacts_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"message": "private_token=supersecret cannot create snippet"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitLabSnippetPublisher("group/project", token="secret-token", client=client)

    with pytest.raises(GitLabSnippetPublishError) as exc:
        publisher.publish(_artifact(), dry_run=False)

    assert exc.value.status_code == 403
    assert "HTTP 403" in str(exc.value)
    assert "private_token=<redacted>" in str(exc.value)
    assert "supersecret" not in str(exc.value)


def test_live_publish_requires_response_id_and_web_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"id": 42})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitLabSnippetPublisher("group/project", token="secret-token", client=client)

    with pytest.raises(GitLabSnippetPublishError, match="id and web_url") as exc:
        publisher.publish(_artifact(), dry_run=False)

    assert exc.value.status_code == 201


def test_public_imports_expose_gitlab_snippet_types() -> None:
    assert GitLabSnippetsPublisher is GitLabSnippetPublisher
    assert GitLabSnippetPayload.__name__ == "GitLabSnippetPayload"
    assert GitLabSnippetPublishResult.__name__ == "GitLabSnippetPublishResult"
    assert issubclass(GitLabSnippetPublishError, RuntimeError)
