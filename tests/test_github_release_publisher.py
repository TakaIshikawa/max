"""Tests for GitHub release publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher import GitHubReleasePublisher as ExportedGitHubReleasePublisher
from max.publisher.github_releases import (
    GitHubReleasePublishError,
    GitHubReleasePublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "design_brief",
            "idea_id": "bu-release001",
            "design_brief_id": "dbf-release001",
            "status": "approved",
            "domain": "devtools",
            "category": "release_handoff",
        },
        "project": {
            "title": "GitHub Release Publisher",
            "summary": "Create versioned handoff artifacts for build agents.",
            "target_users": "product engineers",
            "specific_user": "build agent owner",
            "buyer": "platform team",
            "workflow_context": "release handoff",
        },
        "problem": {"statement": "Accepted briefs lack a versioned handoff artifact."},
        "solution": {"approach": "Publish a draft GitHub Release."},
        "execution": {
            "mvp_scope": ["Release payload builder", "Draft release API call"],
            "validation_plan": "Create one draft release in a sandbox repository.",
        },
        "evidence": {
            "rationale": "Versioned artifacts keep build handoffs traceable.",
            "insight_ids": ["ins-release001"],
            "signal_ids": ["sig-release001"],
        },
        "quality": {"quality_score": 8.5, "rejection_tags": []},
        "evaluation": {"overall_score": 88.0, "recommendation": "yes"},
    }


def _design_brief() -> dict:
    return {
        "schema_version": "max.blueprint.source_brief.v1",
        "design_brief": {
            "id": "dbf-release",
            "title": "Release Handoff",
            "domain": "devtools",
            "theme": "release-publishing",
            "lead_idea_id": "bu-lead",
            "source_idea_ids": ["bu-lead", "bu-supporting", "bu-lead"],
            "readiness_score": 92.0,
            "design_status": "ready",
            "merged_product_concept": "Publish generated briefs as draft releases.",
            "validation_plan": "Create a draft release.",
        },
    }


def test_dry_run_returns_endpoint_payload_and_no_token_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubReleasePublisher(
        "owner/repo",
        token="secret",
        tag_name="v1.2.3",
        target_commitish="main",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.owner == "owner"
    assert result.repo == "repo"
    assert result.repository == "owner/repo"
    assert result.endpoint == "https://api.github.com/repos/owner/repo/releases"
    assert result.release_id is None
    assert result.release_url is None
    assert result.upload_url is None
    assert result.payload["tag_name"] == "v1.2.3"
    assert result.payload["name"] == "GitHub Release Publisher"
    assert result.payload["draft"] is True
    assert result.payload["prerelease"] is False
    assert result.payload["target_commitish"] == "main"
    assert result.payload["body"].startswith("## GitHub Release Publisher")
    assert "Design brief ID: dbf-release001" in result.payload["body"]
    assert '"kind": "tact.project_spec"' in result.payload["body"]
    assert result.payload["metadata"]["publisher"] == "max.github_releases"
    assert "token" not in json.dumps(result.payload).lower()


def test_build_design_brief_payload_maps_markdown_and_source_metadata() -> None:
    publisher = GitHubReleasePublisher("owner/repo", tag_name="release/dbf-release")

    payload = publisher.build_design_brief_payload(
        _design_brief(),
        markdown="# Release Handoff",
    ).to_dict()

    assert payload["name"] == "Release Handoff"
    assert payload["body"].startswith("## Release Handoff")
    assert "Publish generated briefs as draft releases." in payload["body"]
    assert "# Release Handoff" in payload["body"]
    assert payload["metadata"]["source_type"] == "design_brief"
    assert payload["metadata"]["design_brief_id"] == "dbf-release"
    assert payload["metadata"]["source_idea_ids"] == ["bu-lead", "bu-supporting"]


def test_live_publish_posts_expected_release_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "id": 12345,
                "html_url": "https://github.com/owner/repo/releases/tag/v1.2.3",
                "upload_url": "https://uploads.github.com/repos/owner/repo/releases/12345/assets{?name,label}",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubReleasePublisher(
        owner="owner",
        repo="repo",
        token="secret",
        tag_name="v1.2.3",
        release_name="Release v1.2.3",
        body="Generated release notes",
        target_commitish="abc123",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 201
    assert result.release_id == "12345"
    assert result.release_url == "https://github.com/owner/repo/releases/tag/v1.2.3"
    assert requests[0].url == "https://api.github.com/repos/owner/repo/releases"
    assert requests[0].headers["Authorization"] == "Bearer secret"
    assert requests[0].headers["User-Agent"] == "max-github-releases-publisher/1"
    assert _json_from_request(requests[0]) == {
        "tag_name": "v1.2.3",
        "name": "Release v1.2.3",
        "body": "Generated release notes",
        "draft": True,
        "prerelease": False,
        "target_commitish": "abc123",
    }
    assert result.payload["metadata"]["github_release_id"] == "12345"


def test_from_env_reads_github_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "env-owner/env-repo")
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    monkeypatch.setenv("GITHUB_RELEASE_TAG", "v2.0.0")
    monkeypatch.setenv("GITHUB_RELEASE_NAME", "Env release")
    monkeypatch.setenv("GITHUB_TARGET_COMMITISH", "main")

    publisher = GitHubReleasePublisher.from_env()
    result = publisher.publish(_tact_spec(), dry_run=True)

    assert publisher.repository == "env-owner/env-repo"
    assert publisher.token == "env-token"
    assert result.payload["tag_name"] == "v2.0.0"
    assert result.payload["name"] == "Env release"
    assert result.payload["target_commitish"] == "main"


def test_from_env_accepts_explicit_owner_repo_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    publisher = GitHubReleasePublisher.from_env(
        owner="explicit-owner",
        repo="explicit-repo",
        tag_name="v1.0.0",
    )

    assert publisher.repository == "explicit-owner/explicit-repo"


def test_missing_repository_configuration_fails_before_http_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("configuration validation should fail before HTTP")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(GitHubReleasePublishError, match="repository is required"):
        GitHubReleasePublisher(None, tag_name="v1.0.0", client=client)


def test_invalid_repository_format_raises_clear_error() -> None:
    with pytest.raises(GitHubReleasePublishError, match="owner/repo format"):
        GitHubReleasePublisher("owner/repo/extra", tag_name="v1.0.0")


def test_invalid_tag_name_raises_clear_error() -> None:
    publisher = GitHubReleasePublisher("owner/repo")

    with pytest.raises(GitHubReleasePublishError, match="tag name"):
        publisher.publish(_tact_spec(), dry_run=True, tag_name="bad tag")


def test_live_publish_requires_token_before_http_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("missing token should fail before HTTP")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubReleasePublisher("owner/repo", tag_name="v1.0.0", client=client)

    with pytest.raises(GitHubReleasePublishError, match="GITHUB_TOKEN"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_live_publish_raises_duplicate_release_error() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                422,
                json={
                    "message": "Validation Failed",
                    "errors": [
                        {
                            "resource": "Release",
                            "field": "tag_name",
                            "code": "already_exists",
                        }
                    ],
                },
            )
        )
    )
    publisher = GitHubReleasePublisher(
        "owner/repo",
        tag_name="v1.0.0",
        token="secret",
        client=client,
    )

    with pytest.raises(GitHubReleasePublishError, match="already exists") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 422


def test_live_publish_raises_error_with_status_code_on_non_2xx() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(500, json={"message": "server error"})
        )
    )
    publisher = GitHubReleasePublisher(
        "owner/repo",
        tag_name="v1.0.0",
        token="secret",
        client=client,
    )

    with pytest.raises(GitHubReleasePublishError, match="HTTP 500") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 500


def test_exported_from_publisher_package() -> None:
    assert ExportedGitHubReleasePublisher is GitHubReleasePublisher


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
