from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from max.sources.gitlab_blog import GitLabBlogAdapter, parse_gitlab_blog
from max.sources.registry import get_adapter_class
from max.types.signal import SignalSourceType


ATOM_FEED = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>GitLab 18.0 released</title>
    <link href="https://about.gitlab.com/releases/2026/05/15/gitlab-18-0-released/"/>
    <summary>Release announcement with DevSecOps improvements.</summary>
    <published>2026-05-15T12:00:00Z</published>
    <author><name>Jane Doe</name></author>
    <category term="releases"/>
  </entry>
</feed>
"""


def test_parse_gitlab_blog_normalizes_feed_entries() -> None:
    signals = parse_gitlab_blog({"entries": [{"title": "GitLab Duo update", "url": "https://about.gitlab.com/blog/duo/", "summary": "AI workflow news", "published_at": "2026-05-01T00:00:00Z", "author": "Alex", "categories": ["AI", "releases"]}]})

    assert len(signals) == 1
    signal = signals[0]
    assert signal.source_type == SignalSourceType.NEWS
    assert signal.source_adapter == "gitlab_blog"
    assert signal.title == "GitLab Duo update"
    assert signal.url == "https://about.gitlab.com/blog/duo"
    assert signal.content == "AI workflow news"
    assert signal.published_at is not None
    assert signal.author == "Alex"
    assert signal.tags == ["gitlab", "AI", "releases"]
    assert signal.metadata["author"] == "Alex"
    assert signal.metadata["categories"] == ["AI", "releases"]


def test_parse_gitlab_blog_accepts_atom_fixture() -> None:
    signals = parse_gitlab_blog(ATOM_FEED)

    assert len(signals) == 1
    assert signals[0].title == "GitLab 18.0 released"
    assert signals[0].url == "https://about.gitlab.com/releases/2026/05/15/gitlab-18-0-released"
    assert "releases" in signals[0].tags


@pytest.mark.asyncio
async def test_gitlab_blog_fetch_reads_configured_payload() -> None:
    adapter = GitLabBlogAdapter(config={"entries": [{"title": "A", "url": "https://about.gitlab.com/blog/a"}]})

    signals = await adapter.fetch(limit=5)

    assert [signal.title for signal in signals] == ["A"]


@pytest.mark.asyncio
async def test_gitlab_blog_fetch_uses_feed_url_when_no_payload() -> None:
    adapter = GitLabBlogAdapter(config={"feed_url": "https://example.test/feed.xml"})
    response = MagicMock(text=ATOM_FEED)

    async def mock_fetch_with_retry(url: str, client, *, adapter_name: str):
        assert url == "https://example.test/feed.xml"
        assert adapter_name == "gitlab_blog"
        return response

    with patch("max.sources.gitlab_blog.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=5)

    assert signals[0].title == "GitLab 18.0 released"


def test_gitlab_blog_registry_fallback_mapping() -> None:
    assert get_adapter_class("gitlab_blog") is GitLabBlogAdapter
