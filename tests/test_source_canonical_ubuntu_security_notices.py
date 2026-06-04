from __future__ import annotations

import pytest

from max.sources.canonical_ubuntu_security_notices import (
    CanonicalUbuntuSecurityNoticesAdapter,
    parse_canonical_ubuntu_security_notices,
)
from max.types.signal import SignalSourceType


def test_notice_parsing_extracts_advisory_and_packages() -> None:
    signals = parse_canonical_ubuntu_security_notices(
        [{"advisory_id": "USN-9999-1", "title": "openssl vulnerabilities", "url": "https://ubuntu.com/security/notices/USN-9999-1", "affected_packages": ["openssl", "libssl"], "published_at": "2026-05-02T00:00:00Z"}]
    )

    assert signals[0].source_type == SignalSourceType.SECURITY
    assert signals[0].metadata["advisory_id"] == "USN-9999-1"
    assert signals[0].metadata["affected_packages"] == ["openssl", "libssl"]
    assert "openssl" in signals[0].tags


def test_notice_parser_ignores_malformed_entries() -> None:
    assert parse_canonical_ubuntu_security_notices([{"advisory_id": "USN-1"}, {"url": "https://ubuntu.com"}, None]) == []


@pytest.mark.asyncio
async def test_notice_adapter_fetch_uses_payload() -> None:
    signals = await CanonicalUbuntuSecurityNoticesAdapter(config={"payload": [{"id": "USN-1", "url": "https://ubuntu.com/1"}]}).fetch()

    assert [signal.title for signal in signals] == ["USN-1"]
