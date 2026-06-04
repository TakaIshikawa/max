from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from max.sources.aws_security_blog import AwsSecurityBlogAdapter, parse_aws_security_blog
from max.sources.registry import get_adapter_class
from max.types.signal import SignalSourceType


RSS_FEED = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <item>
      <title>AWS IAM Access Analyzer adds policy checks</title>
      <link>https://aws.amazon.com/blogs/security/iam-access-analyzer-policy-checks/?utm_source=feed</link>
      <description><![CDATA[<p>Validate security policies before deployment.</p>]]></description>
      <pubDate>Mon, 01 Jun 2026 10:30:00 GMT</pubDate>
      <category>Identity</category>
      <category>Security</category>
      <guid>https://aws.amazon.com/blogs/security/iam-access-analyzer-policy-checks/</guid>
    </item>
    <item>
      <description>Missing title and URL.</description>
    </item>
  </channel>
</rss>
"""


def test_parse_aws_security_blog_converts_entries_to_security_signals() -> None:
    signals = parse_aws_security_blog(
        {
            "entries": [
                {
                    "title": "Threat detection with Amazon GuardDuty",
                    "url": "https://aws.amazon.com/blogs/security/guardduty-threat-detection/",
                    "summary": "Detection guidance for cloud workloads.",
                    "published_at": "2026-06-01T10:30:00Z",
                    "author": "AWS Security",
                    "categories": ["Threat Detection", "Security"],
                }
            ]
        }
    )

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id.startswith("aws_security_blog:")
    assert signal.source_type == SignalSourceType.SECURITY
    assert signal.source_adapter == "aws_security_blog"
    assert signal.title == "Threat detection with Amazon GuardDuty"
    assert signal.content == "Detection guidance for cloud workloads."
    assert signal.url == "https://aws.amazon.com/blogs/security/guardduty-threat-detection"
    assert signal.published_at is not None
    assert signal.published_at.isoformat() == "2026-06-01T10:30:00+00:00"
    assert signal.author == "AWS Security"
    assert {"aws", "security", "cloud-security", "Threat Detection"}.issubset(signal.tags)
    assert signal.metadata["source_name"] == "AWS Security Blog"
    assert signal.metadata["canonical_url"] == signal.url
    assert signal.metadata["categories"] == ["Threat Detection", "Security"]


def test_parse_aws_security_blog_skips_empty_and_malformed_entries() -> None:
    assert parse_aws_security_blog(None) == []
    assert parse_aws_security_blog([None, "bad", {"title": "No URL"}, {"url": "https://aws.amazon.com/blogs/security/no-title/"}]) == []


def test_parse_aws_security_blog_accepts_rss_feed_text_and_limit() -> None:
    signals = parse_aws_security_blog(RSS_FEED, limit=1, feed_url="https://example.test/feed.xml")

    assert len(signals) == 1
    signal = signals[0]
    assert signal.title == "AWS IAM Access Analyzer adds policy checks"
    assert signal.content == "Validate security policies before deployment."
    assert signal.url == "https://aws.amazon.com/blogs/security/iam-access-analyzer-policy-checks"
    assert signal.published_at is not None
    assert "Identity" in signal.tags
    assert signal.metadata["feed_url"] == "https://example.test/feed.xml"


@pytest.mark.asyncio
async def test_aws_security_blog_fetch_reads_configured_entries() -> None:
    adapter = AwsSecurityBlogAdapter(config={"entries": [{"title": "A", "url": "https://aws.amazon.com/blogs/security/a"}]})

    signals = await adapter.fetch(limit=5)

    assert [signal.title for signal in signals] == ["A"]


@pytest.mark.asyncio
async def test_aws_security_blog_fetch_uses_feed_url_when_no_payload() -> None:
    adapter = AwsSecurityBlogAdapter(config={"feed_url": "https://example.test/security.xml"})
    response = MagicMock(text=RSS_FEED)

    async def mock_fetch_with_retry(url: str, client, *, adapter_name: str):
        assert url == "https://example.test/security.xml"
        assert adapter_name == "aws_security_blog"
        return response

    with patch("max.sources.aws_security_blog.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=5)

    assert [signal.title for signal in signals] == ["AWS IAM Access Analyzer adds policy checks"]


def test_aws_security_blog_registry_fallback_mapping() -> None:
    assert get_adapter_class("aws_security_blog") is AwsSecurityBlogAdapter
