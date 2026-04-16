"""Comprehensive tests for PyPI registry source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.base import AdapterFetchError, AdapterRateLimitError
from max.sources.pypi_registry import (
    PyPIRegistryAdapter,
    _DEFAULT_KEYWORDS,
    _build_tags,
    _fetch_download_stats,
    _fetch_package_info,
    _matches_keywords,
    _parse_rfc822,
    _parse_rss,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────


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
    <item>
      <title>anthropic-sdk 2.0.0</title>
      <link>https://pypi.org/project/anthropic-sdk/2.0.0/</link>
      <pubDate>Sat, 29 Mar 2026 09:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

MOCK_PYPI_JSON_LANGCHAIN = {
    "info": {
        "name": "langchain-agent",
        "version": "0.2.0",
        "summary": "AI agent framework built on LangChain",
        "author": "testdev",
        "classifiers": [
            "Topic :: Scientific/Engineering :: Artificial Intelligence",
            "Development Status :: 4 - Beta",
        ],
        "requires_python": ">=3.10",
        "package_url": "https://pypi.org/project/langchain-agent/",
        "project_urls": {"GitHub": "https://github.com/test/langchain-agent"},
        "keywords": "ai,agent,langchain",
    }
}

MOCK_PYPI_JSON_OPENAI = {
    "info": {
        "name": "openai-helpers",
        "version": "1.0.0",
        "summary": "Helper utilities for OpenAI API",
        "author_email": "dev@example.com",
        "classifiers": ["Topic :: Software Development :: Libraries"],
        "requires_python": ">=3.9",
        "package_url": "https://pypi.org/project/openai-helpers/",
        "project_urls": {"Homepage": "https://example.com/openai-helpers"},
        "keywords": "openai api utilities",
    }
}

MOCK_PYPI_JSON_ANTHROPIC = {
    "info": {
        "name": "anthropic-sdk",
        "version": "2.0.0",
        "summary": "Official Anthropic SDK for Claude API",
        "author_email": "support@anthropic.com",
        "classifiers": [
            "Topic :: Scientific/Engineering :: Artificial Intelligence",
            "Topic :: Software Development :: Libraries :: Python Modules",
        ],
        "requires_python": ">=3.8",
        "package_url": "https://pypi.org/project/anthropic-sdk/",
        "project_urls": {
            "GitHub": "https://github.com/anthropics/anthropic-sdk-python",
            "Documentation": "https://docs.anthropic.com",
        },
        "keywords": "anthropic,claude,ai,llm",
    }
}

MOCK_PYPISTATS_HIGH_DOWNLOADS = {"data": {"last_week": 150000}}
MOCK_PYPISTATS_LOW_DOWNLOADS = {"data": {"last_week": 5000}}
MOCK_PYPISTATS_ZERO_DOWNLOADS = {"data": {"last_week": 0}}


# ── Helper Functions Tests ───────────────────────────────────────────


def test_parse_rss_extracts_items() -> None:
    """RSS parser extracts package name, link, and publication date."""
    results = _parse_rss(MOCK_RSS_XML)
    assert len(results) == 4
    assert results[0][0] == "langchain-agent"
    assert "pypi.org" in results[0][1]
    assert results[0][2] is not None
    assert isinstance(results[0][2], datetime)


def test_parse_rss_handles_invalid_xml() -> None:
    """RSS parser returns empty list for invalid XML."""
    assert _parse_rss("not xml at all") == []
    assert _parse_rss("<broken><xml") == []
    assert _parse_rss("") == []


def test_parse_rss_handles_empty_items() -> None:
    """RSS parser skips items with missing title."""
    xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title></title>
      <link>https://pypi.org/project/empty/</link>
    </item>
    <item>
      <link>https://pypi.org/project/no-title/</link>
    </item>
  </channel>
</rss>
"""
    results = _parse_rss(xml)
    assert len(results) == 0


def test_parse_rss_handles_missing_pubdate() -> None:
    """RSS parser handles items without pubDate gracefully."""
    xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>test-pkg 1.0.0</title>
      <link>https://pypi.org/project/test-pkg/</link>
    </item>
  </channel>
</rss>
"""
    results = _parse_rss(xml)
    assert len(results) == 1
    assert results[0][0] == "test-pkg"
    assert results[0][2] is None


def test_matches_keywords_positive() -> None:
    """Keyword matching identifies AI/ML related packages."""
    assert _matches_keywords("langchain-agent", _DEFAULT_KEYWORDS)
    assert _matches_keywords("openai-helpers", _DEFAULT_KEYWORDS)
    assert _matches_keywords("mcp-server-utils", _DEFAULT_KEYWORDS)
    assert _matches_keywords("anthropic-sdk", _DEFAULT_KEYWORDS)
    assert _matches_keywords("gpt-wrapper", _DEFAULT_KEYWORDS)
    assert _matches_keywords("claude-api", _DEFAULT_KEYWORDS)
    assert _matches_keywords("neural-network-lib", _DEFAULT_KEYWORDS)
    assert _matches_keywords("transformer_models", _DEFAULT_KEYWORDS)


def test_matches_keywords_negative() -> None:
    """Keyword matching filters out non-AI/ML packages."""
    assert not _matches_keywords("flask-utils", _DEFAULT_KEYWORDS)
    assert not _matches_keywords("django-rest", _DEFAULT_KEYWORDS)
    assert not _matches_keywords("pytest-plugin", _DEFAULT_KEYWORDS)
    assert not _matches_keywords("requests-toolbelt", _DEFAULT_KEYWORDS)


def test_matches_keywords_custom_set() -> None:
    """Keyword matching works with custom keyword sets."""
    custom_keywords = {"database", "sql", "postgres"}
    assert _matches_keywords("sqlalchemy", custom_keywords)
    assert _matches_keywords("postgres-adapter", custom_keywords)
    assert not _matches_keywords("ai-toolkit", custom_keywords)


def test_build_tags_from_classifiers() -> None:
    """Tag builder extracts tags from PyPI classifiers."""
    info = {
        "classifiers": [
            "Topic :: Scientific/Engineering :: Artificial Intelligence",
            "Development Status :: 4 - Beta",
        ],
        "keywords": "",
        "name": "test-pkg",
    }
    tags = _build_tags(info, "test-pkg")
    assert "ai" in tags
    assert "python" in tags


def test_build_tags_from_keywords() -> None:
    """Tag builder extracts tags from keywords field."""
    info = {
        "classifiers": [],
        "keywords": "ai,llm,transformer",
        "name": "test-pkg",
    }
    tags = _build_tags(info, "test-pkg")
    assert "ai" in tags
    assert "llm" in tags
    assert "transformer" in tags
    assert "python" in tags


def test_build_tags_from_package_name() -> None:
    """Tag builder extracts tags from package name."""
    info = {"classifiers": [], "keywords": "", "name": "langchain-agent"}
    tags = _build_tags(info, "langchain-agent")
    assert "langchain" in tags
    assert "agent" in tags
    assert "python" in tags


def test_build_tags_limits_to_10() -> None:
    """Tag builder limits output to 10 tags."""
    info = {
        "classifiers": [
            "Topic :: Scientific/Engineering :: Artificial Intelligence",
            "Topic :: Scientific/Engineering :: Machine Learning",
        ],
        "keywords": "ai,llm,gpt,claude,openai,anthropic,transformer,embedding,rag,vector,chatbot,prompt",
        "name": "ai-llm-gpt-claude-openai-anthropic",
    }
    tags = _build_tags(info, "ai-llm-gpt")
    assert len(tags) <= 10


def test_parse_rfc822_valid_date() -> None:
    """RFC 822 parser handles valid date strings."""
    date_str = "Sat, 29 Mar 2026 12:00:00 GMT"
    parsed = _parse_rfc822(date_str)
    assert parsed is not None
    assert isinstance(parsed, datetime)
    assert parsed.tzinfo == timezone.utc


def test_parse_rfc822_invalid_date() -> None:
    """RFC 822 parser returns None for invalid date strings."""
    assert _parse_rfc822("not a date") is None
    assert _parse_rfc822("") is None
    assert _parse_rfc822("2026-03-29") is None


# ── Async Helper Tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_package_info_success() -> None:
    """Package info fetcher successfully retrieves metadata."""
    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: MOCK_PYPI_JSON_LANGCHAIN,
            raise_for_status=lambda: None,
        )

    async with httpx.AsyncClient() as client:
        with patch.object(client, "get", mock_get):
            info = await _fetch_package_info(client, "langchain-agent")

    assert info is not None
    assert info["name"] == "langchain-agent"
    assert info["version"] == "0.2.0"
    assert info["author"] == "testdev"


@pytest.mark.asyncio
async def test_fetch_package_info_http_error() -> None:
    """Package info fetcher returns None on HTTP error."""
    async def mock_get(url: str, **kwargs) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found",
            request=MagicMock(),
            response=MagicMock(status_code=404),
        )
        return resp

    async with httpx.AsyncClient() as client:
        with patch.object(client, "get", mock_get):
            info = await _fetch_package_info(client, "nonexistent-package")

    assert info is None


@pytest.mark.asyncio
async def test_fetch_package_info_network_error() -> None:
    """Package info fetcher returns None on network error."""
    async def mock_get(url: str, **kwargs) -> MagicMock:
        raise httpx.RequestError("Connection failed")

    async with httpx.AsyncClient() as client:
        with patch.object(client, "get", mock_get):
            info = await _fetch_package_info(client, "test-pkg")

    assert info is None


@pytest.mark.asyncio
async def test_fetch_package_info_malformed_json() -> None:
    """Package info fetcher returns None on malformed JSON."""
    async def mock_get(url: str, **kwargs) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.json.side_effect = ValueError("Invalid JSON")
        return resp

    async with httpx.AsyncClient() as client:
        with patch.object(client, "get", mock_get):
            info = await _fetch_package_info(client, "broken-pkg")

    assert info is None


@pytest.mark.asyncio
async def test_fetch_package_info_uses_author_email_fallback() -> None:
    """Package info fetcher falls back to author_email when author is missing."""
    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: MOCK_PYPI_JSON_OPENAI,
            raise_for_status=lambda: None,
        )

    async with httpx.AsyncClient() as client:
        with patch.object(client, "get", mock_get):
            info = await _fetch_package_info(client, "openai-helpers")

    assert info is not None
    assert info["author"] == "dev@example.com"


@pytest.mark.asyncio
async def test_fetch_download_stats_success() -> None:
    """Download stats fetcher successfully retrieves weekly downloads."""
    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: MOCK_PYPISTATS_HIGH_DOWNLOADS,
            raise_for_status=lambda: None,
        )

    async with httpx.AsyncClient() as client:
        with patch.object(client, "get", mock_get):
            downloads = await _fetch_download_stats(client, "popular-pkg")

    assert downloads == 150000


@pytest.mark.asyncio
async def test_fetch_download_stats_http_error() -> None:
    """Download stats fetcher returns None on HTTP error."""
    async def mock_get(url: str, **kwargs) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found",
            request=MagicMock(),
            response=MagicMock(status_code=404),
        )
        return resp

    async with httpx.AsyncClient() as client:
        with patch.object(client, "get", mock_get):
            downloads = await _fetch_download_stats(client, "unknown-pkg")

    assert downloads is None


@pytest.mark.asyncio
async def test_fetch_download_stats_malformed_json() -> None:
    """Download stats fetcher returns None on malformed JSON."""
    async def mock_get(url: str, **kwargs) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.json.side_effect = ValueError("Invalid JSON")
        return resp

    async with httpx.AsyncClient() as client:
        with patch.object(client, "get", mock_get):
            downloads = await _fetch_download_stats(client, "broken-pkg")

    assert downloads is None


# ── Adapter Integration Tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_pypi_adapter_fetch_success() -> None:
    """PyPI adapter successfully fetches and enriches AI/ML packages."""
    adapter = PyPIRegistryAdapter()

    async def mock_get(url: str, **kwargs) -> MagicMock:
        if "rss" in url:
            return MagicMock(text=MOCK_RSS_XML, raise_for_status=lambda: None)
        if "pypi.org/pypi/langchain-agent" in url:
            return MagicMock(json=lambda: MOCK_PYPI_JSON_LANGCHAIN, raise_for_status=lambda: None)
        if "pypi.org/pypi/openai-helpers" in url:
            return MagicMock(json=lambda: MOCK_PYPI_JSON_OPENAI, raise_for_status=lambda: None)
        if "pypi.org/pypi/anthropic-sdk" in url:
            return MagicMock(json=lambda: MOCK_PYPI_JSON_ANTHROPIC, raise_for_status=lambda: None)
        if "pypistats.org" in url:
            return MagicMock(json=lambda: MOCK_PYPISTATS_HIGH_DOWNLOADS, raise_for_status=lambda: None)
        return MagicMock(raise_for_status=lambda: None, json=lambda: {}, text="")

    with patch("max.sources.pypi_registry.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    # Should filter out flask-utils (no AI keyword), keep AI packages
    assert len(signals) >= 1
    names = {s.metadata["pypi_name"] for s in signals}
    assert "langchain-agent" in names
    assert "flask-utils" not in names

    # Check signal structure
    first = [s for s in signals if s.metadata["pypi_name"] == "langchain-agent"][0]
    assert first.source_type == SignalSourceType.REGISTRY
    assert first.source_adapter == "pypi_registry"
    assert first.title == "langchain-agent@0.2.0"
    assert first.author == "testdev"
    assert "python" in first.tags
    assert first.credibility == min(150000 / 100_000, 1.0)
    assert first.metadata["version"] == "0.2.0"
    assert first.metadata["requires_python"] == ">=3.10"


@pytest.mark.asyncio
async def test_pypi_adapter_respects_limit() -> None:
    """PyPI adapter respects the limit parameter."""
    adapter = PyPIRegistryAdapter()

    # Create RSS with many AI packages
    many_packages = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item><title>ai-pkg-1 1.0.0</title><link>https://pypi.org/project/ai-pkg-1/</link></item>
    <item><title>ai-pkg-2 1.0.0</title><link>https://pypi.org/project/ai-pkg-2/</link></item>
    <item><title>ai-pkg-3 1.0.0</title><link>https://pypi.org/project/ai-pkg-3/</link></item>
    <item><title>ai-pkg-4 1.0.0</title><link>https://pypi.org/project/ai-pkg-4/</link></item>
    <item><title>ai-pkg-5 1.0.0</title><link>https://pypi.org/project/ai-pkg-5/</link></item>
  </channel>
</rss>
"""

    async def mock_get(url: str, **kwargs) -> MagicMock:
        if "rss" in url:
            return MagicMock(text=many_packages, raise_for_status=lambda: None)
        if "pypi.org/pypi/" in url:
            pkg_name = url.split("/")[-2]
            return MagicMock(
                json=lambda: {
                    "info": {
                        "name": pkg_name,
                        "version": "1.0.0",
                        "summary": f"AI package {pkg_name}",
                        "author": "test",
                    }
                },
                raise_for_status=lambda: None,
            )
        if "pypistats.org" in url:
            return MagicMock(json=lambda: MOCK_PYPISTATS_LOW_DOWNLOADS, raise_for_status=lambda: None)
        return MagicMock(raise_for_status=lambda: None, json=lambda: {}, text="")

    with patch("max.sources.pypi_registry.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=2)

    assert len(signals) <= 2


@pytest.mark.asyncio
async def test_pypi_adapter_filters_by_keywords() -> None:
    """PyPI adapter filters packages by configured keywords."""
    adapter = PyPIRegistryAdapter(config={"keywords": ["database", "sql"]})

    rss_mixed = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item><title>sqlalchemy 2.0.0</title><link>https://pypi.org/project/sqlalchemy/</link></item>
    <item><title>ai-toolkit 1.0.0</title><link>https://pypi.org/project/ai-toolkit/</link></item>
  </channel>
</rss>
"""

    async def mock_get(url: str, **kwargs) -> MagicMock:
        if "rss" in url:
            return MagicMock(text=rss_mixed, raise_for_status=lambda: None)
        if "pypi.org/pypi/sqlalchemy" in url:
            return MagicMock(
                json=lambda: {
                    "info": {
                        "name": "sqlalchemy",
                        "version": "2.0.0",
                        "summary": "Database toolkit",
                        "author": "test",
                    }
                },
                raise_for_status=lambda: None,
            )
        if "pypistats.org" in url:
            return MagicMock(json=lambda: MOCK_PYPISTATS_LOW_DOWNLOADS, raise_for_status=lambda: None)
        return MagicMock(raise_for_status=lambda: None, json=lambda: {}, text="")

    with patch("max.sources.pypi_registry.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    # Only sqlalchemy should match custom keywords
    assert len(signals) >= 1
    assert signals[0].metadata["pypi_name"] == "sqlalchemy"


@pytest.mark.asyncio
async def test_pypi_adapter_handles_404_package() -> None:
    """PyPI adapter skips packages that return 404 from JSON API."""
    adapter = PyPIRegistryAdapter()

    async def mock_get(url: str, **kwargs) -> MagicMock:
        if "rss" in url:
            return MagicMock(text=MOCK_RSS_XML, raise_for_status=lambda: None)
        if "pypi.org/pypi/langchain-agent" in url:
            resp = MagicMock()
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "404 Not Found",
                request=MagicMock(),
                response=MagicMock(status_code=404),
            )
            return resp
        if "pypi.org/pypi/openai-helpers" in url:
            return MagicMock(json=lambda: MOCK_PYPI_JSON_OPENAI, raise_for_status=lambda: None)
        if "pypistats.org" in url:
            return MagicMock(json=lambda: MOCK_PYPISTATS_LOW_DOWNLOADS, raise_for_status=lambda: None)
        return MagicMock(raise_for_status=lambda: None, json=lambda: {}, text="")

    with patch("max.sources.pypi_registry.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    # langchain-agent returned 404, should be skipped
    names = {s.metadata["pypi_name"] for s in signals}
    assert "langchain-agent" not in names
    assert "openai-helpers" in names


@pytest.mark.asyncio
async def test_pypi_adapter_handles_rss_fetch_failure() -> None:
    """PyPI adapter continues with next RSS feed if one fails."""
    adapter = PyPIRegistryAdapter()

    call_count = 0

    async def mock_get(url: str, **kwargs) -> MagicMock:
        nonlocal call_count
        if "rss/updates.xml" in url:
            # First RSS feed fails
            raise httpx.RequestError("Connection timeout")
        if "rss/packages.xml" in url:
            # Second RSS feed succeeds
            return MagicMock(text=MOCK_RSS_XML, raise_for_status=lambda: None)
        if "pypi.org/pypi/langchain-agent" in url:
            return MagicMock(json=lambda: MOCK_PYPI_JSON_LANGCHAIN, raise_for_status=lambda: None)
        if "pypistats.org" in url:
            return MagicMock(json=lambda: MOCK_PYPISTATS_LOW_DOWNLOADS, raise_for_status=lambda: None)
        return MagicMock(raise_for_status=lambda: None, json=lambda: {}, text="")

    with patch("max.sources.pypi_registry.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    # Should still get results from second RSS feed
    assert len(signals) >= 1


@pytest.mark.asyncio
async def test_pypi_adapter_pypistats_fallback_credibility() -> None:
    """When pypistats fails, credibility falls back to 0.3."""
    adapter = PyPIRegistryAdapter()

    async def mock_get(url: str, **kwargs) -> MagicMock:
        if "rss" in url:
            return MagicMock(text=MOCK_RSS_XML, raise_for_status=lambda: None)
        if "pypi.org/pypi/langchain-agent" in url:
            return MagicMock(json=lambda: MOCK_PYPI_JSON_LANGCHAIN, raise_for_status=lambda: None)
        if "pypistats.org" in url:
            raise httpx.HTTPError("pypistats service unavailable")
        return MagicMock(raise_for_status=lambda: None, json=lambda: {}, text="")

    with patch("max.sources.pypi_registry.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) >= 1
    first = [s for s in signals if s.metadata["pypi_name"] == "langchain-agent"][0]
    assert first.credibility == 0.3
    assert first.metadata["downloads_week"] is None


@pytest.mark.asyncio
async def test_pypi_adapter_credibility_calculation() -> None:
    """Credibility is calculated correctly based on download counts."""
    adapter = PyPIRegistryAdapter()

    test_cases = [
        ("pkg-high", 150000, 1.0),  # 150k/100k = 1.5, capped at 1.0
        ("pkg-medium", 50000, 0.5),  # 50k/100k = 0.5
        ("pkg-low", 5000, 0.05),  # 5k/100k = 0.05
        ("pkg-zero", 0, 0.0),  # 0/100k = 0.0
    ]

    for pkg_name, downloads, expected_credibility in test_cases:
        rss = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item><title>ai-{pkg_name} 1.0.0</title><link>https://pypi.org/project/ai-{pkg_name}/</link></item>
  </channel>
</rss>
"""

        async def mock_get(url: str, **kwargs) -> MagicMock:
            if "rss" in url:
                return MagicMock(text=rss, raise_for_status=lambda: None)
            if "pypi.org/pypi/" in url:
                return MagicMock(
                    json=lambda: {
                        "info": {
                            "name": f"ai-{pkg_name}",
                            "version": "1.0.0",
                            "summary": "Test package",
                            "author": "test",
                        }
                    },
                    raise_for_status=lambda: None,
                )
            if "pypistats.org" in url:
                return MagicMock(
                    json=lambda: {"data": {"last_week": downloads}},
                    raise_for_status=lambda: None,
                )
            return MagicMock(raise_for_status=lambda: None, json=lambda: {}, text="")

        with patch("max.sources.pypi_registry.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_client

            signals = await adapter.fetch(limit=1)

        assert len(signals) == 1
        assert signals[0].credibility == expected_credibility
        assert signals[0].metadata["downloads_week"] == downloads


@pytest.mark.asyncio
async def test_pypi_adapter_deduplicates_packages() -> None:
    """PyPI adapter deduplicates packages seen in multiple RSS feeds."""
    adapter = PyPIRegistryAdapter()

    # Both RSS feeds contain the same package
    duplicate_rss = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item><title>langchain-agent 0.2.0</title><link>https://pypi.org/project/langchain-agent/</link></item>
  </channel>
</rss>
"""

    async def mock_get(url: str, **kwargs) -> MagicMock:
        if "rss" in url:
            return MagicMock(text=duplicate_rss, raise_for_status=lambda: None)
        if "pypi.org/pypi/langchain-agent" in url:
            return MagicMock(json=lambda: MOCK_PYPI_JSON_LANGCHAIN, raise_for_status=lambda: None)
        if "pypistats.org" in url:
            return MagicMock(json=lambda: MOCK_PYPISTATS_LOW_DOWNLOADS, raise_for_status=lambda: None)
        return MagicMock(raise_for_status=lambda: None, json=lambda: {}, text="")

    with patch("max.sources.pypi_registry.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    # Despite appearing in both RSS feeds, should only appear once
    assert len(signals) == 1
    assert signals[0].metadata["pypi_name"] == "langchain-agent"


@pytest.mark.asyncio
async def test_pypi_adapter_handles_malformed_json_in_pypi_api() -> None:
    """PyPI adapter skips packages with malformed JSON responses."""
    adapter = PyPIRegistryAdapter()

    async def mock_get(url: str, **kwargs) -> MagicMock:
        if "rss" in url:
            return MagicMock(text=MOCK_RSS_XML, raise_for_status=lambda: None)
        if "pypi.org/pypi/langchain-agent" in url:
            resp = MagicMock()
            resp.raise_for_status = lambda: None
            resp.json.side_effect = ValueError("Invalid JSON")
            return resp
        if "pypi.org/pypi/openai-helpers" in url:
            return MagicMock(json=lambda: MOCK_PYPI_JSON_OPENAI, raise_for_status=lambda: None)
        if "pypistats.org" in url:
            return MagicMock(json=lambda: MOCK_PYPISTATS_LOW_DOWNLOADS, raise_for_status=lambda: None)
        return MagicMock(raise_for_status=lambda: None, json=lambda: {}, text="")

    with patch("max.sources.pypi_registry.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    # langchain-agent had malformed JSON, should be skipped
    names = {s.metadata["pypi_name"] for s in signals}
    assert "langchain-agent" not in names
    assert "openai-helpers" in names


@pytest.mark.asyncio
async def test_pypi_adapter_timeout_handling() -> None:
    """PyPI adapter handles network timeouts gracefully."""
    adapter = PyPIRegistryAdapter()

    async def mock_get(url: str, **kwargs) -> MagicMock:
        if "rss/updates.xml" in url:
            raise httpx.TimeoutException("Request timed out")
        if "rss/packages.xml" in url:
            return MagicMock(text=MOCK_RSS_XML, raise_for_status=lambda: None)
        if "pypi.org/pypi/" in url:
            return MagicMock(json=lambda: MOCK_PYPI_JSON_LANGCHAIN, raise_for_status=lambda: None)
        if "pypistats.org" in url:
            return MagicMock(json=lambda: MOCK_PYPISTATS_LOW_DOWNLOADS, raise_for_status=lambda: None)
        return MagicMock(raise_for_status=lambda: None, json=lambda: {}, text="")

    with patch("max.sources.pypi_registry.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    # Should still get results from second RSS feed despite timeout on first
    assert len(signals) >= 1


@pytest.mark.asyncio
async def test_pypi_adapter_version_parsing_edge_cases() -> None:
    """PyPI adapter handles various version string formats."""
    adapter = PyPIRegistryAdapter()

    rss_versions = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item><title>ai-pkg 1.0.0rc1</title><link>https://pypi.org/project/ai-pkg/</link></item>
    <item><title>ai-tool 2.0.0.dev20260101</title><link>https://pypi.org/project/ai-tool/</link></item>
    <item><title>ai-lib 0.1.0a1</title><link>https://pypi.org/project/ai-lib/</link></item>
  </channel>
</rss>
"""

    async def mock_get(url: str, **kwargs) -> MagicMock:
        if "rss" in url:
            return MagicMock(text=rss_versions, raise_for_status=lambda: None)
        if "pypi.org/pypi/ai-pkg" in url:
            return MagicMock(
                json=lambda: {
                    "info": {
                        "name": "ai-pkg",
                        "version": "1.0.0rc1",
                        "summary": "Release candidate version",
                        "author": "test",
                    }
                },
                raise_for_status=lambda: None,
            )
        if "pypi.org/pypi/ai-tool" in url:
            return MagicMock(
                json=lambda: {
                    "info": {
                        "name": "ai-tool",
                        "version": "2.0.0.dev20260101",
                        "summary": "Dev version",
                        "author": "test",
                    }
                },
                raise_for_status=lambda: None,
            )
        if "pypi.org/pypi/ai-lib" in url:
            return MagicMock(
                json=lambda: {
                    "info": {
                        "name": "ai-lib",
                        "version": "0.1.0a1",
                        "summary": "Alpha version",
                        "author": "test",
                    }
                },
                raise_for_status=lambda: None,
            )
        if "pypistats.org" in url:
            return MagicMock(json=lambda: MOCK_PYPISTATS_LOW_DOWNLOADS, raise_for_status=lambda: None)
        return MagicMock(raise_for_status=lambda: None, json=lambda: {}, text="")

    with patch("max.sources.pypi_registry.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) >= 3
    versions = {s.metadata["version"] for s in signals}
    assert "1.0.0rc1" in versions
    assert "2.0.0.dev20260101" in versions
    assert "0.1.0a1" in versions


@pytest.mark.asyncio
async def test_pypi_adapter_name_property() -> None:
    """PyPI adapter returns correct name."""
    adapter = PyPIRegistryAdapter()
    assert adapter.name == "pypi_registry"


@pytest.mark.asyncio
async def test_pypi_adapter_source_type_property() -> None:
    """PyPI adapter returns correct source type."""
    adapter = PyPIRegistryAdapter()
    assert adapter.source_type == SignalSourceType.REGISTRY.value


def test_pypi_adapter_keywords_default() -> None:
    """PyPI adapter uses default keywords when not configured."""
    adapter = PyPIRegistryAdapter()
    assert adapter.keywords == _DEFAULT_KEYWORDS


def test_pypi_adapter_keywords_custom() -> None:
    """PyPI adapter uses custom keywords from config."""
    custom_keywords = ["database", "sql", "postgres"]
    adapter = PyPIRegistryAdapter(config={"keywords": custom_keywords})
    assert adapter.keywords == set(custom_keywords)
