"""Tests for GitHub Actions workflow_dispatch publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher import (
    GitHubWorkflowDispatchPublisher as ExportedGitHubWorkflowDispatchPublisher,
)
from max.publisher.github_workflow_dispatch import (
    GitHubWorkflowDispatchPublishError,
    GitHubWorkflowDispatchPublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-dispatch001",
            "status": "approved",
            "domain": "devtools",
            "category": "automation",
        },
        "project": {
            "title": "Workflow Dispatch Publisher",
            "summary": "Kick off downstream automation from generated specs.",
        },
    }


def _design_brief() -> dict:
    return {
        "schema_version": "max.blueprint.source_brief.v1",
        "design_brief": {
            "id": "dbf-dispatch001",
            "title": "Dispatch Brief",
            "lead_idea_id": "bu-lead001",
            "domain": "devtools",
        },
    }


def test_dry_run_returns_exact_dispatch_request_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubWorkflowDispatchPublisher(
        "owner/repo",
        workflow_id="publish-spec.yml",
        token="secret",
        ref="release",
        inputs={"environment": "staging"},
        client=client,
    )

    result = publisher.publish(
        _tact_spec(),
        dry_run=True,
        inputs={"artifact_url": "https://example.test/spec.json"},
    )

    assert result.dry_run is True
    assert result.status_code is None
    assert result.endpoint == (
        "https://api.github.com/repos/owner/repo/actions/workflows/"
        "publish-spec.yml/dispatches"
    )
    assert result.payload["ref"] == "release"
    assert result.payload["inputs"] == {
        "environment": "staging",
        "artifact_kind": "tact.project_spec",
        "schema_version": "tact-spec-preview/v1",
        "idea_id": "bu-dispatch001",
        "source_type": "idea",
        "title": "Workflow Dispatch Publisher",
        "artifact_url": "https://example.test/spec.json",
    }
    assert "token" not in json.dumps(result.payload).lower()


def test_live_publish_posts_expected_github_actions_endpoint_and_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubWorkflowDispatchPublisher(
        owner="owner",
        repo="repo",
        workflow_id="downstream.yml",
        token="ghp_secret",
        client=client,
    )

    result = publisher.publish(
        _tact_spec(),
        dry_run=False,
        ref="main",
        inputs={"artifact_path": "specs/bu-dispatch001.json"},
    )

    assert result.status_code == 204
    assert result.dry_run is False
    assert result.payload["metadata"]["github_workflow_dispatch_status_code"] == 204
    assert requests[0].method == "POST"
    assert requests[0].url == (
        "https://api.github.com/repos/owner/repo/actions/workflows/"
        "downstream.yml/dispatches"
    )
    assert requests[0].headers["Authorization"] == "Bearer ghp_secret"
    assert requests[0].headers["User-Agent"] == "max-github-workflow-dispatch-publisher/1"
    assert _json_from_request(requests[0]) == {
        "ref": "main",
        "inputs": {
            "artifact_kind": "tact.project_spec",
            "schema_version": "tact-spec-preview/v1",
            "idea_id": "bu-dispatch001",
            "source_type": "idea",
            "title": "Workflow Dispatch Publisher",
            "artifact_path": "specs/bu-dispatch001.json",
        },
    }


def test_missing_token_raises_publisher_error_unless_dry_run() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("missing token should fail before HTTP")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitHubWorkflowDispatchPublisher(
        "owner/repo",
        workflow_id="downstream.yml",
        client=client,
    )

    dry_run = publisher.publish(_tact_spec(), dry_run=True)
    assert dry_run.dry_run is True

    with pytest.raises(GitHubWorkflowDispatchPublishError, match="GITHUB_TOKEN"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_tokens_are_redacted_from_results_and_error_messages() -> None:
    token = "ghp_should_not_leak"
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                500,
                json={
                    "message": "bad token ghp_should_not_leak",
                    "hint": "secret input should not echo",
                },
            )
        )
    )
    publisher = GitHubWorkflowDispatchPublisher(
        "owner/repo",
        workflow_id="downstream.yml",
        token=token,
        client=client,
    )

    dry_run = publisher.publish(
        _tact_spec(),
        dry_run=True,
        inputs={"github_token": token, "api_secret": "secret input should not echo"},
    )

    serialized = json.dumps(dry_run.payload)
    assert token not in serialized
    assert "secret input should not echo" not in serialized
    assert dry_run.payload["inputs"]["github_token"] == "[redacted]"
    assert dry_run.payload["inputs"]["api_secret"] == "[redacted]"

    with pytest.raises(GitHubWorkflowDispatchPublishError) as exc:
        publisher.publish(
            _tact_spec(),
            dry_run=False,
            inputs={"github_token": token},
        )

    message = str(exc.value)
    assert token not in message
    assert "ghp_should_not_leak" not in message
    assert "secret input should not echo" not in message
    assert exc.value.status_code == 500


def test_from_env_reads_configuration_and_url_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "env-owner/env-repo")
    monkeypatch.setenv("GITHUB_WORKFLOW_ID", "publish.yml")
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    monkeypatch.setenv("GITHUB_API_URL", "https://github.example/api/v3")
    monkeypatch.setenv("GITHUB_WORKFLOW_REF", "develop")

    publisher = GitHubWorkflowDispatchPublisher.from_env()
    result = publisher.publish(_design_brief(), dry_run=True)

    assert publisher.repository == "env-owner/env-repo"
    assert publisher.token == "env-token"
    assert result.endpoint == (
        "https://github.example/api/v3/repos/env-owner/env-repo/actions/workflows/"
        "publish.yml/dispatches"
    )
    assert result.payload["ref"] == "develop"
    assert result.payload["inputs"]["design_brief_id"] == "dbf-dispatch001"
    assert result.payload["inputs"]["idea_id"] == "bu-lead001"
    assert result.payload["inputs"]["source_type"] == "design_brief"


def test_invalid_configuration_and_export() -> None:
    with pytest.raises(GitHubWorkflowDispatchPublishError, match="owner/repo format"):
        GitHubWorkflowDispatchPublisher("owner/repo/extra", workflow_id="publish.yml")

    with pytest.raises(GitHubWorkflowDispatchPublishError, match="workflow_id"):
        GitHubWorkflowDispatchPublisher("owner/repo")

    assert ExportedGitHubWorkflowDispatchPublisher is GitHubWorkflowDispatchPublisher


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
