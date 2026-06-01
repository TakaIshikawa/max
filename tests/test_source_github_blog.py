from __future__ import annotations

from max.sources.github_blog import parse_github_blog
from max.types.signal import SignalSourceType


def test_github_blog_category_author_date_and_canonical_url() -> None:
    signals = parse_github_blog([{"title": "Engineering post", "url": "https://github.blog/engineering/a", "author": "octo", "category": "engineering", "date": "2026-03-01T00:00:00Z"}])
    assert signals[0].source_type == SignalSourceType.ARTICLE
    assert signals[0].author == "octo"
    assert signals[0].metadata["category"] == "engineering"
    assert signals[0].url == "https://github.blog/engineering/a"


def test_github_blog_handles_absent_author_category() -> None:
    signal = parse_github_blog([{"title": "A", "url": "https://github.blog/a"}])[0]
    assert signal.author is None
    assert signal.title == "A"


def test_github_blog_stable_ids_and_empty_feeds() -> None:
    payload = [{"title": "A", "url": "https://github.blog/a"}]
    assert parse_github_blog(payload)[0].id == parse_github_blog(payload)[0].id
    assert parse_github_blog(None) == []
