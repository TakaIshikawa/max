"""Tests for Bitbucket Cloud issue publishing."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from max.publisher import (
    BitbucketIssuePayload,
    BitbucketIssuePublishError,
    BitbucketIssuePublishResult,
    BitbucketIssuePublisher,
    BitbucketIssuesPublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-bitbucket001",
            "status": "approved",
            "domain": "devtools",
            "category": "automation",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "Bitbucket Publish Idea",
            "summary": "Publish implementation-ready ideas to Bitbucket",
            "target_users": "developers",
        },
        "problem": {"statement": "Reviewed ideas are trapped in Max"},
        "solution": {"approach": "Create Bitbucket issues through REST"},
        "execution": {
            "mvp_scope": ["Bitbucket publisher", "REST endpoint"],
            "validation_plan": "Publish one approved idea into a test repository.",
        },
        "evidence": {
            "rationale": "Teams triage in Bitbucket.",
            "insight_ids": ["ins-bitbucket001"],
            "signal_ids": ["sig-bitbucket001"],
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
    publisher = BitbucketIssuePublisher("max-team", "handoffs")

    payload = publisher.build_issue_payload(_tact_spec()).to_dict()

    assert payload["title"] == "[Max] Bitbucket Publish Idea"
    assert payload["workspace"] == "max-team"
    assert payload["repository"] == "handoffs"
    assert payload["kind"] == "proposal"
    assert payload["priority"] == "critical"
    assert "Idea ID: bu-bitbucket001" in payload["content"]
    assert "sig-bitbucket001" in payload["content"]
    assert payload["metadata"]["idea_id"] == "bu-bitbucket001"
    assert payload["metadata"]["bitbucket_issue_kind"] == "proposal"
    assert payload["metadata"]["bitbucket_priority"] == "critical"


def test_dry_run_returns_payload_without_credentials_or_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = BitbucketIssuePublisher("max-team", "handoffs", client=client)

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.issue_id is None
    assert result.issue_url is None
    assert result.attempts == 0
    assert result.payload["metadata"]["idea_id"] == "bu-bitbucket001"


def test_live_publish_posts_bitbucket_issue() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "id": 42,
                "links": {
                    "html": {
                        "href": "https://bitbucket.org/max-team/handoffs/issues/42/bitbucket-publish-idea"
                    }
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = BitbucketIssuePublisher(
        "max-team",
        "handoffs",
        username="agent@example.com",
        app_password="bb_app_password",
        client=client,
    )

    result = publisher.publish(
        _tact_spec(),
        title="Custom Bitbucket title",
        issue_kind="enhancement",
        priority="major",
        dry_run=False,
    )

    assert result.status_code == 201
    assert result.issue_id == 42
    assert result.issue_url == "https://bitbucket.org/max-team/handoffs/issues/42/bitbucket-publish-idea"
    assert result.attempts == 1
    assert requests[0].url == "https://api.bitbucket.org/2.0/repositories/max-team/handoffs/issues"
    expected_auth = base64.b64encode(b"agent@example.com:bb_app_password").decode("ascii")
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"
    posted = _json_from_request(requests[0])
    assert posted["title"] == "[Max] Custom Bitbucket title"
    assert posted["content"]["raw"].startswith("# Bitbucket Publish Idea")
    assert posted["kind"] == "enhancement"
    assert posted["priority"] == "major"
    assert result.payload["metadata"]["bitbucket_issue_id"] == 42
    assert result.payload["metadata"]["bitbucket_attempts"] == 1


def test_live_publish_requires_credentials() -> None:
    publisher = BitbucketIssuePublisher("max-team", "handoffs")

    with pytest.raises(BitbucketIssuePublishError, match="BITBUCKET_USERNAME"):
        publisher.publish(_tact_spec(), dry_run=False)


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
                    "id": 42,
                    "links": {"html": {"href": "https://bitbucket.org/max-team/handoffs/issues/42"}},
                },
            )
        return httpx.Response(status, json={"error": {"message": "try again"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = BitbucketIssuePublisher(
        "max-team",
        "handoffs",
        username="agent@example.com",
        app_password="bb_app_password",
        max_retries=2,
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.issue_id == 42
    assert result.attempts == 3
    assert len(requests) == 3


def test_live_publish_redacts_secrets_in_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            text="bad password=bb_secret app_password=bb_app_secret "
            "https://api.bitbucket.org/2.0/repositories/ws/repo/issues?token=url_secret&safe=yes",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = BitbucketIssuePublisher(
        "max-team",
        "handoffs",
        username="agent@example.com",
        app_password="bb_app_password",
        api_url="https://api.bitbucket.org/2.0?token=site_secret",
        client=client,
    )

    with pytest.raises(BitbucketIssuePublishError) as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    message = str(exc.value)
    assert "bb_secret" not in message
    assert "bb_app_secret" not in message
    assert "url_secret" not in message
    assert "site_secret" not in message
    assert "token=%3Credacted%3E" in message


def test_from_env_reads_bitbucket_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BITBUCKET_WORKSPACE", "env-team")
    monkeypatch.setenv("BITBUCKET_REPOSITORY", "env-repo")
    monkeypatch.setenv("BITBUCKET_USERNAME", "env@example.com")
    monkeypatch.setenv("BITBUCKET_APP_PASSWORD", "env_password")

    publisher = BitbucketIssuePublisher.from_env()

    assert publisher.workspace == "env-team"
    assert publisher.repository == "env-repo"
    assert publisher.username == "env@example.com"
    assert publisher.app_password == "env_password"


def test_public_imports_expose_bitbucket_types() -> None:
    assert BitbucketIssuesPublisher is BitbucketIssuePublisher
    assert BitbucketIssuePayload.__name__ == "BitbucketIssuePayload"
    assert BitbucketIssuePublishResult.__name__ == "BitbucketIssuePublishResult"
    assert issubclass(BitbucketIssuePublishError, RuntimeError)


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
