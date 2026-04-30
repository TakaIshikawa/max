"""Tests for the RustSec advisory source adapter."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from unittest.mock import MagicMock, patch

import httpx
import pytest

from max.sources.rustsec_advisories import (
    RUSTSEC_OSV_ARCHIVE_URL,
    RustSecAdvisoriesAdapter,
    parse_rustsec_advisories,
)
from max.types.signal import SignalSourceType


RUSTSEC_HIGH = {
    "id": "RUSTSEC-2026-0001",
    "summary": "Memory safety issue in example-crate",
    "details": "A crafted input can trigger memory unsafety in example-crate.",
    "aliases": ["CVE-2026-12345"],
    "published": "2026-04-01T00:00:00Z",
    "modified": "2026-04-10T00:00:00Z",
    "database_specific": {
        "severity": "HIGH",
        "categories": ["memory-corruption"],
        "keywords": ["unsafe"],
    },
    "affected": [
        {
            "package": {"name": "example-crate", "ecosystem": "crates.io"},
            "ranges": [
                {
                    "type": "ECOSYSTEM",
                    "events": [{"introduced": "0"}, {"fixed": "1.2.3"}],
                }
            ],
        }
    ],
    "references": [
        {"type": "ADVISORY", "url": "https://rustsec.org/advisories/RUSTSEC-2026-0001"},
    ],
}

RUSTSEC_LOW = {
    "id": "RUSTSEC-2026-0002",
    "summary": "Low risk issue in helper-crate",
    "details": "A low risk issue.",
    "database_specific": {"severity": "LOW"},
    "affected": [{"package": {"name": "helper-crate", "ecosystem": "crates.io"}}],
}


def _zip_bytes(files: dict[str, str]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def test_rustsec_adapter_properties_and_config() -> None:
    adapter = RustSecAdvisoriesAdapter(
        config={
            "index_url": "https://example.test/rustsec.zip",
            "base_url": "https://example.test/advisories",
            "packages": ["example-crate"],
            "severity_min": "high",
            "max_items": "5",
        }
    )

    assert adapter.name == "rustsec_advisories"
    assert adapter.source_type == SignalSourceType.SECURITY.value
    assert adapter.index_url == "https://example.test/rustsec.zip"
    assert adapter.base_url == "https://example.test/advisories"
    assert adapter.packages == ["example-crate"]
    assert adapter.severity_min == "high"
    assert adapter.max_items == 5


def test_parse_rustsec_osv_records_maps_security_signal_fields() -> None:
    signals = parse_rustsec_advisories([RUSTSEC_HIGH], limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "rustsec_advisories:RUSTSEC-2026-0001"
    assert signal.source_type == SignalSourceType.SECURITY
    assert signal.source_adapter == "rustsec_advisories"
    assert signal.title.startswith("RustSec RUSTSEC-2026-0001 [HIGH]")
    assert signal.url == "https://rustsec.org/advisories/RUSTSEC-2026-0001"
    assert signal.published_at is not None
    assert "security" in signal.tags
    assert "rust" in signal.tags
    assert "example-crate" in signal.tags
    assert "high" in signal.tags
    assert signal.metadata["rustsec_id"] == "RUSTSEC-2026-0001"
    assert signal.metadata["advisory_id"] == "RUSTSEC-2026-0001"
    assert signal.metadata["affected_crate"] == "example-crate"
    assert signal.metadata["patched_versions"] == [">= 1.2.3"]
    assert signal.metadata["severity"] == "high"
    assert signal.metadata["cve_ids"] == ["CVE-2026-12345"]
    assert signal.metadata["source_catalog"] == "rustsec"
    assert signal.metadata["signal_role"] == "problem"
    assert "Patched versions: >= 1.2.3" in signal.content


def test_parse_rustsec_records_filters_by_package_severity_limit_and_deduplicates() -> None:
    signals = parse_rustsec_advisories(
        [RUSTSEC_LOW, RUSTSEC_HIGH, RUSTSEC_HIGH],
        packages=["example-crate"],
        severity_min="high",
        limit=1,
    )

    assert [signal.metadata["rustsec_id"] for signal in signals] == ["RUSTSEC-2026-0001"]


def test_parse_rustsec_records_skips_malformed_records_with_logging(caplog: pytest.LogCaptureFixture) -> None:
    malformed = {"id": "RUSTSEC-2026-9999", "summary": "missing affected crate"}

    signals = parse_rustsec_advisories([malformed, RUSTSEC_HIGH], limit=10)

    assert [signal.metadata["rustsec_id"] for signal in signals] == ["RUSTSEC-2026-0001"]
    assert "skipping malformed RustSec advisory record" in caplog.text


@pytest.mark.asyncio
async def test_rustsec_adapter_fetches_json_index_with_mocked_http() -> None:
    adapter = RustSecAdvisoriesAdapter(config={"max_items": 10})
    requests: list[dict] = []

    async def mock_fetch(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        requests.append({"url": url, **kwargs})
        return MagicMock(json=lambda: {"advisories": [RUSTSEC_HIGH, RUSTSEC_LOW]})

    with patch("max.sources.rustsec_advisories.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=1)

    assert requests[0]["url"] == RUSTSEC_OSV_ARCHIVE_URL
    assert requests[0]["adapter_name"] == "rustsec_advisories"
    assert [signal.metadata["rustsec_id"] for signal in signals] == ["RUSTSEC-2026-0001"]


@pytest.mark.asyncio
async def test_rustsec_adapter_fetches_zip_archive_and_skips_bad_members(
    caplog: pytest.LogCaptureFixture,
) -> None:
    adapter = RustSecAdvisoriesAdapter(config={"index_url": "https://example.test/rustsec.zip"})
    archive = _zip_bytes(
        {
            "advisory-db-osv/RUSTSEC-2026-0001.json": json.dumps(RUSTSEC_HIGH),
            "advisory-db-osv/bad.json": "{bad json",
        }
    )

    async def mock_fetch(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        response = MagicMock()
        response.json.side_effect = ValueError("not json")
        response.content = archive
        return response

    with patch("max.sources.rustsec_advisories.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=5)

    assert [signal.metadata["rustsec_id"] for signal in signals] == ["RUSTSEC-2026-0001"]
    assert "skipping malformed advisory" in caplog.text


@pytest.mark.asyncio
async def test_rustsec_adapter_fetches_toml_archive_members() -> None:
    adapter = RustSecAdvisoriesAdapter(config={"index_url": "https://example.test/rustsec.zip"})
    archive = _zip_bytes(
        {
            "advisory-db-main/crates/example/RUSTSEC-2026-0003.md": """
[advisory]
id = "RUSTSEC-2026-0003"
package = "toml-crate"
date = "2026-04-02"
url = "https://rustsec.org/advisories/RUSTSEC-2026-0003"
aliases = ["CVE-2026-33333"]
cvss = "9.8"
categories = ["code-execution"]

[versions]
patched = [">= 2.0.0"]

# Description
""",
        }
    )

    async def mock_fetch(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        response = MagicMock()
        response.json.side_effect = ValueError("not json")
        response.content = archive
        return response

    with patch("max.sources.rustsec_advisories.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=5)

    assert [signal.metadata["rustsec_id"] for signal in signals] == ["RUSTSEC-2026-0003"]
    assert signals[0].metadata["affected_crate"] == "toml-crate"
    assert signals[0].metadata["patched_versions"] == [">= 2.0.0"]
    assert signals[0].metadata["severity"] == "critical"
