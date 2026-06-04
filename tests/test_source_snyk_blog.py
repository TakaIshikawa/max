from __future__ import annotations

from max.sources.snyk_blog import parse_snyk_blog
from max.types.signal import SignalSourceType


def test_snyk_blog_parses_security_tags_and_summary() -> None:
    signals = parse_snyk_blog([{"title": "Supply chain risk", "url": "https://snyk.io/blog/a", "summary": "Package provenance matters.", "category": "Open Source Security"}])

    assert signals[0].source_type == SignalSourceType.SECURITY
    assert signals[0].content == "Package provenance matters."
    assert {"snyk", "security", "supply-chain"}.issubset(signals[0].tags)


def test_snyk_blog_date_normalization_and_invalid_items() -> None:
    signals = parse_snyk_blog([{"title": "Dated", "url": "https://snyk.io/blog/date", "date": "2026-05-03T00:00:00Z"}, {"title": "no url"}])

    assert len(signals) == 1
    assert signals[0].published_at is not None
