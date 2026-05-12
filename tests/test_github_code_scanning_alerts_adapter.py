"""Tests for GitHub code scanning alerts import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.github_code_scanning_alerts_adapter import GitHubCodeScanningAlertsAdapter
from max.types.signal import SignalSourceType


ALERT = {
    "number": 7,
    "state": "open",
    "html_url": "https://github.example/acme/api/security/code-scanning/7",
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-02T10:00:00Z",
    "rule": {
        "id": "py/sql-injection",
        "name": "SQL injection",
        "severity": "error",
        "security_severity_level": "high",
        "description": "Unsanitized SQL input",
    },
    "tool": {"name": "CodeQL"},
    "most_recent_instance": {
        "ref": "refs/heads/main",
        "message": {"text": "User input reaches SQL query"},
        "location": {"path": "app/db.py", "start_line": 42, "end_line": 43},
    },
}


@pytest.mark.asyncio
async def test_github_code_scanning_fetch_filters_paginates_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=[ALERT])
        return httpx.Response(200, json=[{**ALERT, "number": 8}])

    adapter = GitHubCodeScanningAlertsAdapter(
        token="gh-token",
        api_url="https://github.example/api/v3",
        config={"repository": "acme/api", "state": "open", "branch": "main", "severity": "high", "per_page": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/api/v3/repos/acme/api/code-scanning/alerts"
    assert requests[0].url.params["state"] == "open"
    assert requests[0].url.params["branch"] == "main"
    assert requests[0].url.params["severity"] == "high"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[1].url.params["page"] == "2"
    assert requests[0].headers["Authorization"] == "Bearer gh-token"
    assert signals[0].source_type == SignalSourceType.FAILURE_DATA
    assert signals[0].source_adapter == "github_code_scanning_alerts_import"
    assert signals[0].title == "acme/api code scanning alert 7: py/sql-injection"
    assert signals[0].content == "User input reaches SQL query"
    assert signals[0].metadata["repository"] == "acme/api"
    assert signals[0].metadata["alert_number"] == 7
    assert signals[0].metadata["severity"] == "error"
    assert signals[0].metadata["security_severity_level"] == "high"
    assert signals[0].metadata["tool_name"] == "CodeQL"
    assert signals[0].metadata["location"]["path"] == "app/db.py"


@pytest.mark.asyncio
async def test_github_code_scanning_empty_for_missing_config_or_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert await GitHubCodeScanningAlertsAdapter(config={"repository": "acme/api"}).fetch() == []
    assert await GitHubCodeScanningAlertsAdapter(token="token", owner="acme").fetch() == []
    assert await GitHubCodeScanningAlertsAdapter(token="token", owner="acme", repo="api").fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    adapter = GitHubCodeScanningAlertsAdapter(
        token="bad",
        owner="acme",
        repo="api",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await adapter.fetch() == []
