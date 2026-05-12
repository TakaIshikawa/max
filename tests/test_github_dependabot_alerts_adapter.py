from __future__ import annotations

import httpx
import pytest

from max.imports.github_dependabot_alerts_adapter import GitHubDependabotAlertsAdapter


def _alert(number: int = 1) -> dict:
    return {
        "number": number,
        "state": "open",
        "html_url": f"https://github.com/acme/app/security/dependabot/{number}",
        "created_at": "2026-05-01T10:00:00Z",
        "updated_at": "2026-05-02T10:00:00Z",
        "dismissed_reason": None,
        "dependency": {"package": {"ecosystem": "npm", "name": "lodash"}, "manifest_path": "package.json", "scope": "runtime"},
        "security_advisory": {
            "ghsa_id": "GHSA-1234",
            "cve_id": "CVE-2026-0001",
            "summary": "Prototype pollution in lodash",
            "severity": "high",
            "permalink": "https://github.com/advisories/GHSA-1234",
            "identifiers": [{"type": "GHSA", "value": "GHSA-1234"}],
        },
        "security_vulnerability": {
            "vulnerable_version_range": "< 4.17.21",
            "first_patched_version": {"identifier": "4.17.21"},
        },
    }


@pytest.mark.asyncio
async def test_fetches_paginated_dependabot_alerts_with_filters_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_alert(len(requests))])

    adapter = GitHubDependabotAlertsAdapter(
        token="gh-token",
        api_url="https://api.github.test",
        config={"owner": "acme", "repo": "app", "state": "open", "severity": "high", "per_page": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/repos/acme/app/dependabot/alerts"
    assert requests[0].url.params["state"] == "open"
    assert requests[0].url.params["severity"] == "high"
    assert requests[1].url.params["page"] == "2"
    assert requests[0].headers["Authorization"] == "Bearer gh-token"
    assert signals[0].id == "github-dependabot:acme/app:1"
    assert signals[0].metadata["repository"] == "acme/app"
    assert signals[0].metadata["package"] == "lodash"
    assert signals[0].metadata["ecosystem"] == "npm"
    assert signals[0].metadata["severity"] == "high"
    assert signals[0].metadata["ghsa_id"] == "GHSA-1234"
    assert signals[0].metadata["cve_id"] == "CVE-2026-0001"
    assert signals[0].metadata["affected_range"] == "< 4.17.21"
    assert signals[0].metadata["fixed_version"] == "4.17.21"
    assert signals[0].metadata["raw"]["number"] == 1


@pytest.mark.asyncio
async def test_dependabot_alerts_empty_without_config_or_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert await GitHubDependabotAlertsAdapter(config={"owner": "acme", "repo": "app"}).fetch() == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = GitHubDependabotAlertsAdapter(
        token="bad",
        config={"owner": "acme", "repo": "app"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await adapter.fetch() == []
