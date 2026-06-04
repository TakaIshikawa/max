from __future__ import annotations

import pytest

from max.sources.github_security_lab_blog import GitHubSecurityLabBlogAdapter, parse_github_security_lab_blog
from max.sources.registry import get_adapter_class
from max.types.signal import SignalSourceType


def test_github_security_lab_blog_preserves_cves_dates_and_stable_ids() -> None:
    signals = parse_github_security_lab_blog(
        [
            {
                "title": "Variant analysis for CVE-2026-1234",
                "link": "https://github.blog/security-lab/2026/05/01/example/?utm_source=x",
                "summary": "Security research details.",
                "published_at": "2026-05-01T10:30:00Z",
                "cve_ids": ["cve-2026-1234", "CVE-2026-9999"],
                "categories": ["CodeQL", "Security"],
            },
            {"title": "Missing URL"},
            {"url": "https://github.blog/security-lab/missing-title"},
        ]
    )

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id.startswith("github_security_lab_blog:")
    assert signal.source_type == SignalSourceType.SECURITY
    assert signal.url == "https://github.blog/security-lab/2026/05/01/example"
    assert signal.published_at is not None
    assert signal.published_at.isoformat() == "2026-05-01T10:30:00+00:00"
    assert signal.metadata["canonical_url"] == signal.url
    assert signal.metadata["cve_ids"] == ["CVE-2026-1234", "CVE-2026-9999"]
    assert "CVE-2026-1234" in signal.tags
    assert "CodeQL" in signal.tags


def test_github_security_lab_blog_limit_and_article_fallback() -> None:
    signals = parse_github_security_lab_blog(
        [
            {"title": "Research recap", "url": "https://github.blog/security-lab/a", "summary": "General secure development notes."},
            {"title": "Second recap", "url": "https://github.blog/security-lab/b"},
        ],
        limit=1,
    )

    assert len(signals) == 1
    assert signals[0].source_type == SignalSourceType.ARTICLE
    assert signals[0].content == "General secure development notes."


@pytest.mark.asyncio
async def test_github_security_lab_blog_fetch_reads_configured_entries() -> None:
    adapter = GitHubSecurityLabBlogAdapter(config={"entries": [{"title": "A", "url": "https://github.blog/security-lab/a"}]})

    signals = await adapter.fetch(limit=5)

    assert [signal.title for signal in signals] == ["A"]


def test_github_security_lab_blog_registry_fallback_mapping() -> None:
    assert get_adapter_class("github_security_lab_blog") is GitHubSecurityLabBlogAdapter
