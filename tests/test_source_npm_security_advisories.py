"""Tests for the npm security advisories source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.base import _circuit_breakers
from max.sources.npm_security_advisories import NpmSecurityAdvisoriesAdapter
from max.types.signal import SignalSourceType


@pytest.fixture(autouse=True)
def _reset_circuit_breakers() -> None:
    _circuit_breakers.clear()


def _response(payload: object, *, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


def _mock_client(request):
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(side_effect=request)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


def _payload() -> dict:
    return {
        "advisories": {
            "1001": {
                "id": 1001,
                "module_name": "minimist",
                "severity": "high",
                "title": "Prototype pollution in minimist",
                "vulnerable_versions": "<1.2.6",
                "patched_versions": ">=1.2.6",
                "cves": ["CVE-2021-44906"],
                "cwe": "CWE-1321",
                "url": "https://www.npmjs.com/advisories/1001",
                "created": "2026-04-01T10:00:00.000Z",
                "updated": "2026-04-02T11:00:00.000Z",
                "recommendation": "Upgrade to version 1.2.6 or later.",
            },
            "1002": {
                "id": 1002,
                "module_name": "lodash",
                "severity": "moderate",
                "title": "Command injection in lodash",
                "vulnerable_range": "<4.17.21",
                "patched_versions": ">=4.17.21",
                "identifiers": [{"type": "CVE", "value": "CVE-2020-8203"}],
                "cwes": ["CWE-94"],
            },
        }
    }


def test_adapter_properties_and_custom_config() -> None:
    adapter = NpmSecurityAdvisoriesAdapter(
        config={
            "package_names": ["Minimist", "minimist"],
            "packages": ["lodash"],
            "watchlist_terms": ["express"],
            "severities": ["HIGH", "moderate", "invalid", "high"],
            "advisory_url": "https://example.test/advisories",
            "max_results": "7",
            "timeout": "12.5",
        }
    )

    assert adapter.name == "npm_security_advisories"
    assert adapter.source_type == SignalSourceType.SECURITY.value
    assert adapter.package_names == ["minimist", "lodash", "express"]
    assert adapter.severities == ["high", "medium"]
    assert adapter.advisory_url == "https://example.test/advisories"
    assert adapter.max_results == 7
    assert adapter.timeout == 12.5


@pytest.mark.asyncio
async def test_fetches_advisory_signals_with_metadata() -> None:
    adapter = NpmSecurityAdvisoriesAdapter(
        config={"advisory_url": "https://example.test/advisories", "max_results": 10}
    )

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        assert method == "GET"
        assert url == "https://example.test/advisories"
        assert kwargs["headers"]["User-Agent"] == "max-npm-security-advisories-adapter/0.1"
        return _response(_payload())

    with patch("max.sources.npm_security_advisories.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    signal = signals[0]
    assert signal.id == "npm-security-advisory:1001"
    assert signal.source_type == SignalSourceType.SECURITY
    assert signal.source_adapter == "npm_security_advisories"
    assert signal.title == "npm advisory 1001 [HIGH]: Prototype pollution in minimist"
    assert "Vulnerable range: <1.2.6" in signal.content
    assert "Patched versions: >=1.2.6" in signal.content
    assert signal.url == "https://www.npmjs.com/advisories/1001"
    assert signal.published_at is not None
    assert {"security", "vulnerability", "npm", "javascript", "dependency-risk", "high", "minimist"} <= set(signal.tags)
    assert signal.metadata["signal_role"] == "problem"
    assert signal.metadata["signal_kind"] == "security_advisory"
    assert signal.metadata["package_ecosystem"] == "npm"
    assert signal.metadata["package_name"] == "minimist"
    assert signal.metadata["severity"] == "high"
    assert signal.metadata["vulnerable_range"] == "<1.2.6"
    assert signal.metadata["patched_versions"] == ">=1.2.6"
    assert signal.metadata["advisory_id"] == "1001"
    assert signal.metadata["identifiers"] == ["CVE-2021-44906", "CWE-1321"]
    assert signal.metadata["cves"] == ["CVE-2021-44906"]
    assert signal.metadata["cwes"] == ["CWE-1321"]
    assert signal.metadata["canonical_url"] == "https://www.npmjs.com/advisories/1001"
    assert signal.metadata["feed_url"] == "https://example.test/advisories"
    assert signal.metadata["updated_at"] == "2026-04-02T11:00:00+00:00"


@pytest.mark.asyncio
async def test_filters_by_package_and_severity_deterministically() -> None:
    adapter = NpmSecurityAdvisoriesAdapter(
        config={
            "package_names": ["lodash"],
            "severities": ["moderate"],
            "advisory_url": "https://example.test/advisories",
        }
    )

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        return _response(_payload())

    with patch("max.sources.npm_security_advisories.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["package_name"] == "lodash"
    assert signals[0].metadata["severity"] == "medium"
    assert signals[0].metadata["vulnerable_range"] == "<4.17.21"


@pytest.mark.asyncio
async def test_malformed_entries_are_skipped() -> None:
    adapter = NpmSecurityAdvisoriesAdapter(config={"advisory_url": "https://example.test/advisories"})
    payload = [
        {"id": "missing-package", "severity": "high", "vulnerable_versions": "<1.0.0"},
        {"id": "missing-range", "module_name": "broken", "severity": "critical"},
        {"id": "unknown-severity", "module_name": "broken", "severity": "bad", "vulnerable_versions": "<1.0.0"},
        {
            "advisory_id": "GHSA-aaaa-bbbb-cccc",
            "package": {"name": "@scope/pkg"},
            "severity": "critical",
            "range": "<2.0.0",
            "patched": ">=2.0.0",
            "identifiers": ["GHSA-aaaa-bbbb-cccc", "CVE-2026-12345"],
        },
    ]

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        return _response(payload)

    with patch("max.sources.npm_security_advisories.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].id == "npm-security-advisory:GHSA-aaaa-bbbb-cccc"
    assert signals[0].metadata["package_name"] == "@scope/pkg"
    assert signals[0].metadata["canonical_url"] == "https://www.npmjs.com/advisories/GHSA-aaaa-bbbb-cccc"
    assert signals[0].metadata["cves"] == ["CVE-2026-12345"]


@pytest.mark.asyncio
async def test_empty_fetch_behavior() -> None:
    adapter = NpmSecurityAdvisoriesAdapter(config={"advisory_url": "https://example.test/advisories"})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        return _response({"advisories": []})

    with patch("max.sources.npm_security_advisories.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        assert await adapter.fetch(limit=10) == []
        assert await adapter.fetch(limit=0) == []
