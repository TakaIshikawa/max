"""Tests for GitLab merge request publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher import GitLabMergeRequestPublisher as ExportedGitLabMergeRequestPublisher
from max.publisher.gitlab_merge_requests import (
    GitLabMergeRequestPublishError,
    GitLabMergeRequestPublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "design_brief",
            "idea_id": "bu-mr001",
            "design_brief_id": "dbf-mr001",
            "status": "approved",
            "domain": "devtools",
            "category": "handoff",
        },
        "project": {
            "title": "GitLab Merge Request Publisher",
            "summary": "Open implementation-ready merge requests from generated specs.",
            "target_users": "product engineers",
        },
        "problem": {"statement": "Implementation handoffs stop before merge review."},
        "solution": {"approach": "Create a GitLab merge request with the spec context."},
        "execution": {
            "mvp_scope": ["Merge request payload builder", "GitLab API call"],
            "validation_plan": "Create one merge request in a sandbox project.",
        },
        "evidence": {
            "rationale": "Merge requests are the GitLab review handoff.",
            "insight_ids": ["ins-mr001"],
            "signal_ids": ["sig-mr001"],
        },
        "quality": {"quality_score": 8.5, "rejection_tags": []},
        "evaluation": {"overall_score": 87.0, "recommendation": "yes"},
    }


def test_dry_run_returns_endpoint_payload_and_no_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitLabMergeRequestPublisher(
        "group/subgroup/project",
        token="secret",
        source_branch="feature/max-mr",
        target_branch="main",
        title="MR handoff",
        description="Generated merge request description",
        labels=["ready-for-review"],
        assignee_ids=[12],
        remove_source_branch=True,
        squash=True,
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.project == "group/subgroup/project"
    assert result.endpoint == (
        "https://gitlab.com/api/v4/projects/group%2Fsubgroup%2Fproject/merge_requests"
    )
    assert result.merge_request_id is None
    assert result.merge_request_iid is None
    assert result.merge_request_url is None
    assert result.payload["title"] == "MR handoff"
    assert result.payload["source_branch"] == "feature/max-mr"
    assert result.payload["target_branch"] == "main"
    assert result.payload["description"] == "Generated merge request description"
    assert "ready-for-review" in result.payload["labels"]
    assert result.payload["assignee_ids"] == [12]
    assert result.payload["remove_source_branch"] is True
    assert result.payload["squash"] is True
    assert result.payload["metadata"]["publisher"] == "max.gitlab_merge_requests"
    assert result.payload["metadata"]["design_brief_id"] == "dbf-mr001"
    assert "token" not in json.dumps(result.payload).lower()


def test_default_payload_maps_spec_to_merge_request_description_and_labels() -> None:
    publisher = GitLabMergeRequestPublisher(
        "group/project",
        source_branch="feature/spec-handoff",
        target_branch="main",
        labels=["delivery"],
        assignee_ids=[7],
    )

    payload = publisher.build_merge_request_payload(_tact_spec()).to_dict()

    assert payload["title"] == "GitLab Merge Request Publisher"
    assert payload["project"] == "group/project"
    assert payload["source_branch"] == "feature/spec-handoff"
    assert payload["target_branch"] == "main"
    assert payload["assignee_ids"] == [7]
    assert payload["description"].startswith("## GitLab Merge Request Publisher")
    assert "Design brief ID: dbf-mr001" in payload["description"]
    assert '"kind": "tact.project_spec"' in payload["description"]
    assert payload["labels"] == [
        "max",
        "merge-request",
        "design-brief",
        "handoff",
        "devtools",
        "approved",
        "recommendation-yes",
        "delivery",
    ]


def test_live_publish_posts_expected_gitlab_merge_request_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "id": 1001,
                "iid": 42,
                "web_url": "https://gitlab.example.com/group/project/-/merge_requests/42",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitLabMergeRequestPublisher(
        project_path="group/project",
        token="glpat_secret",
        base_url="https://gitlab.example.com",
        source_branch="feature/max-mr",
        target_branch="main",
        labels=["delivery"],
        assignee_ids=[12],
        remove_source_branch=True,
        client=client,
    )

    result = publisher.publish(
        _tact_spec(),
        title="Custom MR title",
        description="Generated MR body",
        labels=["handoff"],
        assignee_ids=[13],
        squash=True,
        dry_run=False,
    )

    assert result.status_code == 201
    assert result.merge_request_id == 1001
    assert result.merge_request_iid == 42
    assert result.merge_request_url == (
        "https://gitlab.example.com/group/project/-/merge_requests/42"
    )
    assert requests[0].method == "POST"
    assert requests[0].url == (
        "https://gitlab.example.com/api/v4/projects/group%2Fproject/merge_requests"
    )
    assert requests[0].headers["Authorization"] == "Bearer glpat_secret"
    assert requests[0].headers["User-Agent"] == "max-gitlab-merge-requests-publisher/1"
    assert _json_from_request(requests[0]) == {
        "title": "Custom MR title",
        "source_branch": "feature/max-mr",
        "target_branch": "main",
        "description": "Generated MR body",
        "remove_source_branch": True,
        "labels": (
            "max,merge-request,design-brief,handoff,devtools,approved,"
            "recommendation-yes,delivery"
        ),
        "assignee_ids": [13],
        "squash": True,
    }
    assert result.payload["metadata"]["gitlab_merge_request_id"] == 1001
    assert result.payload["metadata"]["gitlab_merge_request_iid"] == 42


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"project": None}, "project ID/path"),
        ({"source_branch": None}, "source_branch"),
        ({"source_branch": "bad branch"}, "branch names"),
        ({"target_branch": None}, "target_branch"),
    ],
)
def test_missing_required_fields_raise_validation_errors(
    kwargs: dict[str, object],
    message: str,
) -> None:
    values = {
        "project": "group/project",
        "source_branch": "feature/max-mr",
        "target_branch": "main",
    }
    values.update(kwargs)

    if values["project"] is None:
        with pytest.raises(GitLabMergeRequestPublishError, match=message):
            GitLabMergeRequestPublisher(
                values["project"],
                source_branch=values["source_branch"],
                target_branch=values["target_branch"],
            )
        return

    publisher = GitLabMergeRequestPublisher(
        values["project"],
        source_branch=values["source_branch"],
        target_branch=values["target_branch"],
    )
    with pytest.raises(GitLabMergeRequestPublishError, match=message):
        publisher.publish(_tact_spec(), dry_run=True)


def test_live_publish_requires_token_before_http_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("missing token should fail before HTTP")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitLabMergeRequestPublisher(
        "group/project",
        source_branch="feature/max-mr",
        target_branch="main",
        client=client,
    )

    with pytest.raises(GitLabMergeRequestPublishError, match="GITLAB_TOKEN"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_live_publish_raises_error_with_status_code_on_non_2xx() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(400, json={"message": "source branch missing"})
        )
    )
    publisher = GitLabMergeRequestPublisher(
        "group/project",
        source_branch="feature/max-mr",
        target_branch="main",
        token="secret",
        client=client,
    )

    with pytest.raises(GitLabMergeRequestPublishError, match="HTTP 400") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 400


def test_from_env_reads_gitlab_merge_request_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITLAB_BASE_URL", "https://gitlab.env")
    monkeypatch.setenv("GITLAB_PROJECT_PATH", "env/group")
    monkeypatch.setenv("GITLAB_TOKEN", "env_token")
    monkeypatch.setenv("GITLAB_MERGE_REQUEST_SOURCE_BRANCH", "feature/env")
    monkeypatch.setenv("GITLAB_MERGE_REQUEST_TARGET_BRANCH", "develop")
    monkeypatch.setenv("GITLAB_MERGE_REQUEST_TITLE", "Env MR")

    publisher = GitLabMergeRequestPublisher.from_env()
    result = publisher.publish(_tact_spec(), dry_run=True)

    assert publisher.base_url == "https://gitlab.env"
    assert publisher.project == "env/group"
    assert publisher.token == "env_token"
    assert result.endpoint == (
        "https://gitlab.env/api/v4/projects/env%2Fgroup/merge_requests"
    )
    assert result.payload["source_branch"] == "feature/env"
    assert result.payload["target_branch"] == "develop"
    assert result.payload["title"] == "Env MR"


def test_exported_from_publisher_package() -> None:
    assert ExportedGitLabMergeRequestPublisher is GitLabMergeRequestPublisher


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
