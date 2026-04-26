"""Tests for the CISA KEV source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from max.sources.base import AdapterFetchError
from max.sources.cisa_kev import CISA_KEV_CATALOG_URL, CisaKevAdapter, parse_cisa_kev_catalog
from max.sources.registry import get_adapter, get_adapter_metadata, list_adapters, reload_registry
from max.types.signal import SignalSourceType


MOCK_CATALOG = {
    "title": "CISA Known Exploited Vulnerabilities Catalog",
    "catalogVersion": "2026.04.01",
    "dateReleased": "2026-04-20",
    "count": 3,
    "vulnerabilities": [
        {
            "cveID": "CVE-2026-1111",
            "vendorProject": "Example",
            "product": "Edge Gateway",
            "vulnerabilityName": "Example Edge Gateway command injection vulnerability",
            "dateAdded": "2026-04-10",
            "shortDescription": "Example Edge Gateway contains a command injection flaw.",
            "requiredAction": "Apply mitigations per vendor instructions.",
            "dueDate": "2026-05-01",
            "knownRansomwareCampaignUse": "Known",
            "notes": "Exploited by ransomware operators in the wild.",
        },
        {
            "cveID": "CVE-2026-2222",
            "vendorProject": "OtherCorp",
            "product": "Mail Server",
            "vulnerabilityName": "OtherCorp Mail Server authentication bypass",
            "dateAdded": "2026-03-20",
            "shortDescription": "Mail Server allows authentication bypass.",
            "requiredAction": "Disconnect affected systems until patched.",
            "dueDate": "2026-04-15",
            "knownRansomwareCampaignUse": "Unknown",
            "notes": "",
        },
        {
            "cveID": "CVE-2026-1111",
            "vendorProject": "Example",
            "product": "Edge Gateway",
            "vulnerabilityName": "Duplicate should be ignored",
            "dateAdded": "2026-04-11",
            "shortDescription": "Duplicate CVE entry.",
            "knownRansomwareCampaignUse": "Known",
        },
    ],
}


def test_parse_cisa_kev_catalog_maps_entries_to_signals() -> None:
    signals = parse_cisa_kev_catalog(
        MOCK_CATALOG,
        max_age_days=0,
        limit=10,
        now=datetime(2026, 4, 26, tzinfo=timezone.utc),
    )

    assert [signal.id for signal in signals] == ["cisa_kev:CVE-2026-1111", "cisa_kev:CVE-2026-2222"]

    signal = signals[0]
    assert signal.source_type == SignalSourceType.SECURITY
    assert signal.source_adapter == "cisa_kev"
    assert signal.title == (
        "CISA KEV CVE-2026-1111: "
        "Example Edge Gateway command injection vulnerability"
    )
    assert signal.url == f"{CISA_KEV_CATALOG_URL}?search_api_fulltext=CVE-2026-1111"
    assert signal.published_at == datetime(2026, 4, 10, tzinfo=timezone.utc)
    assert "security" in signal.tags
    assert "cisa-kev" in signal.tags
    assert "known-exploited" in signal.tags
    assert "ransomware" in signal.tags
    assert "example" in signal.tags
    assert "edge-gateway" in signal.tags
    assert signal.metadata["cve_id"] == "CVE-2026-1111"
    assert signal.metadata["vendor_project"] == "Example"
    assert signal.metadata["product"] == "Edge Gateway"
    assert signal.metadata["known_ransomware_campaign_use"] == "Known"
    assert signal.metadata["required_action"] == "Apply mitigations per vendor instructions."
    assert signal.metadata["signal_role"] == "problem"


def test_parse_cisa_kev_catalog_filters_by_keyword_vendor_product_age_and_ransomware() -> None:
    signals = parse_cisa_kev_catalog(
        MOCK_CATALOG,
        keywords=["command injection"],
        vendors=["example"],
        products=["gateway"],
        max_age_days=30,
        known_ransomware_campaign_use=True,
        now=datetime(2026, 4, 26, tzinfo=timezone.utc),
        limit=10,
    )

    assert [signal.metadata["cve_id"] for signal in signals] == ["CVE-2026-1111"]


def test_parse_cisa_kev_catalog_can_filter_for_unknown_ransomware_use() -> None:
    signals = parse_cisa_kev_catalog(
        MOCK_CATALOG,
        max_age_days=0,
        known_ransomware_campaign_use=False,
        now=datetime(2026, 4, 26, tzinfo=timezone.utc),
        limit=10,
    )

    assert [signal.metadata["cve_id"] for signal in signals] == ["CVE-2026-2222"]


def test_parse_cisa_kev_catalog_gracefully_handles_empty_or_malformed_payloads() -> None:
    assert parse_cisa_kev_catalog({}, max_age_days=0) == []
    assert parse_cisa_kev_catalog({"vulnerabilities": "bad"}, max_age_days=0) == []
    assert parse_cisa_kev_catalog({"vulnerabilities": [{"vendorProject": "Example"}]}, max_age_days=0) == []


def test_cisa_kev_adapter_config_properties() -> None:
    adapter = CisaKevAdapter(
        config={
            "keywords": ["rce"],
            "vendors": "Example",
            "products": ["Gateway"],
            "max_age_days": "14",
            "known_ransomware_campaign_use": "known",
        }
    )

    assert adapter.name == "cisa_kev"
    assert adapter.source_type == SignalSourceType.SECURITY.value
    assert adapter.keywords == ["rce"]
    assert adapter.vendors == ["Example"]
    assert adapter.products == ["Gateway"]
    assert adapter.max_age_days == 14
    assert adapter.known_ransomware_campaign_use is True


@pytest.mark.asyncio
async def test_cisa_kev_adapter_fetch_success() -> None:
    adapter = CisaKevAdapter(config={"vendors": ["Example"], "max_age_days": 0})

    async def mock_fetch(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        assert kwargs["adapter_name"] == "cisa_kev"
        assert kwargs["headers"]["Accept"] == "application/json"
        return MagicMock(json=lambda: MOCK_CATALOG)

    with patch("max.sources.cisa_kev.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=5)

    assert [signal.metadata["cve_id"] for signal in signals] == ["CVE-2026-1111"]
    assert signals[0].id == "cisa_kev:CVE-2026-1111"


@pytest.mark.asyncio
async def test_cisa_kev_adapter_handles_fetch_errors() -> None:
    adapter = CisaKevAdapter()

    async def mock_fetch(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        raise AdapterFetchError("cisa_kev", 503, url)

    with patch("max.sources.cisa_kev.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=5)

    assert signals == []


@pytest.mark.asyncio
async def test_cisa_kev_adapter_handles_bad_json() -> None:
    adapter = CisaKevAdapter()

    async def mock_fetch(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        response = MagicMock()
        response.json.side_effect = ValueError("bad json")
        return response

    with patch("max.sources.cisa_kev.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=5)

    assert signals == []


def test_cisa_kev_registry_registration_and_metadata() -> None:
    with patch("max.config.MAX_ADAPTERS", "cisa_kev"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()

        assert list_adapters() == ["cisa_kev"]
        assert get_adapter("cisa_kev").name == "cisa_kev"
        metadata = get_adapter_metadata()["cisa_kev"]

    assert metadata.config_keys == [
        "keywords",
        "vendors",
        "products",
        "max_age_days",
        "known_ransomware_campaign_use",
        "catalog_url",
    ]
    assert metadata.required_keys == []
    assert "CISA Known Exploited Vulnerabilities" in metadata.description

    reload_registry()
