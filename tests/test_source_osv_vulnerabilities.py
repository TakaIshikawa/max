"""Tests for the OSV.dev vulnerability source adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from max.sources.osv_vulnerabilities import (
    OSV_QUERY_API,
    OSV_QUERY_BATCH_API,
    OsvVulnerabilitiesAdapter,
    _extract_affected_packages,
    _extract_severity,
    _parse_dt,
)
from max.sources.registry import get_adapter, reload_registry
from max.types.signal import SignalSourceType


MOCK_OSV_HIGH = {
    "id": "OSV-2026-0001",
    "summary": "Prototype pollution in example-package",
    "details": "A crafted payload can trigger prototype pollution in example-package.",
    "aliases": ["CVE-2026-11111", "GHSA-abcd-efgh-ijkl"],
    "published": "2026-04-01T10:00:00Z",
    "modified": "2026-04-20T12:00:00Z",
    "database_specific": {"severity": "HIGH"},
    "affected": [
        {"package": {"name": "example-package", "ecosystem": "npm"}},
        {"package": {"name": "example-package", "ecosystem": "npm"}},
    ],
    "references": [
        {"type": "ADVISORY", "url": "https://osv.dev/vulnerability/OSV-2026-0001"},
    ],
}

MOCK_OSV_MEDIUM = {
    "id": "OSV-2026-0002",
    "summary": "Medium issue in helper-lib",
    "details": "A medium severity vulnerability in helper-lib.",
    "aliases": [],
    "published": "2026-04-02T10:00:00Z",
    "modified": "2026-04-21T12:00:00Z",
    "database_specific": {"severity": "MODERATE"},
    "affected": [{"package": {"name": "helper-lib", "ecosystem": "PyPI"}}],
}

MOCK_OSV_CRITICAL = {
    "id": "OSV-2026-0003",
    "summary": "Critical issue in fastapi",
    "details": "A critical vulnerability in fastapi.",
    "aliases": ["CVE-2026-22222"],
    "published": "2026-04-03T10:00:00Z",
    "modified": "2026-04-22T12:00:00Z",
    "database_specific": {"severity": "CRITICAL"},
    "affected": [{"package": {"name": "fastapi", "ecosystem": "PyPI"}}],
}


def test_osv_adapter_can_be_instantiated_by_registry_name() -> None:
    reload_registry()

    adapter = get_adapter("osv_vulnerabilities")

    assert adapter.name == "osv_vulnerabilities"
    assert adapter.source_type == SignalSourceType.SECURITY.value


def test_osv_adapter_config_defaults_and_custom_values() -> None:
    adapter = OsvVulnerabilitiesAdapter(
        config={
            "ecosystems": ["npm"],
            "packages": [{"name": "example-package", "ecosystem": "npm"}],
            "queries": ["lodash"],
            "severity_min": "high",
            "modified_since_days": 14,
            "max_items": 5,
        }
    )

    assert adapter.ecosystems == ["npm"]
    assert adapter.packages == [{"package": {"name": "example-package", "ecosystem": "npm"}}]
    assert adapter.queries == ["lodash"]
    assert adapter.severity_min == "high"
    assert adapter.modified_since_days == 14
    assert adapter.max_items == 5


def test_extract_affected_packages_deduplicates_package_ecosystem_pairs() -> None:
    assert _extract_affected_packages(MOCK_OSV_HIGH) == [
        {"name": "example-package", "ecosystem": "npm"}
    ]


def test_extract_severity_normalizes_database_specific_severity() -> None:
    assert _extract_severity(MOCK_OSV_HIGH) == "high"
    assert _extract_severity(MOCK_OSV_MEDIUM) == "medium"
    assert _extract_severity({"id": "OSV-1"}) == "unknown"


def test_extract_severity_derives_rank_from_cvss_v3_vector() -> None:
    vuln = {
        "severity": [
            {
                "type": "CVSS_V3",
                "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
            }
        ]
    }

    assert _extract_severity(vuln) == "critical"


def test_parse_dt_accepts_osv_timestamps() -> None:
    assert _parse_dt("2026-04-20T12:00:00Z") is not None
    assert _parse_dt("2026-04-20T12:00:00+00:00") is not None
    assert _parse_dt("not a date") is None


@pytest.mark.asyncio
async def test_osv_package_queries_produce_deduplicated_security_signals() -> None:
    adapter = OsvVulnerabilitiesAdapter(
        config={
            "ecosystems": ["npm"],
            "packages": [{"name": "example-package", "ecosystem": "npm"}],
            "queries": ["example-package"],
            "severity_min": "high",
            "modified_since_days": 0,
            "max_items": 10,
        }
    )
    requests: list[dict] = []

    async def mock_fetch(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        requests.append({"url": url, **kwargs})
        if url == OSV_QUERY_BATCH_API:
            return MagicMock(
                json=lambda: {
                    "results": [
                        {"vulns": [MOCK_OSV_HIGH, MOCK_OSV_MEDIUM]},
                        {"vulns": [MOCK_OSV_HIGH]},
                    ]
                }
            )
        return MagicMock(json=lambda: {"vulns": []})

    with patch("max.sources.osv_vulnerabilities.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=10)

    assert [request["url"] for request in requests] == [OSV_QUERY_BATCH_API, OSV_QUERY_API]
    assert requests[0]["method"] == "POST"
    assert requests[0]["json"] == {
        "queries": [{"package": {"name": "example-package", "ecosystem": "npm"}}]
    }

    assert len(signals) == 1
    signal = signals[0]
    assert signal.source_type == SignalSourceType.SECURITY
    assert signal.source_adapter == "osv_vulnerabilities"
    assert signal.title.startswith("OSV OSV-2026-0001 [HIGH]")
    assert signal.url == "https://osv.dev/vulnerability/OSV-2026-0001"
    assert signal.published_at is not None
    assert "npm" in signal.tags
    assert "example-package" in signal.tags
    assert signal.metadata["osv_id"] == "OSV-2026-0001"
    assert signal.metadata["aliases"] == ["CVE-2026-11111", "GHSA-abcd-efgh-ijkl"]
    assert signal.metadata["severity"] == "high"
    assert signal.metadata["ecosystems"] == ["npm"]
    assert signal.metadata["packages"] == ["example-package"]
    assert signal.metadata["affected_packages"] == [
        {"name": "example-package", "ecosystem": "npm"}
    ]
    assert signal.metadata["modified"] == "2026-04-20T12:00:00Z"


@pytest.mark.asyncio
async def test_osv_ecosystem_mode_fetches_without_package_queries() -> None:
    adapter = OsvVulnerabilitiesAdapter(
        config={
            "ecosystems": ["PyPI"],
            "severity_min": "critical",
            "modified_since_days": 0,
            "max_items": 5,
        }
    )
    requests: list[dict] = []

    async def mock_fetch(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        requests.append({"url": url, **kwargs})
        return MagicMock(json=lambda: {"vulns": [MOCK_OSV_MEDIUM, MOCK_OSV_CRITICAL]})

    with patch("max.sources.osv_vulnerabilities.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=5)

    assert [request["url"] for request in requests] == [OSV_QUERY_API]
    assert requests[0]["json"] == {"package": {"ecosystem": "PyPI"}}
    assert [signal.metadata["osv_id"] for signal in signals] == ["OSV-2026-0003"]
    assert signals[0].metadata["ecosystems"] == ["PyPI"]
