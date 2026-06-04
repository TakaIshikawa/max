from __future__ import annotations

from max.sources.github_changelog import GitHubChangelogAdapter, parse_github_changelog
from max.types.signal import SignalSourceType


def test_github_changelog_is_distinct_from_blog_adapter() -> None:
    adapter = GitHubChangelogAdapter()

    assert adapter.name == "github_changelog"
    assert adapter.name != "github_blog"


def test_github_changelog_captures_product_tags() -> None:
    signals = parse_github_changelog([{"title": "Actions update", "url": "https://github.blog/changelog/a", "product": "Actions"}])

    assert signals[0].source_type == SignalSourceType.ROADMAP
    assert signals[0].metadata["product"] == "Actions"
    assert {"github", "product", "platform"}.issubset(signals[0].tags)


def test_github_changelog_empty_feeds() -> None:
    assert parse_github_changelog({"entries": []}) == []
