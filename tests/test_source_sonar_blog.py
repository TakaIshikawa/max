from __future__ import annotations

import pytest

from max.sources.sonar_blog import SonarBlogAdapter, parse_sonar_blog
from max.types.signal import SignalSourceType


def test_sonar_blog_parses_code_quality_tags() -> None:
    signals = parse_sonar_blog([{"title": "Static analysis updates", "url": "https://sonarsource.com/blog/a", "summary": "Rules improved.", "category": "Code Quality", "date": "2026-05-01T00:00:00Z"}])

    assert signals[0].source_adapter == "sonar_blog"
    assert signals[0].source_type == SignalSourceType.ARTICLE
    assert {"sonar", "code-quality", "static-analysis"}.issubset(signals[0].tags)
    assert signals[0].published_at is not None


def test_sonar_blog_skips_malformed_entries() -> None:
    assert parse_sonar_blog([{"title": "missing url"}, "bad", {"url": "https://example.com"}]) == []


@pytest.mark.asyncio
async def test_sonar_blog_adapter_fetch_uses_configured_payload() -> None:
    signals = await SonarBlogAdapter(config={"entries": [{"title": "A", "url": "https://sonar/a"}]}).fetch()

    assert [signal.title for signal in signals] == ["A"]
