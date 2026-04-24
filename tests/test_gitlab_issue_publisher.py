"""Tests for GitLab issue publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.gitlab_issues import GitLabIssuePublishError, GitLabIssuePublisher


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-gitlab001",
            "status": "approved",
            "domain": "devtools",
            "category": "automation",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "GitLab Publish Idea",
            "summary": "Publish implementation-ready ideas to GitLab",
            "target_users": "developers",
        },
        "problem": {"statement": "Reviewed ideas are trapped in Max"},
        "solution": {"approach": "Create GitLab issues through REST"},
        "execution": {
            "mvp_scope": ["GitLab publisher", "REST endpoint"],
            "validation_plan": "Publish one approved idea into a test project.",
        },
        "evidence": {
            "rationale": "Teams triage in GitLab.",
            "insight_ids": ["ins-gitlab001"],
            "signal_ids": ["sig-gitlab001"],
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
        },
    }


def test_build_issue_payload_maps_tact_spec_fields() -> None:
    publisher = GitLabIssuePublisher(
        "group/project",
        labels=["delivery"],
        assignee_ids=[12],
        confidential=True,
    )

    payload = publisher.build_issue_payload(_tact_spec()).to_dict()

    assert payload["title"] == "[Max] GitLab Publish Idea"
    assert payload["project"] == "group/project"
    assert payload["assignee_ids"] == [12]
    assert payload["confidential"] is True
    assert "delivery" in payload["labels"]
    assert "Idea ID: bu-gitlab001" in payload["description"]
    assert "sig-gitlab001" in payload["description"]
    assert payload["metadata"]["idea_id"] == "bu-gitlab001"


def test_dry_run_returns_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitLabIssuePublisher("group/project", token="gitlab_pat", client=client)

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.issue_id is None
    assert result.issue_iid is None
    assert result.issue_url is None
    assert result.attempts == 0
    assert result.payload["metadata"]["idea_id"] == "bu-gitlab001"


def test_live_publish_posts_gitlab_issue() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "id": 10042,
                "iid": 42,
                "web_url": "https://gitlab.example.com/group/project/-/issues/42",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitLabIssuePublisher(
        "group/project",
        token="gitlab_pat",
        base_url="https://gitlab.example.com",
        labels=["delivery"],
        assignee_ids=[12],
        client=client,
    )

    result = publisher.publish(
        _tact_spec(),
        title="Custom GitLab title",
        labels=["handoff"],
        assignee_ids=[13],
        confidential=True,
        dry_run=False,
    )

    assert result.status_code == 201
    assert result.issue_id == 10042
    assert result.issue_iid == 42
    assert result.issue_url == "https://gitlab.example.com/group/project/-/issues/42"
    assert result.attempts == 1
    assert requests[0].url == "https://gitlab.example.com/api/v4/projects/group%2Fproject/issues"
    assert requests[0].headers["Authorization"] == "Bearer gitlab_pat"
    posted = _json_from_request(requests[0])
    assert posted["title"] == "[Max] Custom GitLab title"
    assert posted["labels"] == "max,tact-spec,idea,automation,devtools,approved,recommendation-yes,delivery,handoff"
    assert posted["assignee_ids"] == [13]
    assert posted["confidential"] is True
    assert result.payload["metadata"]["gitlab_issue_id"] == 10042
    assert result.payload["metadata"]["gitlab_issue_iid"] == 42
    assert result.payload["metadata"]["gitlab_attempts"] == 1


def test_live_publish_retries_transient_failures() -> None:
    statuses = [503, 429, 201]
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        status = statuses.pop(0)
        if status == 201:
            return httpx.Response(
                201,
                json={
                    "id": 10042,
                    "iid": 42,
                    "web_url": "https://gitlab.example.com/group/project/-/issues/42",
                },
            )
        return httpx.Response(status, json={"error": "try again"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitLabIssuePublisher(
        "group/project",
        token="gitlab_pat",
        base_url="https://gitlab.example.com",
        max_retries=2,
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.issue_iid == 42
    assert result.attempts == 3
    assert len(requests) == 3


def test_live_publish_redacts_secrets_in_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            text="bad token=gitlab_secret private_token=private_secret "
            "https://gitlab.example.com/api/v4/projects/1/issues?token=url_secret&safe=yes",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitLabIssuePublisher(
        "group/project",
        token="gitlab_pat",
        base_url="https://gitlab.example.com?token=site_secret",
        client=client,
    )

    with pytest.raises(GitLabIssuePublishError) as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    message = str(exc.value)
    assert "gitlab_secret" not in message
    assert "private_secret" not in message
    assert "url_secret" not in message
    assert "site_secret" not in message
    assert "token=%3Credacted%3E" in message


def test_from_env_reads_gitlab_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITLAB_BASE_URL", "https://gitlab.env")
    monkeypatch.setenv("GITLAB_PROJECT_PATH", "env/group")
    monkeypatch.setenv("GITLAB_TOKEN", "env_token")

    publisher = GitLabIssuePublisher.from_env()

    assert publisher.base_url == "https://gitlab.env"
    assert publisher.project == "env/group"
    assert publisher.token == "env_token"


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
