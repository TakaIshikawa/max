"""Tests for GitHub milestone publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.github_milestones import (
    GitHubMilestonePublishError,
    GitHubMilestonePublisher,
)


def _design_brief() -> dict:
    return {
        "id": "dbf-gh-ms",
        "title": "Milestone Design Brief",
        "domain": "devtools",
        "theme": "execution-window",
        "lead_idea_id": "bu-lead",
        "source_idea_ids": ["bu-lead", "bu-support"],
    }


def test_build_design_brief_payload_maps_context_metadata() -> None:
    publisher = GitHubMilestonePublisher("owner/repo", labels=["design", "Delivery"])

    payload = publisher.build_design_brief_payload(
        _design_brief(),
        description="# Milestone Design Brief\n\nPlan the delivery window.",
        due_on="2026-06-01T00:00:00Z",
        include_source_ids=True,
    ).to_dict()

    assert payload["title"] == "Milestone Design Brief"
    assert payload["description"].startswith("# Milestone Design Brief")
    assert payload["state"] == "open"
    assert payload["due_on"] == "2026-06-01T00:00:00Z"
    assert payload["labels"] == ["design", "Delivery"]
    assert payload["metadata"]["design_brief_id"] == "dbf-gh-ms"
    assert payload["metadata"]["repository"] == "owner/repo"
    assert payload["metadata"]["source_idea_ids"] == ["bu-lead", "bu-support"]
    assert payload["metadata"]["include_source_ids"] is True


def test_dry_run_returns_payload_without_network_or_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubMilestonePublisher("owner/repo", client=client)

    result = publisher.publish_design_brief(
        _design_brief(),
        description="Delivery plan",
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.status_code is None
    assert result.milestone_number is None
    assert result.milestone_url is None
    assert result.payload["metadata"]["design_brief_id"] == "dbf-gh-ms"


def test_live_publish_posts_github_milestone_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "number": 7,
                "html_url": "https://github.com/owner/repo/milestone/7",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubMilestonePublisher("owner/repo", token="secret", client=client)

    result = publisher.publish_design_brief(
        _design_brief(),
        description="Delivery plan",
        state="closed",
        due_on="2026-06-01T00:00:00Z",
        dry_run=False,
    )

    assert result.status_code == 201
    assert result.milestone_number == 7
    assert result.milestone_url == "https://github.com/owner/repo/milestone/7"
    assert requests[0].url == "https://api.github.com/repos/owner/repo/milestones"
    assert requests[0].headers["Authorization"] == "Bearer secret"
    posted = _json_from_request(requests[0])
    assert posted == {
        "title": "Milestone Design Brief",
        "description": "Delivery plan",
        "state": "closed",
        "due_on": "2026-06-01T00:00:00Z",
    }
    assert result.payload["metadata"]["github_milestone_number"] == 7


def test_live_publish_retries_transient_failures() -> None:
    statuses = [503, 429, 201]
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        status = statuses.pop(0)
        if status == 201:
            return httpx.Response(
                201,
                json={"number": 8, "html_url": "https://github.com/owner/repo/milestone/8"},
            )
        return httpx.Response(status, json={"message": "try again"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubMilestonePublisher(
        "owner/repo",
        token="secret",
        max_retries=2,
        client=client,
    )

    result = publisher.publish_design_brief(
        _design_brief(),
        description="Delivery plan",
        dry_run=False,
    )

    assert result.milestone_number == 8
    assert len(requests) == 3


def test_live_publish_requires_token() -> None:
    publisher = GitHubMilestonePublisher("owner/repo")

    with pytest.raises(GitHubMilestonePublishError, match="GITHUB_TOKEN"):
        publisher.publish_design_brief(_design_brief(), description="Delivery plan", dry_run=False)


def test_live_publish_redacts_secrets_in_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            text="bad token=body_secret password=body_password "
            "https://api.github.test/repos/owner/repo/milestones?token=url_secret&safe=yes",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubMilestonePublisher(
        "owner/repo",
        token="ghp_secret",
        api_url="https://api.github.test?token=site_secret",
        client=client,
    )

    with pytest.raises(GitHubMilestonePublishError) as exc:
        publisher.publish_design_brief(_design_brief(), description="Delivery plan", dry_run=False)

    message = str(exc.value)
    assert "body_secret" not in message
    assert "body_password" not in message
    assert "url_secret" not in message
    assert "site_secret" not in message
    assert "token=%3Credacted%3E" in message


def test_from_env_reads_github_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "env-owner/env-repo")
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")

    publisher = GitHubMilestonePublisher.from_env()

    assert publisher.repository == "env-owner/env-repo"
    assert publisher.token == "env-token"


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
