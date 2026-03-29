"""Tests for source adapters with mocked HTTP responses."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.github_issues import GitHubIssuesAdapter, _build_tags as _gh_build_tags
from max.sources.hackernews import HackerNewsAdapter, _extract_tags
from max.sources.npm_registry import NpmRegistryAdapter
from max.sources.product_hunt import ProductHuntAdapter, _extract_posts
from max.sources.pypi_registry import (
    PyPIRegistryAdapter,
    _matches_ai_keywords,
    _parse_rss,
)
from max.sources.registry import get_adapter, get_all_adapters, list_adapters
from max.sources.security_advisories import SecurityAdvisoriesAdapter


# ── HackerNews ───────────────────────────────────────────────────────


def _mock_hn_item(story_id: int, title: str, score: int = 100) -> dict:
    return {
        "id": story_id,
        "type": "story",
        "title": title,
        "url": f"https://example.com/{story_id}",
        "by": "testuser",
        "time": 1711000000,
        "score": score,
        "descendants": 50,
    }


@pytest.mark.asyncio
async def test_hackernews_fetch_parses_stories() -> None:
    adapter = HackerNewsAdapter()

    mock_responses = {
        "topstories.json": MagicMock(
            json=lambda: [101, 102, 103],
            raise_for_status=lambda: None,
        ),
        "item/101.json": MagicMock(
            json=lambda: _mock_hn_item(101, "Show HN: AI Agent Testing Framework"),
            raise_for_status=lambda: None,
        ),
        "item/102.json": MagicMock(
            json=lambda: _mock_hn_item(102, "MCP Server Security Audit Results", score=400),
            raise_for_status=lambda: None,
        ),
        "item/103.json": MagicMock(
            json=lambda: _mock_hn_item(103, "Rust Package Manager Update"),
            raise_for_status=lambda: None,
        ),
    }

    async def mock_get(url: str) -> MagicMock:
        for key, resp in mock_responses.items():
            if url.endswith(key):
                return resp
        raise ValueError(f"Unexpected URL: {url}")

    with patch("max.sources.hackernews.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        signals = await adapter.fetch(limit=3)

    assert len(signals) == 3
    assert signals[0].title == "Show HN: AI Agent Testing Framework"
    assert signals[0].source_adapter == "hackernews"
    assert signals[0].source_type.value == "forum"
    assert signals[0].author == "testuser"
    assert signals[0].metadata["hn_id"] == 101

    # Score-based credibility
    assert signals[1].credibility == 400 / 500  # 0.8
    assert signals[0].credibility == 100 / 500  # 0.2


@pytest.mark.asyncio
async def test_hackernews_skips_non_story_items() -> None:
    adapter = HackerNewsAdapter()

    mock_responses = {
        "topstories.json": MagicMock(
            json=lambda: [201],
            raise_for_status=lambda: None,
        ),
        "item/201.json": MagicMock(
            json=lambda: {"id": 201, "type": "comment", "text": "just a comment"},
            raise_for_status=lambda: None,
        ),
    }

    async def mock_get(url: str) -> MagicMock:
        for key, resp in mock_responses.items():
            if url.endswith(key):
                return resp
        raise ValueError(f"Unexpected URL: {url}")

    with patch("max.sources.hackernews.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 0


def test_extract_tags_ai() -> None:
    assert "ai" in _extract_tags("New Claude AI model released")
    assert "ai" in _extract_tags("LLM benchmarks for 2026")


def test_extract_tags_mcp() -> None:
    assert "mcp" in _extract_tags("MCP server for database access")


def test_extract_tags_multiple() -> None:
    tags = _extract_tags("Python AI Agent Security Vulnerability")
    assert "python" in tags
    assert "ai" in tags
    assert "agent" in tags
    assert "security" in tags


def test_extract_tags_no_match() -> None:
    assert _extract_tags("random unrelated title") == []


# ── npm registry ─────────────────────────────────────────────────────


def _mock_npm_response(packages: list[dict]) -> dict:
    return {
        "objects": [
            {
                "package": pkg,
                "searchScore": pkg.get("_score", 50000),
            }
            for pkg in packages
        ]
    }


@pytest.mark.asyncio
async def test_npm_fetch_parses_packages() -> None:
    adapter = NpmRegistryAdapter()

    mock_data = _mock_npm_response([
        {
            "name": "@test/mcp-server",
            "description": "An MCP server for testing",
            "version": "1.0.0",
            "date": "2026-03-20T00:00:00Z",
            "publisher": {"username": "testpublisher"},
            "keywords": ["mcp", "server"],
            "_score": 80000,
        },
    ])

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: mock_data,
            raise_for_status=lambda: None,
        )

    with patch("max.sources.npm_registry.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        signals = await adapter.fetch(limit=5)

    assert len(signals) >= 1
    first = signals[0]
    assert first.title == "@test/mcp-server@1.0.0"
    assert first.source_adapter == "npm_registry"
    assert first.source_type.value == "registry"
    assert first.author == "testpublisher"
    assert first.metadata["npm_name"] == "@test/mcp-server"
    assert first.credibility == 80000 / 100_000


@pytest.mark.asyncio
async def test_npm_respects_limit() -> None:
    adapter = NpmRegistryAdapter()

    # Return many packages per query
    many_pkgs = [
        {"name": f"pkg-{i}", "description": f"Package {i}", "version": "1.0.0"}
        for i in range(20)
    ]
    mock_data = _mock_npm_response(many_pkgs)

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: mock_data,
            raise_for_status=lambda: None,
        )

    with patch("max.sources.npm_registry.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        signals = await adapter.fetch(limit=3)

    assert len(signals) <= 3


# ── Registry ─────────────────────────────────────────────────────────


def test_list_adapters() -> None:
    adapters = list_adapters()
    assert "hackernews" in adapters
    assert "npm_registry" in adapters


def test_get_adapter() -> None:
    adapter = get_adapter("hackernews")
    assert adapter.name == "hackernews"


def test_get_adapter_unknown() -> None:
    with pytest.raises(KeyError, match="Unknown adapter"):
        get_adapter("nonexistent")


def test_get_all_adapters() -> None:
    adapters = get_all_adapters()
    assert len(adapters) >= 2
    names = {a.name for a in adapters}
    assert "hackernews" in names
    assert "npm_registry" in names


# ── PyPI Registry ────────────────────────────────────────────────────


MOCK_RSS_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>langchain-agent 0.2.0</title>
      <link>https://pypi.org/project/langchain-agent/0.2.0/</link>
      <pubDate>Sat, 29 Mar 2026 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>flask-utils 3.1.0</title>
      <link>https://pypi.org/project/flask-utils/3.1.0/</link>
      <pubDate>Sat, 29 Mar 2026 11:00:00 GMT</pubDate>
    </item>
    <item>
      <title>openai-helpers 1.0.0</title>
      <link>https://pypi.org/project/openai-helpers/1.0.0/</link>
      <pubDate>Sat, 29 Mar 2026 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

MOCK_PYPI_JSON = {
    "info": {
        "name": "langchain-agent",
        "version": "0.2.0",
        "summary": "AI agent framework built on LangChain",
        "author": "testdev",
        "classifiers": ["Topic :: Scientific/Engineering :: Artificial Intelligence"],
        "requires_python": ">=3.10",
        "package_url": "https://pypi.org/project/langchain-agent/",
        "project_urls": {"GitHub": "https://github.com/test/langchain-agent"},
        "keywords": "ai,agent,langchain",
    }
}

MOCK_PYPISTATS = {"data": {"last_week": 50000}}


def test_parse_rss_extracts_items() -> None:
    results = _parse_rss(MOCK_RSS_XML)
    assert len(results) == 3
    assert results[0][0] == "langchain-agent"
    assert "pypi.org" in results[0][1]
    assert results[0][2] is not None  # parsed date


def test_parse_rss_handles_invalid_xml() -> None:
    assert _parse_rss("not xml at all") == []


def test_matches_ai_keywords_positive() -> None:
    assert _matches_ai_keywords("langchain-agent")
    assert _matches_ai_keywords("openai-helpers")
    assert _matches_ai_keywords("mcp-server-utils")


def test_matches_ai_keywords_negative() -> None:
    assert not _matches_ai_keywords("flask-utils")
    assert not _matches_ai_keywords("django-rest")


@pytest.mark.asyncio
async def test_pypi_fetch_filters_and_enriches() -> None:
    adapter = PyPIRegistryAdapter()

    call_log: list[str] = []

    async def mock_get(url: str, **kwargs) -> MagicMock:
        call_log.append(url)
        if "rss" in url:
            return MagicMock(text=MOCK_RSS_XML, raise_for_status=lambda: None)
        if "pypi.org/pypi/" in url:
            return MagicMock(json=lambda: MOCK_PYPI_JSON, raise_for_status=lambda: None)
        if "pypistats.org" in url:
            return MagicMock(json=lambda: MOCK_PYPISTATS, raise_for_status=lambda: None)
        return MagicMock(raise_for_status=lambda: None, json=lambda: {}, text="")

    with patch("max.sources.pypi_registry.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=5)

    # Should filter out flask-utils (no AI keyword), keep langchain-agent and openai-helpers
    assert len(signals) >= 1
    names = {s.metadata["pypi_name"] for s in signals}
    assert "langchain-agent" in names
    assert "flask-utils" not in names

    # Check enrichment
    first = [s for s in signals if s.metadata["pypi_name"] == "langchain-agent"][0]
    assert first.source_type.value == "registry"
    assert first.source_adapter == "pypi_registry"
    assert first.author == "testdev"
    assert "python" in first.tags
    assert first.credibility == 50000 / 100_000  # 0.5


@pytest.mark.asyncio
async def test_pypi_pypistats_fallback_credibility() -> None:
    """When pypistats fails, credibility falls back to 0.3."""
    adapter = PyPIRegistryAdapter()

    async def mock_get(url: str, **kwargs) -> MagicMock:
        if "rss" in url:
            return MagicMock(text=MOCK_RSS_XML, raise_for_status=lambda: None)
        if "pypi.org/pypi/" in url:
            return MagicMock(json=lambda: MOCK_PYPI_JSON, raise_for_status=lambda: None)
        if "pypistats.org" in url:
            raise httpx.HTTPError("pypistats down")
        return MagicMock(raise_for_status=lambda: None, json=lambda: {}, text="")

    with patch("max.sources.pypi_registry.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=5)

    assert len(signals) >= 1
    assert signals[0].credibility == 0.3


# ── GitHub Issues ────────────────────────────────────────────────────


MOCK_ISSUES_RESPONSE = {
    "items": [
        {
            "id": 1001,
            "title": "AI Agent fails to handle tool errors gracefully",
            "html_url": "https://github.com/test/ai-framework/issues/42",
            "body": "When the agent calls a tool that returns an error, it crashes instead of retrying.",
            "user": {"login": "dev1"},
            "created_at": "2026-03-28T10:00:00Z",
            "state": "open",
            "labels": [{"name": "bug"}, {"name": "enhancement"}],
            "reactions": {"total_count": 25},
            "comments": 15,
        },
        {
            "id": 1002,
            "title": "Add MCP support for database queries",
            "html_url": "https://github.com/test/ai-framework/issues/43",
            "body": "We need an MCP server that can query SQL databases.",
            "user": {"login": "dev2"},
            "created_at": "2026-03-27T09:00:00Z",
            "state": "open",
            "labels": [{"name": "feature-request"}],
            "reactions": {"total_count": 50},
            "comments": 30,
        },
        {
            "id": 1003,
            "title": "Update README",
            "html_url": "https://github.com/test/ai-framework/pulls/44",
            "body": "Just a PR",
            "pull_request": {"url": "https://api.github.com/..."},
            "user": {"login": "dev3"},
            "created_at": "2026-03-26T08:00:00Z",
            "state": "open",
            "labels": [],
            "reactions": {"total_count": 0},
            "comments": 1,
        },
    ]
}


@pytest.mark.asyncio
async def test_github_issues_fetch_parses_and_filters_prs() -> None:
    adapter = GitHubIssuesAdapter()

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: MOCK_ISSUES_RESPONSE,
            raise_for_status=lambda: None,
        )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls, \
         patch("max.sources.github_issues.asyncio.sleep", new_callable=AsyncMock):
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    # PR (id=1003) should be filtered out
    ids = {s.metadata["github_issue_id"] for s in signals}
    assert 1003 not in ids
    assert 1001 in ids
    assert 1002 in ids

    first = [s for s in signals if s.metadata["github_issue_id"] == 1001][0]
    assert first.source_type.value == "forum"
    assert first.source_adapter == "github_issues"
    assert first.credibility == (25 + 15) / 100  # 0.4
    assert first.metadata["repo"] == "test/ai-framework"
    assert "bug" in first.tags


@pytest.mark.asyncio
async def test_github_issues_deduplicates_by_url() -> None:
    """Same issue returned by multiple queries is deduplicated."""
    adapter = GitHubIssuesAdapter()

    # All queries return the same item
    single_issue = {
        "items": [MOCK_ISSUES_RESPONSE["items"][0]]
    }

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: single_issue,
            raise_for_status=lambda: None,
        )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls, \
         patch("max.sources.github_issues.asyncio.sleep", new_callable=AsyncMock):
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=30)

    # Despite 4 queries returning the same issue, should appear once
    assert len(signals) == 1


def test_github_issues_build_tags() -> None:
    tags = _gh_build_tags(["bug", "enhancement"], "AI Agent MCP integration")
    assert "bug" in tags
    assert "enhancement" in tags
    assert "ai" in tags
    assert "agent" in tags
    assert "mcp" in tags


# ── Security Advisories ──────────────────────────────────────────────


MOCK_ADVISORIES = [
    {
        "ghsa_id": "GHSA-0001",
        "cve_id": "CVE-2026-0001",
        "severity": "critical",
        "summary": "Remote code execution in ai-framework",
        "description": "A critical RCE vulnerability was found in ai-framework.",
        "html_url": "https://github.com/advisories/GHSA-0001",
        "published_at": "2026-03-28T00:00:00Z",
        "withdrawn_at": None,
        "cvss": {"score": 9.8, "vector_string": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"},
        "cwes": [{"cwe_id": "CWE-94"}],
        "vulnerabilities": [
            {"package": {"name": "ai-framework", "ecosystem": "pip"}}
        ],
    },
    {
        "ghsa_id": "GHSA-0002",
        "cve_id": "CVE-2026-0002",
        "severity": "high",
        "summary": "XSS in dashboard",
        "description": "Reflected XSS via user input.",
        "html_url": "https://github.com/advisories/GHSA-0002",
        "published_at": "2026-03-27T00:00:00Z",
        "withdrawn_at": None,
        "cvss": {"score": 7.5, "vector_string": "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:H/I:N/A:N"},
        "cwes": [{"cwe_id": "CWE-79"}],
        "vulnerabilities": [
            {"package": {"name": "dashboard-lib", "ecosystem": "npm"}}
        ],
    },
    {
        "ghsa_id": "GHSA-0003",
        "cve_id": None,
        "severity": "high",
        "summary": "Withdrawn advisory",
        "description": "This was withdrawn.",
        "html_url": "https://github.com/advisories/GHSA-0003",
        "published_at": "2026-03-26T00:00:00Z",
        "withdrawn_at": "2026-03-27T00:00:00Z",
        "cvss": {"score": 8.0},
        "cwes": [],
        "vulnerabilities": [],
    },
]


@pytest.mark.asyncio
async def test_security_fetch_parses_and_skips_withdrawn() -> None:
    adapter = SecurityAdvisoriesAdapter()

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: MOCK_ADVISORIES,
            raise_for_status=lambda: None,
        )

    with patch("max.sources.security_advisories.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=30)

    # GHSA-0003 is withdrawn → skipped
    ghsa_ids = {s.metadata["ghsa_id"] for s in signals}
    assert "GHSA-0003" not in ghsa_ids
    assert "GHSA-0001" in ghsa_ids
    assert "GHSA-0002" in ghsa_ids

    first = [s for s in signals if s.metadata["ghsa_id"] == "GHSA-0001"][0]
    assert first.source_type.value == "security"
    assert first.source_adapter == "security_advisories"
    assert first.credibility == 9.8 / 10.0  # 0.98
    assert first.metadata["cve_id"] == "CVE-2026-0001"
    assert "ai-framework" in first.metadata["affected_packages"]
    assert "security" in first.tags
    assert "critical" in first.tags
    assert "code-injection" in first.tags  # CWE-94


@pytest.mark.asyncio
async def test_security_cvss_credibility() -> None:
    """CVSS score maps to credibility correctly."""
    adapter = SecurityAdvisoriesAdapter()

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: MOCK_ADVISORIES,
            raise_for_status=lambda: None,
        )

    with patch("max.sources.security_advisories.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=30)

    xss = [s for s in signals if s.metadata["ghsa_id"] == "GHSA-0002"][0]
    assert xss.credibility == 7.5 / 10.0  # 0.75
    assert "xss" in xss.tags  # CWE-79


@pytest.mark.asyncio
async def test_security_ecosystem_tags() -> None:
    """Ecosystem maps to language tags."""
    adapter = SecurityAdvisoriesAdapter()

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: MOCK_ADVISORIES[:1],  # just the pip one
            raise_for_status=lambda: None,
        )

    with patch("max.sources.security_advisories.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=5)

    assert len(signals) >= 1
    assert "python" in signals[0].tags


# ── Product Hunt ─────────────────────────────────────────────────────


MOCK_PH_RESPONSE = {
    "data": {
        "topic": {
            "posts": {
                "edges": [
                    {
                        "node": {
                            "id": "ph-001",
                            "name": "AgentForge",
                            "tagline": "Build AI agents in minutes",
                            "description": "A platform for building and deploying AI agents.",
                            "url": "https://www.producthunt.com/posts/agentforge",
                            "votesCount": 300,
                            "commentsCount": 45,
                            "createdAt": "2026-03-28T12:00:00Z",
                            "makers": [{"username": "maker1"}],
                            "topics": {
                                "edges": [
                                    {"node": {"slug": "artificial-intelligence", "name": "AI"}},
                                    {"node": {"slug": "developer-tools", "name": "Dev Tools"}},
                                ]
                            },
                        }
                    },
                    {
                        "node": {
                            "id": "ph-002",
                            "name": "DevDash",
                            "tagline": "Developer productivity dashboard",
                            "description": "Track your dev metrics.",
                            "url": "https://www.producthunt.com/posts/devdash",
                            "votesCount": 600,
                            "commentsCount": 80,
                            "createdAt": "2026-03-27T12:00:00Z",
                            "makers": [{"username": "maker2"}],
                            "topics": {
                                "edges": [
                                    {"node": {"slug": "developer-tools", "name": "Dev Tools"}},
                                ]
                            },
                        }
                    },
                ]
            }
        }
    }
}


@pytest.mark.asyncio
async def test_product_hunt_no_token_returns_empty() -> None:
    """Without PRODUCT_HUNT_TOKEN, adapter returns empty list."""
    adapter = ProductHuntAdapter()

    with patch.dict("os.environ", {}, clear=True):
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_product_hunt_fetch_parses_posts() -> None:
    adapter = ProductHuntAdapter()

    async def mock_post(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: MOCK_PH_RESPONSE,
            raise_for_status=lambda: None,
        )

    with patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "test-token"}), \
         patch("max.sources.product_hunt.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) >= 2
    first = [s for s in signals if s.metadata["ph_id"] == "ph-001"][0]
    assert first.source_type.value == "trending"
    assert first.source_adapter == "product_hunt"
    assert first.title == "AgentForge"
    assert first.credibility == 300 / 500  # 0.6
    assert "ai" in first.tags
    assert "devtools" in first.tags
    assert first.metadata["makers"] == ["maker1"]

    second = [s for s in signals if s.metadata["ph_id"] == "ph-002"][0]
    assert second.credibility == 1.0  # 600/500 capped at 1.0


@pytest.mark.asyncio
async def test_product_hunt_deduplicates_across_topics() -> None:
    """Same post in multiple topic queries is deduplicated."""
    adapter = ProductHuntAdapter()

    # Both topic queries return same posts
    async def mock_post(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: MOCK_PH_RESPONSE,
            raise_for_status=lambda: None,
        )

    with patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "test-token"}), \
         patch("max.sources.product_hunt.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=30)

    # Despite 2 topic queries returning same 2 posts, should see 2 unique
    ids = {s.metadata["ph_id"] for s in signals}
    assert len(ids) == 2


def test_extract_posts_handles_malformed_data() -> None:
    assert _extract_posts({}) == []
    assert _extract_posts({"data": None}) == []
    assert _extract_posts({"data": {"topic": None}}) == []
