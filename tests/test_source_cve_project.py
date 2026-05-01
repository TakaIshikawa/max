"""Tests for the CVEProject cvelist v5 source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from max.sources.base import AdapterFetchError
from max.sources.cve_project import CveProjectAdapter, parse_cve_project_records
from max.sources.registry import get_adapter, get_adapter_metadata, list_adapters, reload_registry
from max.types.signal import SignalSourceType


MOCK_CVE_RECORD = {
    "dataType": "CVE_RECORD",
    "dataVersion": "5.1",
    "cveMetadata": {
        "cveId": "CVE-2026-12345",
        "assignerShortName": "example-cna",
        "state": "PUBLISHED",
        "datePublished": "2026-04-20T10:30:00.000Z",
        "dateUpdated": "2026-04-21T11:00:00.000Z",
    },
    "containers": {
        "cna": {
            "providerMetadata": {
                "shortName": "example-cna",
                "dateUpdated": "2026-04-21T11:00:00.000Z",
            },
            "title": "Example Gateway command injection vulnerability",
            "descriptions": [
                {
                    "lang": "en",
                    "value": "Example Gateway allows remote command injection.",
                },
            ],
            "problemTypes": [
                {
                    "descriptions": [
                        {
                            "lang": "en",
                            "cweId": "CWE-94",
                            "description": "Improper Control of Generation of Code",
                        },
                    ],
                },
            ],
            "affected": [
                {"vendor": "Example", "product": "Gateway"},
            ],
            "metrics": [
                {
                    "cvssV3_1": {
                        "version": "3.1",
                        "baseScore": 9.8,
                        "baseSeverity": "CRITICAL",
                        "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                    },
                },
            ],
            "references": [
                {"url": "https://example.com/security/CVE-2026-12345"},
            ],
        },
    },
}


MOCK_LOW_DETAIL_RECORD = {
    "cveMetadata": {
        "cveId": "CVE-2026-22222",
        "state": "PUBLISHED",
        "datePublished": "2026-04-19T00:00:00Z",
        "dateUpdated": "2026-04-19T00:00:00Z",
    },
    "containers": {
        "cna": {
            "descriptions": [{"lang": "en", "value": "Sparse CVEProject record."}],
            "metrics": [{"cvssV3_1": {"baseScore": "not numeric"}}],
        },
    },
}


def test_parse_cve_project_records_maps_records_to_signals() -> None:
    signals = parse_cve_project_records(
        {"records": [MOCK_CVE_RECORD]},
        max_age_days=30,
        now=datetime(2026, 4, 25, tzinfo=timezone.utc),
    )

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "cve_project:CVE-2026-12345"
    assert signal.source_type == SignalSourceType.SECURITY
    assert signal.source_adapter == "cve_project"
    assert signal.title.startswith("[CRITICAL] CVSS 9.8 CVE-2026-12345")
    assert signal.content == "Example Gateway allows remote command injection."
    assert signal.url == "https://www.cve.org/CVERecord?id=CVE-2026-12345"
    assert signal.published_at == datetime(2026, 4, 20, 10, 30, tzinfo=timezone.utc)
    assert signal.credibility == 0.9800000000000001
    assert "security" in signal.tags
    assert "cve" in signal.tags
    assert "cve-project" in signal.tags
    assert "critical" in signal.tags
    assert "cwe-94" in signal.tags
    assert "code-injection" in signal.tags
    assert signal.metadata["cve_id"] == "CVE-2026-12345"
    assert signal.metadata["state"] == "PUBLISHED"
    assert signal.metadata["severity"] == "critical"
    assert signal.metadata["cvss_score"] == 9.8
    assert signal.metadata["cvss_vector"] == "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
    assert signal.metadata["cvss_version"] == "3.1"
    assert signal.metadata["cwes"] == ["CWE-94"]
    assert signal.metadata["affected_products"] == ["Example/Gateway"]
    assert signal.metadata["references"] == ["https://example.com/security/CVE-2026-12345"]
    assert signal.metadata["assigner_short_name"] == "example-cna"
    assert signal.metadata["signal_role"] == "problem"


def test_parse_cve_project_records_skips_or_degrades_malformed_records() -> None:
    payload = [
        {"containers": {"cna": {"title": "missing metadata"}}},
        {"cveMetadata": {"state": "PUBLISHED"}},
        MOCK_LOW_DETAIL_RECORD,
        "not a record",
    ]

    signals = parse_cve_project_records(payload, max_age_days=0)

    assert [signal.metadata["cve_id"] for signal in signals] == ["CVE-2026-22222"]
    signal = signals[0]
    assert signal.metadata["cvss_score"] is None
    assert signal.metadata["severity"] == "unknown"
    assert signal.credibility == 0.5
    assert signal.content == "Sparse CVEProject record."


def test_parse_cve_project_records_handles_empty_and_bad_payload_shapes() -> None:
    assert parse_cve_project_records([], max_age_days=0) == []
    assert parse_cve_project_records({}, max_age_days=0) == []
    assert parse_cve_project_records({"records": []}, max_age_days=0) == []
    assert parse_cve_project_records({"records": "bad"}, max_age_days=0) == []
    assert parse_cve_project_records("bad", max_age_days=0) == []


def test_parse_cve_project_records_filters_and_deduplicates() -> None:
    rejected = {
        "cveMetadata": {
            "cveId": "CVE-2026-99999",
            "state": "REJECTED",
            "dateUpdated": "2026-04-20T00:00:00Z",
        },
        "containers": {
            "cna": {
                "rejectedReasons": [{"lang": "en", "value": "Duplicate assignment."}],
            },
        },
    }

    signals = parse_cve_project_records(
        [MOCK_CVE_RECORD, MOCK_CVE_RECORD, rejected],
        keywords=["Gateway"],
        max_age_days=7,
        now=datetime(2026, 4, 25, tzinfo=timezone.utc),
        limit=10,
    )

    assert [signal.metadata["cve_id"] for signal in signals] == ["CVE-2026-12345"]

    rejected_signals = parse_cve_project_records(
        [rejected],
        include_rejected=True,
        max_age_days=0,
    )

    assert rejected_signals[0].metadata["state"] == "REJECTED"
    assert rejected_signals[0].content == "Duplicate assignment."


def test_cve_project_adapter_config_properties() -> None:
    adapter = CveProjectAdapter(
        config={
            "base_url": "https://example.test/cve",
            "recent_path": "recent",
            "keywords": ["gateway"],
            "max_age_days": "14",
            "include_rejected": "true",
        }
    )

    assert adapter.name == "cve_project"
    assert adapter.source_type == SignalSourceType.SECURITY.value
    assert adapter.base_url == "https://example.test/cve"
    assert adapter.recent_path == "recent"
    assert adapter.keywords == ["gateway"]
    assert adapter.max_age_days == 14
    assert adapter.include_rejected is True


@pytest.mark.asyncio
async def test_cve_project_adapter_fetch_success() -> None:
    adapter = CveProjectAdapter(
        config={
            "base_url": "https://example.test/api",
            "recent_path": "recent",
            "max_age_days": 0,
        }
    )
    requested: dict = {}

    async def mock_fetch(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        requested["url"] = url
        requested["kwargs"] = kwargs
        return MagicMock(json=lambda: [MOCK_CVE_RECORD])

    with patch("max.sources.cve_project.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=5)

    assert requested["url"] == "https://example.test/api/recent"
    assert requested["kwargs"]["adapter_name"] == "cve_project"
    assert requested["kwargs"]["headers"]["Accept"] == "application/json"
    assert requested["kwargs"]["params"] == {"limit": 5}
    assert [signal.id for signal in signals] == ["cve_project:CVE-2026-12345"]


@pytest.mark.asyncio
async def test_cve_project_adapter_fetch_empty_response() -> None:
    adapter = CveProjectAdapter(config={"max_age_days": 0})

    async def mock_fetch(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        return MagicMock(json=lambda: {"records": []})

    with patch("max.sources.cve_project.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=5)

    assert signals == []


@pytest.mark.asyncio
async def test_cve_project_adapter_handles_http_errors() -> None:
    adapter = CveProjectAdapter()

    async def mock_fetch(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        raise AdapterFetchError("cve_project", 503, url)

    with patch("max.sources.cve_project.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=5)

    assert signals == []


@pytest.mark.asyncio
async def test_cve_project_adapter_handles_bad_json() -> None:
    adapter = CveProjectAdapter()

    async def mock_fetch(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        response = MagicMock()
        response.json.side_effect = ValueError("bad json")
        return response

    with patch("max.sources.cve_project.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=5)

    assert signals == []


def test_cve_project_registry_registration_and_metadata() -> None:
    with patch("max.config.MAX_ADAPTERS", "cve_project"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()

        assert list_adapters() == ["cve_project"]
        assert get_adapter("cve_project").name == "cve_project"
        metadata = get_adapter_metadata()["cve_project"]

    assert metadata.config_keys == [
        "base_url",
        "recent_path",
        "keywords",
        "max_age_days",
        "include_rejected",
    ]
    assert metadata.required_keys == []
    assert "CVEProject cvelist v5" in metadata.description

    reload_registry()
