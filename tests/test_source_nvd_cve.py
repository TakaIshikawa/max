"""Tests for the NVD CVE source adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from max.sources.base import AdapterRateLimitError
from max.sources.nvd_cve import (
    NvdCveAdapter,
    _DEFAULT_API_KEY_ENV,
    _DEFAULT_MAX_AGE_DAYS,
    _DEFAULT_SEVERITIES,
    _build_params,
    _extract_affected_products,
    _extract_cwes,
    _extract_cvss,
    _parse_dt,
)
from max.types.signal import SignalSourceType


MOCK_CVE = {
    "cve": {
        "id": "CVE-2026-12345",
        "sourceIdentifier": "security@example.com",
        "published": "2026-04-15T10:30:00.000",
        "lastModified": "2026-04-16T11:00:00.000",
        "vulnStatus": "Analyzed",
        "descriptions": [
            {"lang": "en", "value": "Critical SQL injection in example server."},
        ],
        "metrics": {
            "cvssMetricV31": [
                {
                    "type": "Primary",
                    "cvssData": {
                        "baseScore": 9.8,
                        "baseSeverity": "CRITICAL",
                        "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                    },
                },
            ],
        },
        "weaknesses": [
            {"description": [{"lang": "en", "value": "CWE-89"}]},
            {"description": [{"lang": "en", "value": "NVD-CWE-noinfo"}]},
        ],
        "configurations": [
            {
                "nodes": [
                    {
                        "cpeMatch": [
                            {
                                "vulnerable": True,
                                "criteria": "cpe:2.3:a:example:server:1.0:*:*:*:*:*:*:*",
                            },
                            {
                                "vulnerable": False,
                                "criteria": "cpe:2.3:a:example:client:1.0:*:*:*:*:*:*:*",
                            },
                        ],
                    },
                ],
            },
        ],
    },
}


MOCK_CVE_2 = {
    "cve": {
        "id": "CVE-2026-67890",
        "published": "2026-04-14T08:00:00.000Z",
        "descriptions": [{"lang": "en", "value": "High severity XSS in web panel."}],
        "metrics": {
            "cvssMetricV31": [
                {
                    "cvssData": {
                        "baseScore": 7.5,
                        "baseSeverity": "HIGH",
                        "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:N",
                    },
                },
            ],
        },
        "weaknesses": [{"description": [{"lang": "en", "value": "CWE-79"}]}],
        "configurations": [],
    },
}


def test_nvd_cve_default_config() -> None:
    adapter = NvdCveAdapter()
    assert adapter.keywords == []
    assert adapter.severities == _DEFAULT_SEVERITIES
    assert adapter.cvss_min is None
    assert adapter.max_age_days == _DEFAULT_MAX_AGE_DAYS
    assert adapter.api_key_env == _DEFAULT_API_KEY_ENV


def test_nvd_cve_custom_config() -> None:
    adapter = NvdCveAdapter(
        config={
            "keywords": ["kubernetes", "openssl"],
            "severities": ["critical"],
            "cvss_min": 8.5,
            "max_age_days": 7,
            "api_key_env": "CUSTOM_NVD_KEY",
        }
    )
    assert adapter.keywords == ["kubernetes", "openssl"]
    assert adapter.severities == ["critical"]
    assert adapter.cvss_min == 8.5
    assert adapter.max_age_days == 7
    assert adapter.api_key_env == "CUSTOM_NVD_KEY"


def test_build_params_includes_nvd_filters() -> None:
    params = _build_params(
        keyword="openssl",
        severity="critical",
        max_age_days=10,
        results_per_page=25,
    )
    assert params["keywordSearch"] == "openssl"
    assert params["cvssV3Severity"] == "CRITICAL"
    assert params["resultsPerPage"] == 25
    assert params["startIndex"] == 0
    assert "pubStartDate" in params
    assert "pubEndDate" in params


def test_extract_cvss_prefers_primary_v31() -> None:
    score, severity, vector = _extract_cvss(MOCK_CVE["cve"])
    assert score == 9.8
    assert severity == "critical"
    assert vector == "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"


def test_extract_cwes_skips_noinfo() -> None:
    assert _extract_cwes(MOCK_CVE["cve"]) == ["CWE-89"]


def test_extract_affected_products_from_cpe() -> None:
    assert _extract_affected_products(MOCK_CVE["cve"]) == ["example/server"]


def test_parse_dt_accepts_nvd_timestamps() -> None:
    assert _parse_dt("2026-04-15T10:30:00.000") is not None
    assert _parse_dt("2026-04-15T10:30:00.000Z") is not None
    assert _parse_dt("not a date") is None


@pytest.mark.asyncio
async def test_nvd_cve_adapter_fetch_success() -> None:
    adapter = NvdCveAdapter(config={"keywords": ["server"], "severities": ["critical"]})

    requested_params: list[dict] = []

    async def mock_fetch(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        requested_params.append(kwargs["params"])
        return MagicMock(json=lambda: {"vulnerabilities": [MOCK_CVE]})

    with patch("max.sources.nvd_cve.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert requested_params[0]["keywordSearch"] == "server"
    assert requested_params[0]["cvssV3Severity"] == "CRITICAL"

    signal = signals[0]
    assert signal.source_type == SignalSourceType.SECURITY
    assert signal.source_adapter == "nvd_cve"
    assert signal.title.startswith("[CRITICAL] CVSS 9.8 CVE-2026-12345")
    assert signal.url == "https://nvd.nist.gov/vuln/detail/CVE-2026-12345"
    assert signal.credibility == 0.9800000000000001
    assert "security" in signal.tags
    assert "cwe-89" in signal.tags
    assert "sql-injection" in signal.tags
    assert signal.metadata["cve_id"] == "CVE-2026-12345"
    assert signal.metadata["severity"] == "critical"
    assert signal.metadata["cvss_score"] == 9.8
    assert signal.metadata["cwes"] == ["CWE-89"]
    assert signal.metadata["affected_products"] == ["example/server"]


@pytest.mark.asyncio
async def test_nvd_cve_adapter_deduplicates_cve_ids() -> None:
    adapter = NvdCveAdapter(config={"keywords": ["one", "two"], "severities": ["high"]})

    async def mock_fetch(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        return MagicMock(json=lambda: {"vulnerabilities": [MOCK_CVE]})

    with patch("max.sources.nvd_cve.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=10)

    assert [s.metadata["cve_id"] for s in signals] == ["CVE-2026-12345"]


@pytest.mark.asyncio
async def test_nvd_cve_adapter_applies_cvss_min() -> None:
    adapter = NvdCveAdapter(config={"severities": [], "cvss_min": 8.0})

    async def mock_fetch(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        return MagicMock(json=lambda: {"vulnerabilities": [MOCK_CVE_2, MOCK_CVE]})

    with patch("max.sources.nvd_cve.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=10)

    assert [s.metadata["cve_id"] for s in signals] == ["CVE-2026-12345"]


@pytest.mark.asyncio
async def test_nvd_cve_adapter_handles_rate_limit() -> None:
    adapter = NvdCveAdapter(config={"keywords": ["server"], "severities": ["critical"]})

    async def mock_fetch(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        raise AdapterRateLimitError("nvd_cve", url)

    with patch("max.sources.nvd_cve.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=5)

    assert signals == []


@pytest.mark.asyncio
async def test_nvd_cve_adapter_handles_malformed_response() -> None:
    adapter = NvdCveAdapter(config={"severities": ["critical"]})

    async def mock_fetch(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        return MagicMock(json=lambda: {"not_vulnerabilities": []})

    with patch("max.sources.nvd_cve.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=5)

    assert signals == []


@pytest.mark.asyncio
async def test_nvd_cve_adapter_uses_configured_api_key_env() -> None:
    adapter = NvdCveAdapter(config={"api_key_env": "CUSTOM_NVD_KEY"})

    async def mock_fetch(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        return MagicMock(json=lambda: {"vulnerabilities": []})

    with patch.dict("os.environ", {"CUSTOM_NVD_KEY": "secret"}, clear=False), \
         patch("max.sources.nvd_cve.fetch_with_retry", mock_fetch), \
         patch("max.sources.nvd_cve.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value = MagicMock()
        await adapter.fetch(limit=1)

    assert mock_client.call_args.kwargs["headers"]["apiKey"] == "secret"


@pytest.mark.asyncio
async def test_nvd_cve_adapter_name_and_source_type() -> None:
    adapter = NvdCveAdapter()
    assert adapter.name == "nvd_cve"
    assert adapter.source_type == SignalSourceType.SECURITY.value
