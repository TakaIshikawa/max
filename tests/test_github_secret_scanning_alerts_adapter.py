"""Tests for GitHub secret scanning alerts import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.github_secret_scanning_alerts_adapter import GitHubSecretScanningAlertsAdapter
from max.types.signal import SignalSourceType


ALERT = {
    "number": 9,
    "state": "open",
    "resolution": None,
    "validity": "active",
    "secret_type": "stripe_api_key",
    "secret_type_display_name": "Stripe API Key",
    "html_url": "https://github.example/acme/api/security/secret-scanning/9",
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-02T10:00:00Z",
    "resolved_at": None,
    "locations_url": "https://api.github.example/repos/acme/api/secret-scanning/alerts/9/locations",
    "location": {
        "type": "commit",
        "details": {
            "path": "config/prod.env",
            "start_line": 12,
            "end_line": 12,
            "start_column": 5,
            "end_column": 36,
            "blob_sha": "blob-1",
            "commit_sha": "commit-1",
        },
    },
}


@pytest.mark.asyncio
async def test_github_secret_scanning_fetch_filters_paginates_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=[ALERT])
        return httpx.Response(200, json=[{**ALERT, "number": 10, "state": "resolved", "resolution": "revoked"}])

    adapter = GitHubSecretScanningAlertsAdapter(
        token="gh-token",
        api_url="https://github.example/api/v3",
        config={
            "repository": "acme/api",
            "state": "open",
            "secret_type": "stripe_api_key",
            "resolution": "revoked",
            "before": "2026-06-01T00:00:00Z",
            "after": "2026-05-01T00:00:00Z",
            "validity": "active",
            "per_page": 1,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/api/v3/repos/acme/api/secret-scanning/alerts"
    assert requests[0].url.params["state"] == "open"
    assert requests[0].url.params["secret_type"] == "stripe_api_key"
    assert requests[0].url.params["resolution"] == "revoked"
    assert requests[0].url.params["before"] == "2026-06-01T00:00:00Z"
    assert requests[0].url.params["after"] == "2026-05-01T00:00:00Z"
    assert requests[0].url.params["validity"] == "active"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[1].url.params["page"] == "2"
    assert requests[0].headers["Authorization"] == "Bearer gh-token"
    signal = signals[0]
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "github_secret_scanning_alerts_import"
    assert signal.title == "acme/api secret scanning alert 9: stripe_api_key"
    assert signal.url == "https://github.example/acme/api/security/secret-scanning/9"
    assert signal.metadata["repository"] == "acme/api"
    assert signal.metadata["alert_number"] == 9
    assert signal.metadata["secret_type"] == "stripe_api_key"
    assert signal.metadata["state"] == "open"
    assert signal.metadata["resolution"] is None
    assert signal.metadata["validity"] == "active"
    assert signal.metadata["created_at"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["resolved_at"] is None
    assert signal.metadata["location"]["path"] == "config/prod.env"
    assert signal.metadata["location"]["commit_sha"] == "commit-1"
    assert "secret-scanning" in signal.tags


@pytest.mark.asyncio
async def test_github_secret_scanning_accepts_owner_repo_and_repository_argument() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[ALERT])

    adapter = GitHubSecretScanningAlertsAdapter(
        token="gh-token",
        repository="acme/api",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].url.path == "/repos/acme/api/secret-scanning/alerts"
    assert signals[0].metadata["repository"] == "acme/api"


@pytest.mark.asyncio
async def test_github_secret_scanning_empty_for_missing_config_non_positive_limit_or_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert await GitHubSecretScanningAlertsAdapter(config={"repository": "acme/api"}).fetch() == []
    assert await GitHubSecretScanningAlertsAdapter(token="token", owner="acme").fetch() == []
    assert await GitHubSecretScanningAlertsAdapter(token="token", owner="acme", repo="api").fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    adapter = GitHubSecretScanningAlertsAdapter(
        token="bad",
        owner="acme",
        repo="api",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await adapter.fetch() == []
