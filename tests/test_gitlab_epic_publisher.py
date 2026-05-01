"""Tests for GitLab epic publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher import GitLabEpicPublisher as ExportedGitLabEpicPublisher
from max.publisher.gitlab_epics import (
    GitLabEpicPublishError,
    GitLabEpicPublisher,
)


def _design_brief() -> dict:
    return {
        "kind": "design_brief",
        "source": {
            "type": "design_brief",
            "design_brief_id": "db-123",
            "status": "approved",
            "domain": "platform",
            "category": "roadmap",
        },
        "project": {
            "title": "Roadmap planning workspace",
            "summary": "Publish generated plans back to a roadmap surface.",
        },
    }


def test_build_epic_payload_maps_configuration_and_artifact_fields() -> None:
    publisher = GitLabEpicPublisher(
        "group/platform",
        labels=["max", "planning"],
        start_date="2026-05-01",
        due_date="2026-06-15",
        parent_epic_id="77",
    )

    payload = publisher.build_epic_payload(
        _design_brief(),
        title="Approved roadmap plan",
        labels=["planning", "gitlab"],
    ).to_dict()

    assert payload["provider"] == "gitlab"
    assert payload["group_id"] == "group/platform"
    assert payload["title"] == "Approved roadmap plan"
    assert payload["description"] == "Publish generated plans back to a roadmap surface."
    assert payload["labels"] == [
        "max",
        "planning",
        "gitlab",
        "approved",
        "platform",
        "roadmap",
    ]
    assert payload["start_date"] == "2026-05-01"
    assert payload["due_date"] == "2026-06-15"
    assert payload["parent_epic_id"] == 77
    assert payload["metadata"]["publisher"] == "max.gitlab_epics"
    assert payload["metadata"]["source_id"] == "db-123"


def test_dry_run_returns_normalized_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitLabEpicPublisher(
        "group/platform",
        title="Roadmap epic",
        description="Publish a roadmap plan.",
        private_token="gitlab_pat",
        client=client,
    )

    result = publisher.publish(dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.provider == "gitlab"
    assert result.target_url is None
    assert result.epic_id is None
    assert result.epic_iid is None
    assert result.payload["title"] == "Roadmap epic"


def test_successful_publish_posts_group_epic_and_returns_normalized_result() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "id": 9001,
                "iid": 42,
                "web_url": "https://gitlab.example.com/group/platform/-/epics/42",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitLabEpicPublisher(
        "group/platform",
        title="Roadmap epic",
        description="Publish a roadmap plan.",
        labels=["max", "roadmap"],
        start_date="2026-05-01",
        due_date="2026-06-15",
        parent_epic_id=77,
        private_token="gitlab_pat",
        base_url="https://gitlab.example.com",
        client=client,
    )

    result = publisher.publish(labels=["approved"], dry_run=False)

    assert result.status_code == 201
    assert result.provider == "gitlab"
    assert result.group_id == "group/platform"
    assert result.target_url == "https://gitlab.example.com/group/platform/-/epics/42"
    assert result.epic_id == 9001
    assert result.epic_iid == 42
    assert requests[0].url == (
        "https://gitlab.example.com/api/v4/groups/group%2Fplatform/epics"
    )
    assert requests[0].headers["PRIVATE-TOKEN"] == "gitlab_pat"
    assert requests[0].headers["User-Agent"] == "max-gitlab-epics-publisher/1"
    posted = _json_from_request(requests[0])
    assert posted == {
        "title": "Roadmap epic",
        "description": "Publish a roadmap plan.",
        "labels": "max,roadmap,approved",
        "start_date_is_fixed": True,
        "start_date_fixed": "2026-05-01",
        "due_date_is_fixed": True,
        "due_date_fixed": "2026-06-15",
        "parent_id": 77,
    }
    assert result.payload["request"] == posted
    assert result.payload["metadata"]["gitlab_epic_id"] == 9001
    assert result.payload["metadata"]["gitlab_epic_iid"] == 42


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"group_id": ""}, "group_id"),
        ({"title": " "}, "title"),
        ({"description": " "}, "description"),
        ({"start_date": "2026/05/01"}, "YYYY-MM-DD"),
        ({"parent_epic_id": "0"}, "parent_epic_id"),
    ],
)
def test_missing_required_fields_raise_before_http_request(
    kwargs: dict[str, object],
    message: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("validation failures should not make network calls")

    values = {
        "group_id": "group/platform",
        "title": "Roadmap epic",
        "description": "Publish a roadmap plan.",
        "private_token": "gitlab_pat",
        "client": httpx.Client(transport=httpx.MockTransport(handler)),
    }
    values.update(kwargs)

    if values["group_id"] == "" or "start_date" in kwargs or "parent_epic_id" in kwargs:
        with pytest.raises(GitLabEpicPublishError, match=message):
            GitLabEpicPublisher(**values)
        return

    publisher = GitLabEpicPublisher(**values)
    with pytest.raises(GitLabEpicPublishError, match=message):
        publisher.publish(dry_run=False)


def test_missing_token_raises_validation_error_for_live_publish() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("missing token should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitLabEpicPublisher(
        "group/platform",
        title="Roadmap epic",
        description="Publish a roadmap plan.",
        client=client,
    )

    with pytest.raises(GitLabEpicPublishError, match="GITLAB_TOKEN"):
        publisher.publish(dry_run=False)


def test_api_error_raises_consistent_publish_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "forbidden"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitLabEpicPublisher(
        "group/platform",
        title="Roadmap epic",
        description="Publish a roadmap plan.",
        private_token="gitlab_pat",
        base_url="https://gitlab.example.com",
        client=client,
    )

    with pytest.raises(GitLabEpicPublishError) as exc:
        publisher.publish(dry_run=False)

    assert exc.value.status_code == 403
    assert "HTTP 403" in str(exc.value)
    assert "forbidden" in str(exc.value)


def test_from_env_reads_gitlab_epic_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITLAB_BASE_URL", "https://gitlab.env")
    monkeypatch.setenv("GITLAB_GROUP_PATH", "env/group")
    monkeypatch.setenv("GITLAB_PRIVATE_TOKEN", "env_token")
    monkeypatch.setenv("GITLAB_EPIC_TITLE", "Env epic")
    monkeypatch.setenv("GITLAB_EPIC_DESCRIPTION", "Env description")
    monkeypatch.setenv("GITLAB_EPIC_LABELS", "one, two")
    monkeypatch.setenv("GITLAB_EPIC_START_DATE", "2026-05-01")
    monkeypatch.setenv("GITLAB_EPIC_DUE_DATE", "2026-06-15")
    monkeypatch.setenv("GITLAB_PARENT_EPIC_ID", "77")

    publisher = GitLabEpicPublisher.from_env()

    assert publisher.base_url == "https://gitlab.env"
    assert publisher.group_id == "env/group"
    assert publisher.private_token == "env_token"
    assert publisher.title == "Env epic"
    assert publisher.description == "Env description"
    assert publisher.labels == ["one", "two"]
    assert publisher.start_date == "2026-05-01"
    assert publisher.due_date == "2026-06-15"
    assert publisher.parent_epic_id == 77


def test_exported_from_publisher_package() -> None:
    assert ExportedGitLabEpicPublisher is GitLabEpicPublisher


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
