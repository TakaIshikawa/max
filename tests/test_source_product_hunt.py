"""Comprehensive tests for Product Hunt source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.base import AdapterFetchError
from max.sources.product_hunt import (
    ProductHuntAdapter,
    _DEFAULT_TOPICS,
    _build_tags,
    _extract_posts,
    _extract_topics,
    _parse_dt,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────


MOCK_GRAPHQL_POST_1 = {
    "id": "post-12345",
    "name": "AI Agent Framework",
    "tagline": "Build intelligent AI agents with ease",
    "description": "A comprehensive framework for building and deploying AI agents with support for LLM integration, tool use, and multi-agent workflows.",
    "url": "https://www.producthunt.com/posts/ai-agent-framework",
    "votesCount": 250,
    "commentsCount": 15,
    "createdAt": "2026-04-15T10:30:00Z",
    "makers": [
        {"username": "maker1"},
        {"username": "maker2"},
    ],
    "topics": {
        "edges": [
            {"node": {"slug": "developer-tools", "name": "Developer Tools"}},
            {"node": {"slug": "artificial-intelligence", "name": "Artificial Intelligence"}},
        ]
    },
}

MOCK_GRAPHQL_POST_2 = {
    "id": "post-67890",
    "name": "MCP Server Utils",
    "tagline": "Utilities for building MCP servers",
    "description": "Essential utilities and helpers for creating Model Context Protocol servers.",
    "url": "https://www.producthunt.com/posts/mcp-server-utils",
    "votesCount": 500,
    "commentsCount": 25,
    "createdAt": "2026-04-14T14:20:00Z",
    "makers": [
        {"username": "developer123"},
    ],
    "topics": {
        "edges": [
            {"node": {"slug": "developer-tools", "name": "Developer Tools"}},
            {"node": {"slug": "api", "name": "API"}},
        ]
    },
}

MOCK_GRAPHQL_POST_3 = {
    "id": "post-11111",
    "name": "Minimal Product",
    "tagline": "Simple tool",
    "description": None,  # Missing description
    "url": "https://www.producthunt.com/posts/minimal-product",
    "votesCount": 0,
    "commentsCount": 0,
    "createdAt": "2026-04-13T09:15:00Z",
    "makers": [],
    "topics": {
        "edges": []
    },
}

MOCK_GRAPHQL_RESPONSE_DEVTOOLS = {
    "data": {
        "topic": {
            "posts": {
                "edges": [
                    {"node": MOCK_GRAPHQL_POST_1},
                    {"node": MOCK_GRAPHQL_POST_2},
                ]
            }
        }
    }
}

MOCK_GRAPHQL_RESPONSE_AI = {
    "data": {
        "topic": {
            "posts": {
                "edges": [
                    {"node": MOCK_GRAPHQL_POST_1},  # Duplicate
                    {"node": MOCK_GRAPHQL_POST_3},
                ]
            }
        }
    }
}

MOCK_GRAPHQL_RESPONSE_EMPTY = {
    "data": {
        "topic": {
            "posts": {
                "edges": []
            }
        }
    }
}

MOCK_GRAPHQL_RESPONSE_MALFORMED = {
    "data": None
}


# ── Helper Functions Tests ───────────────────────────────────────────


def test_extract_posts_valid_response() -> None:
    """Extract posts from valid GraphQL response."""
    posts = _extract_posts(MOCK_GRAPHQL_RESPONSE_DEVTOOLS)
    assert len(posts) == 2
    assert posts[0]["id"] == "post-12345"
    assert posts[0]["name"] == "AI Agent Framework"
    assert posts[1]["id"] == "post-67890"


def test_extract_posts_empty_edges() -> None:
    """Extract posts returns empty list for empty edges."""
    posts = _extract_posts(MOCK_GRAPHQL_RESPONSE_EMPTY)
    assert len(posts) == 0


def test_extract_posts_missing_keys() -> None:
    """Extract posts returns empty list when keys are missing."""
    assert _extract_posts({"data": None}) == []
    assert _extract_posts({"data": {"topic": None}}) == []
    assert _extract_posts({"data": {"topic": {"posts": None}}}) == []
    assert _extract_posts({}) == []


def test_extract_posts_malformed_data() -> None:
    """Extract posts handles malformed data gracefully."""
    assert _extract_posts(MOCK_GRAPHQL_RESPONSE_MALFORMED) == []
    assert _extract_posts({"invalid": "structure"}) == []


def test_extract_topics_valid_post() -> None:
    """Extract topics from valid post."""
    topics = _extract_topics(MOCK_GRAPHQL_POST_1)
    assert len(topics) == 2
    assert "developer-tools" in topics
    assert "artificial-intelligence" in topics


def test_extract_topics_empty_edges() -> None:
    """Extract topics returns empty list for empty edges."""
    topics = _extract_topics(MOCK_GRAPHQL_POST_3)
    assert len(topics) == 0


def test_extract_topics_missing_topics() -> None:
    """Extract topics handles missing topics field."""
    post_no_topics = {"id": "test", "topics": {}}
    assert _extract_topics(post_no_topics) == []
    assert _extract_topics({"id": "test"}) == []


def test_extract_topics_malformed_edges() -> None:
    """Extract topics handles malformed edges."""
    post_bad_edges = {"topics": {"edges": [{"invalid": "node"}]}}
    topics = _extract_topics(post_bad_edges)
    # Should handle KeyError gracefully and return partial or empty list
    assert isinstance(topics, list)


def test_parse_dt_valid_iso8601() -> None:
    """Parse valid ISO 8601 datetime with Z suffix."""
    dt = _parse_dt("2026-04-15T10:30:00Z")
    assert dt is not None
    assert isinstance(dt, datetime)
    assert dt.year == 2026
    assert dt.month == 4
    assert dt.day == 15
    assert dt.hour == 10
    assert dt.minute == 30
    assert dt.tzinfo is not None


def test_parse_dt_with_timezone_offset() -> None:
    """Parse ISO 8601 datetime with timezone offset."""
    dt = _parse_dt("2026-04-15T10:30:00+05:00")
    assert dt is not None
    assert isinstance(dt, datetime)
    assert dt.tzinfo is not None


def test_parse_dt_invalid_string() -> None:
    """Parse returns None for invalid datetime strings."""
    assert _parse_dt("not a date") is None
    assert _parse_dt("2026-13-01T00:00:00Z") is None
    assert _parse_dt("") is None


def test_parse_dt_none_input() -> None:
    """Parse returns None for None input."""
    assert _parse_dt(None) is None


def test_build_tags_from_topics() -> None:
    """Build tags from Product Hunt topic slugs."""
    topics = ["developer-tools", "artificial-intelligence"]
    tagline = "Some product"
    tags = _build_tags(topics, tagline)

    assert "devtools" in tags
    assert "ai" in tags


def test_build_tags_topic_mapping() -> None:
    """Build tags maps topic slugs to standardized tags."""
    topics = ["machine-learning", "saas", "open-source", "analytics"]
    tags = _build_tags(topics, "")

    assert "ml" in tags
    assert "saas" in tags
    assert "open_source" in tags
    assert "analytics" in tags


def test_build_tags_from_tagline_keywords() -> None:
    """Build tags extracts keywords from tagline."""
    topics: list[str] = []
    tagline = "AI agent framework with LLM support and MCP integration"
    tags = _build_tags(topics, tagline)

    assert "ai" in tags
    assert "agent" in tags
    assert "llm" in tags
    assert "mcp" in tags


def test_build_tags_tagline_keyword_variations() -> None:
    """Build tags handles different keyword variations."""
    test_cases = [
        ("Artificial intelligence powered tool", "ai"),
        ("Developer tools for API integration", "devtools"),
        ("Language model interface", "llm"),
    ]

    for tagline, expected_tag in test_cases:
        tags = _build_tags([], tagline)
        assert expected_tag in tags


def test_build_tags_limits_to_10() -> None:
    """Build tags limits output to 10 tags."""
    topics = [
        "developer-tools",
        "artificial-intelligence",
        "machine-learning",
        "saas",
        "open-source",
        "api",
        "productivity",
        "design-tools",
        "no-code",
        "analytics",
    ]
    tagline = "AI agent LLM MCP devtools API"
    tags = _build_tags(topics, tagline)

    assert len(tags) <= 10


def test_build_tags_sorted_output() -> None:
    """Build tags returns sorted list."""
    topics = ["developer-tools", "artificial-intelligence"]
    tagline = "API tool"
    tags = _build_tags(topics, tagline)

    assert tags == sorted(tags)


def test_build_tags_deduplication() -> None:
    """Build tags deduplicates tags from multiple sources."""
    topics = ["developer-tools"]  # Maps to "devtools"
    tagline = "Developer tools for AI"  # Also matches "devtools" and "ai"
    tags = _build_tags(topics, tagline)

    # Should only have "devtools" once
    assert tags.count("devtools") == 1


# ── Adapter Integration Tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_product_hunt_adapter_fetch_success() -> None:
    """Product Hunt adapter successfully fetches and parses posts."""
    adapter = ProductHuntAdapter()

    call_count = 0

    async def mock_post(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            return MagicMock(
                json=lambda: MOCK_GRAPHQL_RESPONSE_DEVTOOLS,
                raise_for_status=lambda: None,
            )
        elif call_count == 2:
            return MagicMock(
                json=lambda: MOCK_GRAPHQL_RESPONSE_AI,
                raise_for_status=lambda: None,
            )
        else:
            return MagicMock(
                json=lambda: MOCK_GRAPHQL_RESPONSE_EMPTY,
                raise_for_status=lambda: None,
            )

    with patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "test_token_123"}):
        with patch("max.sources.product_hunt.fetch_with_retry", mock_post):
            signals = await adapter.fetch(limit=10)

    # Should get posts with deduplication (post-12345 appears in both topics)
    assert len(signals) >= 2
    assert len(signals) <= 3

    # Check signal structure
    first = signals[0]
    assert first.source_type == SignalSourceType.TRENDING
    assert first.source_adapter == "product_hunt"
    assert first.title == "AI Agent Framework"
    assert "comprehensive framework" in first.content
    assert first.url == "https://www.producthunt.com/posts/ai-agent-framework"
    assert first.published_at is not None

    # Check credibility calculation: min(votes / 500, 1.0)
    assert first.credibility == min(250 / 500, 1.0)
    assert first.credibility == 0.5

    # Check metadata
    assert first.metadata["ph_id"] == "post-12345"
    assert first.metadata["votes"] == 250
    assert first.metadata["comments"] == 15
    assert "developer-tools" in first.metadata["topics"]
    assert "maker1" in first.metadata["makers"]
    assert "maker2" in first.metadata["makers"]

    # Check tags
    assert "devtools" in first.tags or "ai" in first.tags


@pytest.mark.asyncio
async def test_product_hunt_adapter_credibility_calculation() -> None:
    """Product Hunt adapter calculates credibility correctly."""
    adapter = ProductHuntAdapter()

    test_cases = [
        (0, 0.0),  # 0/500 = 0.0
        (250, 0.5),  # 250/500 = 0.5
        (500, 1.0),  # 500/500 = 1.0
        (1000, 1.0),  # 1000/500 = 2.0, capped at 1.0
    ]

    for votes, expected_credibility in test_cases:
        post = {
            **MOCK_GRAPHQL_POST_1,
            "votesCount": votes,
        }

        response = {
            "data": {
                "topic": {
                    "posts": {
                        "edges": [{"node": post}]
                    }
                }
            }
        }

        async def mock_post(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
            return MagicMock(
                json=lambda: response,
                raise_for_status=lambda: None,
            )

        with patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "test_token_123"}):
            with patch("max.sources.product_hunt.fetch_with_retry", mock_post):
                signals = await adapter.fetch(limit=1)

        assert len(signals) == 1
        assert signals[0].credibility == expected_credibility


@pytest.mark.asyncio
async def test_product_hunt_adapter_deduplicates_posts() -> None:
    """Product Hunt adapter deduplicates posts with same ID across topics."""
    adapter = ProductHuntAdapter()

    # Same post appears in all topic queries
    duplicate_response = {
        "data": {
            "topic": {
                "posts": {
                    "edges": [{"node": MOCK_GRAPHQL_POST_1}]
                }
            }
        }
    }

    async def mock_post(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: duplicate_response,
            raise_for_status=lambda: None,
        )

    with patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "test_token_123"}):
        with patch("max.sources.product_hunt.fetch_with_retry", mock_post):
            signals = await adapter.fetch(limit=20)

    # Despite appearing in both topic queries, should only appear once
    assert len(signals) == 1
    assert signals[0].metadata["ph_id"] == "post-12345"


@pytest.mark.asyncio
async def test_product_hunt_adapter_respects_limit() -> None:
    """Product Hunt adapter respects the limit parameter."""
    adapter = ProductHuntAdapter()

    # Create response with many posts
    many_posts = {
        "data": {
            "topic": {
                "posts": {
                    "edges": [
                        {
                            "node": {
                                **MOCK_GRAPHQL_POST_1,
                                "id": f"post-{i}",
                                "url": f"https://www.producthunt.com/posts/product-{i}",
                            }
                        }
                        for i in range(20)
                    ]
                }
            }
        }
    }

    async def mock_post(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: many_posts,
            raise_for_status=lambda: None,
        )

    with patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "test_token_123"}):
        with patch("max.sources.product_hunt.fetch_with_retry", mock_post):
            signals = await adapter.fetch(limit=5)

    assert len(signals) <= 5


@pytest.mark.asyncio
async def test_product_hunt_adapter_content_truncation() -> None:
    """Product Hunt adapter truncates content to 500 characters."""
    adapter = ProductHuntAdapter()

    long_description = "x" * 1000
    post = {
        **MOCK_GRAPHQL_POST_1,
        "description": long_description,
    }

    response = {
        "data": {
            "topic": {
                "posts": {
                    "edges": [{"node": post}]
                }
            }
        }
    }

    async def mock_post(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: response,
            raise_for_status=lambda: None,
        )

    with patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "test_token_123"}):
        with patch("max.sources.product_hunt.fetch_with_retry", mock_post):
            signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert len(signals[0].content) == 500


@pytest.mark.asyncio
async def test_product_hunt_adapter_content_fallback() -> None:
    """Product Hunt adapter falls back from description to tagline to empty."""
    adapter = ProductHuntAdapter()

    # Test description → tagline fallback
    post_no_description = {
        **MOCK_GRAPHQL_POST_1,
        "description": None,
        "tagline": "Fallback tagline",
    }

    response_no_desc = {
        "data": {
            "topic": {
                "posts": {
                    "edges": [{"node": post_no_description}]
                }
            }
        }
    }

    async def mock_post_no_desc(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: response_no_desc,
            raise_for_status=lambda: None,
        )

    with patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "test_token_123"}):
        with patch("max.sources.product_hunt.fetch_with_retry", mock_post_no_desc):
            signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].content == "Fallback tagline"

    # Test tagline → empty fallback (when both description and tagline are empty strings)
    post_no_content = {
        **MOCK_GRAPHQL_POST_1,
        "description": "",
        "tagline": "",
    }

    response_no_content = {
        "data": {
            "topic": {
                "posts": {
                    "edges": [{"node": post_no_content}]
                }
            }
        }
    }

    async def mock_post_no_content(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: response_no_content,
            raise_for_status=lambda: None,
        )

    with patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "test_token_123"}):
        with patch("max.sources.product_hunt.fetch_with_retry", mock_post_no_content):
            signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].content == ""


@pytest.mark.asyncio
async def test_product_hunt_adapter_token_from_env() -> None:
    """Product Hunt adapter reads token from PRODUCT_HUNT_TOKEN environment variable."""
    adapter = ProductHuntAdapter()

    async def mock_post(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: MOCK_GRAPHQL_RESPONSE_EMPTY,
            raise_for_status=lambda: None,
        )

    with patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "env_token_123"}):
        with patch("max.sources.product_hunt.fetch_with_retry", mock_post):
            signals = await adapter.fetch(limit=10)

    assert isinstance(signals, list)


@pytest.mark.asyncio
async def test_product_hunt_adapter_token_from_vault() -> None:
    """Product Hunt adapter falls back to vault when env token is missing."""
    adapter = ProductHuntAdapter()

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "vault_token_456\n"

    async def mock_post(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: MOCK_GRAPHQL_RESPONSE_EMPTY,
            raise_for_status=lambda: None,
        )

    with patch.dict("os.environ", {}, clear=True):  # Clear PRODUCT_HUNT_TOKEN
        with patch("subprocess.run", return_value=mock_result):
            with patch("max.sources.product_hunt.fetch_with_retry", mock_post):
                signals = await adapter.fetch(limit=10)

    assert isinstance(signals, list)


@pytest.mark.asyncio
async def test_product_hunt_adapter_no_token_warning() -> None:
    """Product Hunt adapter returns empty list with warning when no token available."""
    adapter = ProductHuntAdapter()

    with patch.dict("os.environ", {}, clear=True):  # Clear PRODUCT_HUNT_TOKEN
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with patch("max.sources.product_hunt.logger.warning") as mock_warning:
                signals = await adapter.fetch(limit=10)

    assert len(signals) == 0
    assert mock_warning.called
    assert "PRODUCT_HUNT_TOKEN not set" in str(mock_warning.call_args)


@pytest.mark.asyncio
async def test_product_hunt_adapter_handles_fetch_error() -> None:
    """Product Hunt adapter continues to next topic when fetch raises AdapterFetchError."""
    adapter = ProductHuntAdapter()

    call_count = 0

    async def mock_post(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # First topic query fails
            raise AdapterFetchError("product_hunt", 500, "https://api.producthunt.com/v2/api/graphql")
        else:
            # Second topic query succeeds
            return MagicMock(
                json=lambda: MOCK_GRAPHQL_RESPONSE_DEVTOOLS,
                raise_for_status=lambda: None,
            )

    with patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "test_token_123"}):
        with patch("max.sources.product_hunt.fetch_with_retry", mock_post):
            signals = await adapter.fetch(limit=10)

    # Should still get results from second topic
    assert len(signals) >= 1


@pytest.mark.asyncio
async def test_product_hunt_adapter_custom_topics() -> None:
    """Product Hunt adapter uses custom topics from config."""
    custom_topics = ["design-tools", "saas"]
    adapter = ProductHuntAdapter(config={"topics": custom_topics})

    assert adapter.topics == custom_topics

    requested_topics: list[str] = []

    async def mock_post(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        if "variables" in kwargs.get("json", {}):
            requested_topics.append(kwargs["json"]["variables"]["topic"])
        return MagicMock(
            json=lambda: MOCK_GRAPHQL_RESPONSE_EMPTY,
            raise_for_status=lambda: None,
        )

    with patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "test_token_123"}):
        with patch("max.sources.product_hunt.fetch_with_retry", mock_post):
            await adapter.fetch(limit=10)

    assert "design-tools" in requested_topics
    assert "saas" in requested_topics


@pytest.mark.asyncio
async def test_product_hunt_adapter_handles_malformed_response() -> None:
    """Product Hunt adapter handles malformed GraphQL response gracefully."""
    adapter = ProductHuntAdapter()

    async def mock_post(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: MOCK_GRAPHQL_RESPONSE_MALFORMED,
            raise_for_status=lambda: None,
        )

    with patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "test_token_123"}):
        with patch("max.sources.product_hunt.fetch_with_retry", mock_post):
            signals = await adapter.fetch(limit=10)

    # Should handle malformed data and return empty or partial results
    assert isinstance(signals, list)


@pytest.mark.asyncio
async def test_product_hunt_adapter_handles_missing_fields() -> None:
    """Product Hunt adapter handles posts with missing fields."""
    adapter = ProductHuntAdapter()

    minimal_post = {
        "id": "post-minimal",
        "name": "Minimal Post",
        # Missing most fields
    }

    response = {
        "data": {
            "topic": {
                "posts": {
                    "edges": [{"node": minimal_post}]
                }
            }
        }
    }

    async def mock_post(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: response,
            raise_for_status=lambda: None,
        )

    with patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "test_token_123"}):
        with patch("max.sources.product_hunt.fetch_with_retry", mock_post):
            signals = await adapter.fetch(limit=10)

    # Should handle missing fields gracefully
    assert len(signals) == 1
    signal = signals[0]
    assert signal.title == "Minimal Post"
    assert signal.metadata["ph_id"] == "post-minimal"


@pytest.mark.asyncio
async def test_product_hunt_adapter_makers_limit() -> None:
    """Product Hunt adapter limits makers to 5 in metadata."""
    adapter = ProductHuntAdapter()

    post_many_makers = {
        **MOCK_GRAPHQL_POST_1,
        "makers": [{"username": f"maker{i}"} for i in range(10)],
    }

    response = {
        "data": {
            "topic": {
                "posts": {
                    "edges": [{"node": post_many_makers}]
                }
            }
        }
    }

    async def mock_post(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: response,
            raise_for_status=lambda: None,
        )

    with patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "test_token_123"}):
        with patch("max.sources.product_hunt.fetch_with_retry", mock_post):
            signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert len(signals[0].metadata["makers"]) <= 5


@pytest.mark.asyncio
async def test_product_hunt_adapter_per_topic_calculation() -> None:
    """Product Hunt adapter calculates correct per_topic limit."""
    adapter = ProductHuntAdapter()

    # With 2 default topics and limit=30, per_topic should be max(30/2, 5) = 15
    requested_per_topic: list[int] = []

    async def mock_post(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        if "variables" in kwargs.get("json", {}):
            requested_per_topic.append(kwargs["json"]["variables"]["first"])
        return MagicMock(
            json=lambda: MOCK_GRAPHQL_RESPONSE_EMPTY,
            raise_for_status=lambda: None,
        )

    with patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "test_token_123"}):
        with patch("max.sources.product_hunt.fetch_with_retry", mock_post):
            await adapter.fetch(limit=30)

    assert len(requested_per_topic) >= 1
    assert requested_per_topic[0] == 15  # max(30/2, 5) = 15


@pytest.mark.asyncio
async def test_product_hunt_adapter_name_property() -> None:
    """Product Hunt adapter returns correct name."""
    adapter = ProductHuntAdapter()
    assert adapter.name == "product_hunt"


@pytest.mark.asyncio
async def test_product_hunt_adapter_source_type_property() -> None:
    """Product Hunt adapter returns correct source type."""
    adapter = ProductHuntAdapter()
    assert adapter.source_type == SignalSourceType.TRENDING.value


def test_product_hunt_adapter_topics_default() -> None:
    """Product Hunt adapter uses default topics when not configured."""
    adapter = ProductHuntAdapter()
    assert adapter.topics == _DEFAULT_TOPICS


def test_product_hunt_adapter_topics_custom() -> None:
    """Product Hunt adapter uses custom topics from config."""
    custom_topics = ["design-tools", "productivity", "saas"]
    adapter = ProductHuntAdapter(config={"topics": custom_topics})
    assert adapter.topics == custom_topics


@pytest.mark.asyncio
async def test_product_hunt_adapter_graphql_query_structure() -> None:
    """Product Hunt adapter sends correct GraphQL query structure."""
    adapter = ProductHuntAdapter()

    captured_json: dict = {}

    async def mock_post(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        nonlocal captured_json
        if "json" in kwargs:
            captured_json = kwargs["json"]
        return MagicMock(
            json=lambda: MOCK_GRAPHQL_RESPONSE_EMPTY,
            raise_for_status=lambda: None,
        )

    with patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "test_token_123"}):
        with patch("max.sources.product_hunt.fetch_with_retry", mock_post):
            await adapter.fetch(limit=10)

    # Verify GraphQL query structure
    assert "query" in captured_json
    assert "variables" in captured_json
    assert "topic" in captured_json["variables"]
    assert "first" in captured_json["variables"]
    assert "topic(slug:" in captured_json["query"]
    assert "posts(first:" in captured_json["query"]


@pytest.mark.asyncio
async def test_product_hunt_adapter_breaks_on_limit() -> None:
    """Product Hunt adapter stops fetching when limit is reached."""
    adapter = ProductHuntAdapter(config={"topics": ["topic1", "topic2", "topic3"]})

    # First topic returns 3 posts, second returns 2, third shouldn't be queried
    call_count = 0

    async def mock_post(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            return MagicMock(
                json=lambda: {
                    "data": {
                        "topic": {
                            "posts": {
                                "edges": [
                                    {"node": {**MOCK_GRAPHQL_POST_1, "id": "post-1"}},
                                    {"node": {**MOCK_GRAPHQL_POST_1, "id": "post-2"}},
                                    {"node": {**MOCK_GRAPHQL_POST_1, "id": "post-3"}},
                                ]
                            }
                        }
                    }
                },
                raise_for_status=lambda: None,
            )
        elif call_count == 2:
            return MagicMock(
                json=lambda: {
                    "data": {
                        "topic": {
                            "posts": {
                                "edges": [
                                    {"node": {**MOCK_GRAPHQL_POST_1, "id": "post-4"}},
                                    {"node": {**MOCK_GRAPHQL_POST_1, "id": "post-5"}},
                                ]
                            }
                        }
                    }
                },
                raise_for_status=lambda: None,
            )
        else:
            # Third topic shouldn't be queried if limit is reached
            pytest.fail("Should not query third topic when limit is reached")

    with patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "test_token_123"}):
        with patch("max.sources.product_hunt.fetch_with_retry", mock_post):
            signals = await adapter.fetch(limit=5)

    assert len(signals) == 5
    assert call_count == 2  # Only first two topics queried
