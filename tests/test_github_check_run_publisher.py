from __future__ import annotations

import json

import httpx

from max.publisher.github_check_runs import GitHubCheckRunPublisher
from tests.test_intercom_conversation_note_publisher import _tact_spec


def test_dry_run_returns_github_check_run_payload() -> None:
    publisher = GitHubCheckRunPublisher(repository="acme/widgets", head_sha="abc123")

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.payload["repository"] == "acme/widgets"
    assert result.payload["check_run"]["head_sha"] == "abc123"
    assert result.payload["check_run"]["conclusion"] == "success"
    assert "Support teams need handoff context" in result.payload["check_run"]["output"]["summary"]


def test_live_publish_posts_check_run() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": 123, "html_url": "https://github/check"})

    publisher = GitHubCheckRunPublisher(
        repository="acme/widgets",
        head_sha="abc123",
        token="gh_token",
        api_url="https://github.example.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.check_run_id == "123"
    assert result.check_run_url == "https://github/check"
    assert requests[0].url == "https://github.example.test/repos/acme/widgets/check-runs"
    assert requests[0].headers["Authorization"] == "Bearer gh_token"
    assert json.loads(requests[0].read())["head_sha"] == "abc123"
