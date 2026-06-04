from __future__ import annotations

from max.sources.semgrep_blog import parse_semgrep_blog
from max.types.signal import SignalSourceType


def test_semgrep_blog_successful_parsing() -> None:
    signals = parse_semgrep_blog([{"title": "Secure defaults", "url": "https://semgrep.dev/blog/a", "summary": "Safer rules."}])

    assert signals[0].source_type == SignalSourceType.SECURITY
    assert signals[0].source_adapter == "semgrep_blog"


def test_semgrep_blog_category_tag_extraction() -> None:
    signal = parse_semgrep_blog([{"title": "SAST update", "url": "https://semgrep.dev/blog/b", "category": "SAST"}])[0]

    assert {"semgrep", "application-security", "devtools", "sast"}.issubset(signal.tags)


def test_semgrep_blog_malformed_entries() -> None:
    assert parse_semgrep_blog([{"url": "https://semgrep.dev/blog/no-title"}, None]) == []
