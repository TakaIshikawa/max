"""Tests for GitHub Projects v2 publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.github_projects import (
    GitHubProjectItemPublisher,
    GitHubProjectPublishError,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-project001",
            "status": "evaluated",
            "domain": "devtools",
            "category": "workflow",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "Projects Draft Idea",
            "summary": "Publish validated ideas to GitHub Projects",
            "target_users": "product engineers",
        },
        "problem": {"statement": "Reviewed ideas are not visible in planning boards"},
        "solution": {"approach": "Create GitHub Projects v2 draft items through GraphQL"},
        "execution": {
            "mvp_scope": ["GraphQL publisher", "Project item metadata"],
            "validation_plan": "Publish one reviewed idea into a project.",
        },
        "evidence": {
            "rationale": "Teams triage in GitHub Projects.",
            "insight_ids": ["ins-project001"],
            "signal_ids": ["sig-project001"],
            "source_idea_ids": ["bu-source001"],
        },
        "quality": {
            "quality_score": 8.0,
            "novelty_score": 7.0,
            "usefulness_score": 9.0,
            "rejection_tags": [],
        },
        "evaluation": {
            "overall_score": 84.0,
            "recommendation": "yes",
        },
    }


def test_build_project_payload_maps_tact_spec_fields() -> None:
    publisher = GitHubProjectItemPublisher("PVT_kwDOProject")

    payload = publisher.build_project_item_payload(_tact_spec()).to_dict()

    assert payload["project_id"] == "PVT_kwDOProject"
    assert payload["title"] == "[Max] Projects Draft Idea"
    assert "Idea ID: bu-project001" in payload["body"]
    assert "Publish one reviewed idea" in payload["body"]
    assert '"kind": "tact.project_spec"' in payload["body"]
    assert payload["metadata"]["publisher"] == "max.github_projects"
    assert payload["metadata"]["idea_id"] == "bu-project001"


def test_dry_run_returns_graphql_ready_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubProjectItemPublisher("PVT_kwDOProject", token="secret", client=client)

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.item_id is None
    assert result.attempts == []
    assert result.payload["metadata"]["idea_id"] == "bu-project001"


def test_live_publish_posts_add_project_v2_draft_issue_mutation() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": {
                    "addProjectV2DraftIssue": {
                        "projectItem": {
                            "id": "PVTI_item123",
                            "url": "https://github.com/orgs/acme/projects/7/views/1?pane=issue&itemId=PVTI_item123",
                            "content": {
                                "id": "DI_draft123",
                                "title": "[Max] Projects Draft Idea",
                                "body": "body",
                            },
                        }
                    }
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubProjectItemPublisher(
        "PVT_kwDOProject",
        token="secret",
        api_url="https://api.github.test/graphql",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert result.project_id == "PVT_kwDOProject"
    assert result.item_id == "PVTI_item123"
    assert result.item_url == "https://github.com/orgs/acme/projects/7/views/1?pane=issue&itemId=PVTI_item123"
    assert result.attempts == [
        {
            "method": "POST",
            "url": "https://api.github.test/graphql",
            "status_code": 200,
        }
    ]
    assert requests[0].url == "https://api.github.test/graphql"
    assert requests[0].headers["Authorization"] == "Bearer secret"
    posted = _json_from_request(requests[0])
    assert "addProjectV2DraftIssue" in posted["query"]
    item_input = posted["variables"]["input"]
    assert item_input["projectId"] == "PVT_kwDOProject"
    assert item_input["title"] == "[Max] Projects Draft Idea"
    assert "Idea ID: bu-project001" in item_input["body"]
    assert result.payload["metadata"]["github_project_item_id"] == "PVTI_item123"


def test_from_env_uses_explicit_values_before_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_PROJECT_ID", "PVT_env")
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    monkeypatch.setenv("GITHUB_GRAPHQL_URL", "https://env.example/graphql")

    publisher = GitHubProjectItemPublisher.from_env(
        project_id="PVT_explicit",
        token="explicit-token",
        api_url="https://explicit.example/graphql",
    )

    assert publisher.project_id == "PVT_explicit"
    assert publisher.token == "explicit-token"
    assert publisher.graphql_endpoint == "https://explicit.example/graphql"


def test_live_publish_raises_redacted_error_on_graphql_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"errors": [{"message": "Token ghp_secret denied access to project"}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubProjectItemPublisher("PVT_kwDOProject", token="ghp_secret", client=client)

    with pytest.raises(GitHubProjectPublishError) as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    message = str(exc.value)
    assert "ghp_secret" not in message
    assert "[redacted] denied access" in message
    assert exc.value.status_code == 200
    assert exc.value.attempts[0]["status_code"] == 200


def test_live_publish_raises_redacted_error_on_http_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "Bad credentials ghp_secret"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubProjectItemPublisher(
        "PVT_kwDOProject",
        token="ghp_secret",
        api_url="https://user:password@api.github.test/graphql?token=ghp_secret",
        client=client,
    )

    with pytest.raises(GitHubProjectPublishError) as exc:
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


def test_live_publish_requires_token() -> None:
    publisher = GitHubProjectItemPublisher("PVT_kwDOProject")

    with pytest.raises(GitHubProjectPublishError, match="GITHUB_TOKEN"):
        publisher.publish(_tact_spec(), dry_run=False)


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
