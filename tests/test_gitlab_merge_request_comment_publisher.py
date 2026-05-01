"""Tests for GitLab merge request comment publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher import (
    GitLabMergeRequestCommentPublisher as ExportedGitLabMergeRequestCommentPublisher,
)
from max.publisher.gitlab_merge_request_comments import (
    GitLabMergeRequestCommentPublishError,
    GitLabMergeRequestCommentPublisher,
)


def test_dry_run_returns_normalized_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitLabMergeRequestCommentPublisher(
        "group/project",
        merge_request_iid=42,
        body="Spec handoff",
        token="gitlab_pat",
        client=client,
    )

    result = publisher.publish(dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.provider == "gitlab"
    assert result.project == "group/project"
    assert result.merge_request_iid == 42
    assert result.note_id is None
    assert result.payload["provider"] == "gitlab"
    assert result.payload["project"] == "group/project"
    assert result.payload["merge_request_iid"] == 42
    assert result.payload["body"] == "Spec handoff"
    assert result.payload["metadata"]["publisher"] == "max.gitlab_merge_request_comments"


def test_successful_publish_posts_merge_request_note_and_returns_note_id() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "id": 98765,
                "web_url": "https://gitlab.example.com/group/project/-/merge_requests/42#note_98765",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitLabMergeRequestCommentPublisher(
        "group/project",
        merge_request_iid="42",
        body="Review packet",
        token="gitlab_pat",
        base_url="https://gitlab.example.com",
        client=client,
    )

    result = publisher.publish(dry_run=False)

    assert result.status_code == 201
    assert result.provider == "gitlab"
    assert result.project == "group/project"
    assert result.merge_request_iid == 42
    assert result.note_id == "98765"
    assert (
        result.note_url
        == "https://gitlab.example.com/group/project/-/merge_requests/42#note_98765"
    )
    assert requests[0].url == (
        "https://gitlab.example.com/api/v4/projects/group%2Fproject/"
        "merge_requests/42/notes"
    )
    assert requests[0].headers["PRIVATE-TOKEN"] == "gitlab_pat"
    assert requests[0].headers["User-Agent"] == (
        "max-gitlab-merge-request-comments-publisher/1"
    )
    posted = _json_from_request(requests[0])
    assert posted == {"body": "Review packet"}
    assert result.payload["note_id"] == "98765"
    assert result.payload["metadata"]["gitlab_merge_request_note_id"] == "98765"


def test_comment_endpoint_url_encodes_nested_project_paths() -> None:
    publisher = GitLabMergeRequestCommentPublisher(
        "platform/subgroup/project",
        merge_request_iid=7,
        body="Review packet",
    )

    assert publisher.comment_endpoint() == (
        "https://gitlab.com/api/v4/projects/platform%2Fsubgroup%2Fproject/"
        "merge_requests/7/notes"
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"project_id_or_path": ""}, "project ID/path"),
        ({"merge_request_iid": None}, "merge request iid"),
        ({"merge_request_iid": "0"}, "positive integer"),
        ({"body": " "}, "comment body"),
    ],
)
def test_missing_required_fields_raise_deterministic_validation_errors(
    kwargs: dict[str, object],
    message: str,
) -> None:
    values = {
        "project_id_or_path": "group/project",
        "merge_request_iid": 42,
        "body": "Review packet",
    }
    values.update(kwargs)

    if not values["project_id_or_path"] or values["merge_request_iid"] == "0":
        with pytest.raises(GitLabMergeRequestCommentPublishError, match=message):
            GitLabMergeRequestCommentPublisher(
                values["project_id_or_path"],
                merge_request_iid=values["merge_request_iid"],
                body=values["body"],
            )
        return

    publisher = GitLabMergeRequestCommentPublisher(
        values["project_id_or_path"],
        merge_request_iid=values["merge_request_iid"],
        body=values["body"],
    )
    with pytest.raises(GitLabMergeRequestCommentPublishError, match=message):
        publisher.publish(dry_run=True)


def test_missing_token_raises_validation_error_for_live_publish() -> None:
    publisher = GitLabMergeRequestCommentPublisher(
        "group/project",
        merge_request_iid=42,
        body="Review packet",
    )

    with pytest.raises(GitLabMergeRequestCommentPublishError, match="GITLAB_TOKEN"):
        publisher.publish(dry_run=False)


def test_from_env_reads_gitlab_merge_request_comment_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITLAB_BASE_URL", "https://gitlab.env")
    monkeypatch.setenv("GITLAB_PROJECT_PATH", "env/group")
    monkeypatch.setenv("GITLAB_MERGE_REQUEST_IID", "123")
    monkeypatch.setenv("GITLAB_MERGE_REQUEST_COMMENT_BODY", "Env body")
    monkeypatch.setenv("GITLAB_TOKEN", "env_token")

    publisher = GitLabMergeRequestCommentPublisher.from_env()

    assert publisher.base_url == "https://gitlab.env"
    assert publisher.project_id_or_path == "env/group"
    assert publisher.merge_request_iid == 123
    assert publisher.body == "Env body"
    assert publisher.token == "env_token"


def test_exported_from_publisher_package() -> None:
    assert ExportedGitLabMergeRequestCommentPublisher is GitLabMergeRequestCommentPublisher


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
