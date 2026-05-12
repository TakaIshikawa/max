from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.jira_versions import JiraVersionPublishError, JiraVersionPublisher


def test_builds_payload_with_only_provided_optional_fields() -> None:
    publisher = JiraVersionPublisher(site_url="https://jira.example.test", project_key="MAX")

    payload = publisher.build_version_payload(name="1.2.0", released=False)

    assert payload == {"name": "1.2.0", "project": "MAX", "released": False}


def test_from_env_reads_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JIRA_SITE_URL", "https://jira.example.test")
    monkeypatch.setenv("JIRA_EMAIL", "dev@example.test")
    monkeypatch.setenv("JIRA_API_TOKEN", "api-token")
    monkeypatch.setenv("JIRA_PROJECT_ID", "10001")

    publisher = JiraVersionPublisher.from_env()

    assert publisher.site_url == "https://jira.example.test"
    assert publisher.email == "dev@example.test"
    assert publisher.api_token == "api-token"
    assert publisher.project_id == "10001"


def test_live_publish_posts_version_with_basic_auth() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": "20001", "self": "https://jira.example.test/rest/api/3/version/20001"})

    publisher = JiraVersionPublisher(site_url="https://jira.example.test", email="dev@example.test", api_token="api-token", project_key="MAX", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(name="1.2.0", description="Release notes", release_date="2026-05-12", dry_run=False)

    assert result.version_id == "20001"
    assert requests[0].url == "https://jira.example.test/rest/api/3/version"
    assert requests[0].headers["Authorization"].startswith("Basic ")
    posted = json.loads(requests[0].read())
    assert posted["project"] == "MAX"
    assert posted["description"] == "Release notes"
    assert posted["releaseDate"] == "2026-05-12"


def test_supports_bearer_auth_and_missing_auth() -> None:
    requests: list[httpx.Request] = []
    publisher = JiraVersionPublisher(site_url="https://jira.example.test", bearer_token="bearer", project_id="10001", client=httpx.Client(transport=httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(201, json={"id": "1"}))))

    publisher.publish(name="1.0", dry_run=False)

    assert requests[0].headers["Authorization"] == "Bearer bearer"

    missing = JiraVersionPublisher(site_url="https://jira.example.test", project_key="MAX")
    with pytest.raises(JiraVersionPublishError, match="email/api_token or bearer_token"):
        missing.publish(name="1.0", dry_run=False)
