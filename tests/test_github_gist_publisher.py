"""Tests for GitHub Gist publishing."""

from __future__ import annotations

import httpx
import pytest

from max.publisher.github_gists import GitHubGistPublishError, GitHubGistPublisher


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-test001",
            "status": "evaluated",
            "domain": "devtools",
            "category": "cli_tool",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "MCP Test Framework",
            "summary": "Standardized testing for MCP servers",
            "target_users": "developers",
            "specific_user": "MCP server maintainer",
            "buyer": "platform team",
            "workflow_context": "pre-release CI",
        },
        "problem": {"statement": "No standard way to test MCP servers"},
        "solution": {"approach": "A CLI tool that validates MCP server implementations"},
        "execution": {
            "mvp_scope": ["Protocol fixtures", "CLI runner"],
            "validation_plan": "Run with three teams.",
        },
        "evidence": {
            "rationale": "Evidence supports the idea.",
            "insight_ids": ["ins-test001"],
            "signal_ids": ["sig-test001"],
        },
        "quality": {
            "quality_score": 8.0,
            "novelty_score": 7.5,
            "usefulness_score": 8.5,
            "rejection_tags": [],
        },
        "evaluation": {
            "overall_score": 78.0,
            "recommendation": "yes",
            "strengths": ["High demand"],
            "weaknesses": ["Niche audience"],
        },
    }


def test_build_gist_payload_maps_idea_summary_and_evidence_links() -> None:
    publisher = GitHubGistPublisher(public=True, filename="mcp-test-framework.md")

    payload = publisher.build_gist_payload(
        _tact_spec(),
        evidence_links=["https://example.com/evidence"],
    ).to_dict()

    assert payload["description"] == "Max idea: MCP Test Framework"
    assert payload["public"] is True
    assert set(payload["files"]) == {"mcp-test-framework.md"}
    content = payload["files"]["mcp-test-framework.md"]["content"]
    assert "# MCP Test Framework" in content
    assert "Idea ID: bu-test001" in content
    assert "https://example.com/evidence" in content
    assert '"kind": "tact.project_spec"' in content
    assert payload["metadata"]["idea_id"] == "bu-test001"
    assert payload["metadata"]["public"] is True


def test_dry_run_returns_exact_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubGistPublisher(token="secret", client=client)

    result = publisher.publish(_tact_spec(), dry_run=True)
    expected = publisher.build_gist_payload(_tact_spec()).to_dict()

    assert result.dry_run is True
    assert result.status_code is None
    assert result.gist_url is None
    assert result.payload == expected


def test_live_publish_posts_github_gist_payload_without_metadata() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "id": "abc123",
                "html_url": "https://gist.github.com/owner/abc123",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubGistPublisher(
        token="secret",
        api_url="https://api.github.test",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 201
    assert result.gist_url == "https://gist.github.com/owner/abc123"
    assert result.payload["metadata"]["github_gist_id"] == "abc123"
    assert requests[0].url == "https://api.github.test/gists"
    assert requests[0].headers["Authorization"] == "Bearer secret"
    posted = json_from_request(requests[0])
    assert posted["description"] == "Max idea: MCP Test Framework"
    assert posted["public"] is False
    assert "metadata" not in posted


def test_live_publish_requires_token() -> None:
    publisher = GitHubGistPublisher()

    with pytest.raises(GitHubGistPublishError, match="GITHUB_TOKEN"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_from_env_reads_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")

    publisher = GitHubGistPublisher.from_env()

    assert publisher.token == "env-token"


def json_from_request(request: httpx.Request) -> dict:
    import json

    return json.loads(request.read())
