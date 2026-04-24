"""Tests for Linear issue publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.linear_issues import LinearIssuePublishError, LinearIssuePublisher


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-linear001",
            "status": "evaluated",
            "domain": "devtools",
            "category": "automation",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "Linear Publish Idea",
            "summary": "Publish implementation-ready ideas to Linear",
            "target_users": "developers",
        },
        "problem": {"statement": "Reviewed ideas are trapped in Max"},
        "solution": {"approach": "Create Linear issues through GraphQL"},
        "execution": {
            "mvp_scope": ["GraphQL publisher", "REST endpoint"],
            "validation_plan": "Publish one reviewed idea into a test team.",
        },
        "evidence": {
            "rationale": "Teams triage in Linear.",
            "insight_ids": ["ins-linear001"],
            "signal_ids": ["sig-linear001"],
            "source_idea_ids": ["bu-source001"],
        },
        "quality": {
            "quality_score": 8.0,
            "novelty_score": 7.0,
            "usefulness_score": 9.0,
            "rejection_tags": [],
        },
        "evaluation": {
            "overall_score": 82.0,
            "recommendation": "yes",
            "dimensions": {
                "pain_severity": {
                    "value": 8.0,
                    "confidence": 0.8,
                    "reasoning": "Manual handoff is slow.",
                },
            },
        },
    }


def test_build_issue_payload_maps_tact_spec_fields() -> None:
    publisher = LinearIssuePublisher(
        "team-123",
        project_id="project-123",
        labels=["label-1"],
        priority=2,
    )

    payload = publisher.build_issue_payload(_tact_spec()).to_dict()

    assert payload["title"] == "[Max] Linear Publish Idea"
    assert payload["team_id"] == "team-123"
    assert payload["project_id"] == "project-123"
    assert payload["label_ids"] == ["label-1"]
    assert payload["priority"] == 2
    assert "Idea ID: bu-linear001" in payload["description"]
    assert "## Evidence Chain" in payload["description"]
    assert "Publish one reviewed idea" in payload["description"]
    assert payload["metadata"]["idea_id"] == "bu-linear001"


def test_dry_run_returns_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = LinearIssuePublisher("team-123", api_key="lin_api", client=client)

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.issue_url is None
    assert result.payload["metadata"]["idea_id"] == "bu-linear001"


def test_live_publish_posts_linear_graphql_issue_create() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": {
                    "issueCreate": {
                        "success": True,
                        "issue": {
                            "id": "issue-123",
                            "identifier": "MAX-42",
                            "url": "https://linear.app/max/issue/MAX-42/linear-publish-idea",
                        },
                    }
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = LinearIssuePublisher(
        "team-123",
        api_key="lin_api",
        project_id="project-123",
        labels=["label-1"],
        priority=1,
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert result.issue_url == "https://linear.app/max/issue/MAX-42/linear-publish-idea"
    assert requests[0].url == "https://api.linear.app/graphql"
    assert requests[0].headers["Authorization"] == "lin_api"
    posted = _json_from_request(requests[0])
    assert "issueCreate" in posted["query"]
    issue_input = posted["variables"]["input"]
    assert issue_input["teamId"] == "team-123"
    assert issue_input["projectId"] == "project-123"
    assert issue_input["labelIds"] == ["label-1"]
    assert issue_input["priority"] == 1
    assert issue_input["title"] == "[Max] Linear Publish Idea"
    assert result.payload["metadata"]["linear_issue_identifier"] == "MAX-42"


def test_live_publish_raises_on_graphql_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "Team not found"}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = LinearIssuePublisher("team-404", api_key="lin_api", client=client)

    with pytest.raises(LinearIssuePublishError, match="Team not found") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 200


def test_live_publish_raises_on_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network unavailable", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = LinearIssuePublisher("team-123", api_key="lin_api", client=client)

    with pytest.raises(LinearIssuePublishError, match="network unavailable"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_from_env_reads_team_and_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINEAR_TEAM_ID", "team-env")
    monkeypatch.setenv("LINEAR_API_KEY", "lin_env")

    publisher = LinearIssuePublisher.from_env()

    assert publisher.team_id == "team-env"
    assert publisher.api_key == "lin_env"


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
