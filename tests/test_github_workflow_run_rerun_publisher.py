from __future__ import annotations

import httpx
import pytest

from max.publisher.github_workflow_run_rerun import (
    GitHubWorkflowRunRerunPublishError,
    GitHubWorkflowRunRerunPublisher,
)


def test_dry_run_returns_rerun_endpoint_without_network_call() -> None:
    publisher = GitHubWorkflowRunRerunPublisher(
        repository="owner/repo",
        run_id=123,
        token="secret",
        client=httpx.Client(transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(AssertionError("dry run should not make network calls")))),
    )

    result = publisher.publish(dry_run=True)

    assert result.status_code is None
    assert result.dry_run is True
    assert result.repository == "owner/repo"
    assert result.run_id == 123
    assert result.endpoint == "https://api.github.com/repos/owner/repo/actions/runs/123/rerun"
    assert result.payload["failed_jobs_only"] is False
    assert result.payload["metadata"]["publisher"] == "max.github_workflow_run_rerun"


def test_failed_jobs_only_chooses_failed_jobs_endpoint() -> None:
    publisher = GitHubWorkflowRunRerunPublisher(
        repository="owner/repo",
        run_id="456",
        failed_jobs_only=True,
    )

    result = publisher.publish(dry_run=True)

    assert result.endpoint == "https://api.github.com/repos/owner/repo/actions/runs/456/rerun-failed-jobs"
    assert result.payload["failed_jobs_only"] is True


def test_live_publish_posts_expected_endpoint_and_headers() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"message": "queued"})

    publisher = GitHubWorkflowRunRerunPublisher(
        repository="owner/repo",
        run_id=789,
        token="ghp_secret",
        api_url="https://github.example/api/v3",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(dry_run=False)

    assert result.status_code == 201
    assert result.response == {"message": "queued"}
    assert requests[0].method == "POST"
    assert requests[0].url == "https://github.example/api/v3/repos/owner/repo/actions/runs/789/rerun"
    assert requests[0].headers["Authorization"] == "Bearer ghp_secret"
    assert requests[0].headers["User-Agent"] == "max-github-workflow-run-rerun-publisher/1"
    assert result.payload["metadata"]["github_workflow_run_rerun_status_code"] == 201


def test_validates_repository_and_positive_run_id() -> None:
    with pytest.raises(GitHubWorkflowRunRerunPublishError, match="owner/repo format"):
        GitHubWorkflowRunRerunPublisher(repository="owner/repo/extra", run_id=1)

    with pytest.raises(GitHubWorkflowRunRerunPublishError, match="positive integer"):
        GitHubWorkflowRunRerunPublisher(repository="owner/repo", run_id=0)

    with pytest.raises(GitHubWorkflowRunRerunPublishError, match="positive integer"):
        GitHubWorkflowRunRerunPublisher(repository="owner/repo", run_id="bad")


def test_from_env_reads_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "env-owner/env-repo")
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    monkeypatch.setenv("GITHUB_WORKFLOW_RUN_ID", "321")
    monkeypatch.setenv("GITHUB_RERUN_FAILED_JOBS_ONLY", "true")
    monkeypatch.setenv("GITHUB_API_URL", "https://github.example/api/v3")

    publisher = GitHubWorkflowRunRerunPublisher.from_env()
    result = publisher.publish(dry_run=True)

    assert publisher.repository == "env-owner/env-repo"
    assert publisher.token == "env-token"
    assert publisher.run_id == 321
    assert result.endpoint == "https://github.example/api/v3/repos/env-owner/env-repo/actions/runs/321/rerun-failed-jobs"


def test_live_publish_requires_token() -> None:
    publisher = GitHubWorkflowRunRerunPublisher(repository="owner/repo", run_id=123)

    with pytest.raises(GitHubWorkflowRunRerunPublishError, match="GITHUB_TOKEN"):
        publisher.publish(dry_run=False)


def test_error_redacts_token_and_includes_status() -> None:
    publisher = GitHubWorkflowRunRerunPublisher(
        repository="owner/repo",
        run_id=123,
        token="ghp_secret",
        client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(500, text="bad ghp_secret"))
        ),
    )

    with pytest.raises(GitHubWorkflowRunRerunPublishError, match="HTTP 500") as exc:
        publisher.publish(dry_run=False)

    assert exc.value.status_code == 500
    assert "ghp_secret" not in str(exc.value)
    assert "[redacted]" in str(exc.value)
