"""Tests for GitHub Discussions publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher import GitHubDiscussionPublisher as ExportedGitHubDiscussionPublisher
from max.publisher.github_discussions import (
    GitHubDiscussionPublishError,
    GitHubDiscussionPublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-discuss001",
            "status": "evaluated",
            "domain": "devtools",
            "category": "community_feedback",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "Discussion Brief",
            "summary": "Collect community feedback before implementation",
            "target_users": "maintainers",
        },
        "problem": {"statement": "Generated ideas need lightweight feedback loops"},
        "solution": {"approach": "Publish the brief as a repository discussion"},
        "execution": {
            "mvp_scope": ["GraphQL publisher", "Discussion metadata"],
            "validation_plan": "Post one idea brief and collect comments.",
        },
        "evidence": {
            "rationale": "Communities already discuss roadmap candidates in GitHub.",
            "insight_ids": ["ins-discuss001"],
            "signal_ids": ["sig-discuss001"],
            "source_idea_ids": ["bu-source001"],
        },
        "evaluation": {
            "overall_score": 82.0,
            "recommendation": "yes",
        },
    }


def test_build_discussion_payload_maps_tact_spec_fields() -> None:
    publisher = GitHubDiscussionPublisher("acme", "ideas", "DIC_kwDOCat")

    payload = publisher.build_discussion_payload(_tact_spec()).to_dict()

    assert payload["owner"] == "acme"
    assert payload["repo"] == "ideas"
    assert payload["category_id"] == "DIC_kwDOCat"
    assert payload["title"] == "[Max] Discussion Brief"
    assert "Idea ID: bu-discuss001" in payload["body"]
    assert "Post one idea brief" in payload["body"]
    assert '"kind": "tact.project_spec"' in payload["body"]
    assert payload["metadata"]["publisher"] == "max.github_discussions"
    assert payload["metadata"]["repository"] == "acme/ideas"
    assert payload["metadata"]["idea_id"] == "bu-discuss001"

    request = publisher.build_create_discussion_request(payload, repository_id="R_repo123")
    item_input = request["variables"]["input"]
    assert "createDiscussion" in request["query"]
    assert item_input["repositoryId"] == "R_repo123"
    assert item_input["categoryId"] == "DIC_kwDOCat"
    assert item_input["title"] == "[Max] Discussion Brief"


def test_design_brief_payload_uses_markdown_and_source_metadata() -> None:
    publisher = GitHubDiscussionPublisher("acme", "ideas", "DIC_kwDOCat")
    brief = {
        "id": "dbf-discuss001",
        "title": "Design Brief Discussion",
        "domain": "devtools",
        "theme": "feedback",
        "lead_idea_id": "bu-lead",
        "source_idea_ids": ["bu-lead", "bu-supporting", "bu-lead"],
    }

    payload = publisher.build_design_brief_payload(
        brief,
        markdown="# Design Brief Discussion\n\nSource ideas: `bu-lead`, `bu-supporting`\n",
    ).to_dict()

    assert payload["title"] == "[Max] Design Brief Discussion"
    assert payload["body"].startswith("# Design Brief Discussion")
    assert payload["metadata"]["source_type"] == "design_brief"
    assert payload["metadata"]["design_brief_id"] == "dbf-discuss001"
    assert payload["metadata"]["source_idea_ids"] == ["bu-lead", "bu-supporting"]


def test_dry_run_returns_payload_without_token_or_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubDiscussionPublisher("acme", "ideas", "DIC_kwDOCat", client=client)
    expected = publisher.build_discussion_payload(_tact_spec()).to_dict()

    result = publisher.publish_payload(expected, dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.discussion_id is None
    assert result.discussion_url is None
    assert result.attempts == []
    assert result.payload == expected


def test_live_publish_resolves_repository_and_posts_create_discussion_mutation() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        posted = _json_from_request(request)
        if "query MaxDiscussionRepository" in posted["query"]:
            return httpx.Response(200, json={"data": {"repository": {"id": "R_repo123"}}})
        return httpx.Response(
            200,
            json={
                "data": {
                    "createDiscussion": {
                        "discussion": {
                            "id": "D_discussion123",
                            "url": "https://github.com/acme/ideas/discussions/42",
                            "title": "[Max] Discussion Brief",
                        }
                    }
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubDiscussionPublisher(
        "acme",
        "ideas",
        "DIC_kwDOCat",
        token="secret",
        graphql_endpoint="https://api.github.test/graphql",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert result.repository == "acme/ideas"
    assert result.discussion_id == "D_discussion123"
    assert result.discussion_url == "https://github.com/acme/ideas/discussions/42"
    assert result.attempts == [
        {
            "method": "POST",
            "url": "https://api.github.test/graphql",
            "status_code": 200,
        },
        {
            "method": "POST",
            "url": "https://api.github.test/graphql",
            "status_code": 200,
        },
    ]
    assert requests[0].headers["Authorization"] == "Bearer secret"
    lookup = _json_from_request(requests[0])
    assert lookup["variables"] == {"owner": "acme", "name": "ideas"}
    mutation = _json_from_request(requests[1])
    assert "createDiscussion" in mutation["query"]
    item_input = mutation["variables"]["input"]
    assert item_input["repositoryId"] == "R_repo123"
    assert item_input["categoryId"] == "DIC_kwDOCat"
    assert item_input["title"] == "[Max] Discussion Brief"
    assert "Idea ID: bu-discuss001" in item_input["body"]
    assert result.payload["metadata"]["github_discussion_id"] == "D_discussion123"
    assert result.payload["metadata"]["github_repository_id"] == "R_repo123"


def test_live_publish_requires_token() -> None:
    publisher = GitHubDiscussionPublisher("acme", "ideas", "DIC_kwDOCat")

    with pytest.raises(GitHubDiscussionPublishError, match="GITHUB_TOKEN"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_live_publish_raises_redacted_error_on_graphql_errors() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(200, json={"data": {"repository": {"id": "R_repo123"}}})
        return httpx.Response(
            200,
            json={"errors": [{"message": "Token ghp_secret cannot create discussion"}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubDiscussionPublisher("acme", "ideas", "DIC_kwDOCat", token="ghp_secret", client=client)

    with pytest.raises(GitHubDiscussionPublishError) as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    message = str(exc.value)
    assert "ghp_secret" not in message
    assert "[redacted] cannot create discussion" in message
    assert exc.value.status_code == 200
    assert len(exc.value.attempts) == 2


def test_live_publish_raises_redacted_error_on_http_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "Bad credentials ghp_secret"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubDiscussionPublisher(
        "acme",
        "ideas",
        "DIC_kwDOCat",
        token="ghp_secret",
        graphql_endpoint="https://user:password@api.github.test/graphql?token=ghp_secret",
        client=client,
    )

    with pytest.raises(GitHubDiscussionPublishError) as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    message = str(exc.value)
    assert "ghp_secret" not in message
    assert "password" not in json.dumps(exc.value.attempts)
    assert "Bad credentials [redacted]" in message
    assert exc.value.status_code == 403
    assert exc.value.attempts == [
        {
            "method": "POST",
            "url": "https://***@api.github.test/graphql?[redacted]",
            "status_code": 403,
        }
    ]


def test_from_env_reads_repository_values_and_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "env-owner/env-repo")
    monkeypatch.setenv("GITHUB_DISCUSSION_CATEGORY_ID", "DIC_env")
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")

    publisher = GitHubDiscussionPublisher.from_env()

    assert publisher.owner == "env-owner"
    assert publisher.repo == "env-repo"
    assert publisher.category_id == "DIC_env"
    assert publisher.token == "env-token"


def test_publisher_is_exported_from_package() -> None:
    assert ExportedGitHubDiscussionPublisher is GitHubDiscussionPublisher


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
