from __future__ import annotations

import httpx
import pytest

from max.imports.snyk_vulnerabilities_adapter import SnykVulnerabilitiesAdapter, SnykVulnerabilitiesImportAdapter


@pytest.mark.asyncio
async def test_fetches_vulnerabilities_with_filters_and_maps_security_signal() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"issues": [_issue()]})

    adapter = SnykVulnerabilitiesImportAdapter(
        organization_id="org-1",
        token="snyk-token",
        api_url="https://snyk.example",
        project_ids=["proj-1"],
        severity=["high", "critical"],
        status="open",
        per_page=10,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert SnykVulnerabilitiesAdapter is SnykVulnerabilitiesImportAdapter
    assert requests[0].url.path == "/v1/org/org-1/issues"
    assert requests[0].headers["Authorization"] == "token snyk-token"
    assert requests[0].url.params["projectId"] == "proj-1"
    assert requests[0].url.params["severity"] == "high"
    assert requests[0].url.params.get_list("severity") == ["high", "critical"]
    assert requests[0].url.params["status"] == "open"
    assert requests[0].url.params["perPage"] == "5"
    assert signals[0].source_type == "security"
    assert signals[0].title == "Prototype Pollution"
    assert signals[0].metadata["severity"] == "high"
    assert signals[0].metadata["package"] == "lodash"
    assert signals[0].metadata["project"] == "web-app"
    assert signals[0].metadata["issue_url"] == "https://app.snyk.io/org/org-1/project/proj-1#issue-SNYK-JS-LODASH-567746"
    assert signals[0].metadata["identifiers"]["CVE"] == ["CVE-2020-8203"]
    assert signals[0].metadata["cvss_score"] == 7.4
    assert signals[0].metadata["exploit_maturity"] == "proof-of-concept"
    assert signals[0].metadata["disclosure_date"] == "2020-07-15T00:00:00Z"
    assert signals[0].metadata["status"] == "open"
    assert {"snyk", "vulnerability", "high"}.issubset(set(signals[0].tags))


@pytest.mark.asyncio
async def test_paginates_and_respects_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"issues": [_issue("1"), _issue("2")]})

    adapter = SnykVulnerabilitiesImportAdapter(
        organization_id="org",
        token="token",
        per_page=2,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    assert len(signals) == 3
    assert requests[0].url.params["page"] == "1"
    assert requests[1].url.params["page"] == "2"
    assert requests[1].url.params["perPage"] == "1"


@pytest.mark.asyncio
async def test_missing_config_non_positive_limit_and_errors_return_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SNYK_ORGANIZATION_ID", raising=False)
    monkeypatch.delenv("SNYK_TOKEN", raising=False)
    assert await SnykVulnerabilitiesImportAdapter(token="token").fetch(limit=10) == []
    assert await SnykVulnerabilitiesImportAdapter(organization_id="org").fetch(limit=10) == []
    assert await SnykVulnerabilitiesImportAdapter(organization_id="org", token="token").fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="nope")

    adapter = SnykVulnerabilitiesImportAdapter(organization_id="org", token="token", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await adapter.fetch(limit=1) == []


def _issue(suffix: str = "") -> dict:
    return {
        "id": f"SNYK-JS-LODASH-567746{suffix}",
        "issue": {
            "id": f"SNYK-JS-LODASH-567746{suffix}",
            "title": "Prototype Pollution",
            "severity": "high",
            "identifiers": {"CVE": ["CVE-2020-8203"], "CWE": ["CWE-1321"]},
            "cvssScore": 7.4,
            "exploitMaturity": "proof-of-concept",
            "disclosureTime": "2020-07-15T00:00:00Z",
        },
        "pkg": {"name": "lodash"},
        "project": {"id": "proj-1", "name": "web-app"},
        "status": "open",
        "url": "https://app.snyk.io/org/org-1/project/proj-1#issue-SNYK-JS-LODASH-567746",
        "isPatchable": True,
    }
