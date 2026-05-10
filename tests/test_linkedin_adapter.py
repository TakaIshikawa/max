"""Tests for the LinkedIn source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.imports.linkedin_adapter import LinkedInAdapter, _extract_tags, _parse_timestamp
from max.sources.base import AdapterFetchError
from max.types.signal import SignalSourceType


MOCK_POSTS_RESPONSE = {
    "elements": [
        {
            "id": "urn:li:share:1234567890",
            "commentary": "Excited to announce our new AI-powered developer tools platform. #AI #DevTools",
            "author": {"name": "Jane Smith"},
            "url": "https://www.linkedin.com/feed/update/urn:li:share:1234567890",
            "likeCount": 150,
            "commentCount": 25,
            "shareCount": 10,
            "publishedAt": 1714003200000,
        },
        {
            "id": "urn:li:share:9876543210",
            "commentary": "The future of cloud native development is here. Kubernetes adoption continues to grow.",
            "author": {"name": "Bob Chen"},
            "url": "https://www.linkedin.com/feed/update/urn:li:share:9876543210",
            "likeCount": 80,
            "commentCount": 12,
            "shareCount": 5,
            "publishedAt": "2024-04-25T10:00:00Z",
        },
        {
            "id": "urn:li:share:empty",
            "commentary": "",
            "author": {"name": "No Content"},
        },
    ]
}

MOCK_JOBS_RESPONSE = {
    "elements": [
        {
            "id": "job-001",
            "title": "Senior Machine Learning Engineer",
            "description": "We are looking for an experienced ML engineer to join our AI team. Must have experience with LLMs and cloud infrastructure.",
            "company": {"name": "TechCorp"},
            "location": "San Francisco, CA",
            "skills": ["Python", "PyTorch", "Kubernetes", "LLMs"],
            "url": "https://www.linkedin.com/jobs/view/job-001",
            "postedAt": 1714089600000,
        },
        {
            "id": "job-002",
            "title": "DevOps Engineer",
            "description": "Join our SRE team to build and maintain cloud infrastructure.",
            "company": {"name": "CloudStart"},
            "location": "Remote",
            "skills": ["AWS", "Terraform", "Docker"],
            "postedAt": "2024-04-26T08:00:00Z",
        },
        {
            "id": "job-003",
            "title": "",
            "description": "No title job",
            "company": {"name": "BadCo"},
        },
    ]
}


def test_linkedin_adapter_properties() -> None:
    adapter = LinkedInAdapter()

    assert adapter.name == "linkedin"
    assert adapter.source_type == SignalSourceType.MARKET.value
    assert "artificial intelligence" in adapter.keywords


def test_linkedin_adapter_config_overrides() -> None:
    adapter = LinkedInAdapter(
        config={
            "keywords": ["rust", "golang"],
            "watchlist_terms": ["wasm"],
            "access_token": "test-token-123",
        }
    )

    assert adapter.keywords == ["rust", "golang", "wasm"]
    assert adapter._access_token == "test-token-123"


def test_linkedin_adapter_auth_headers() -> None:
    adapter = LinkedInAdapter(config={"access_token": "my-token"})
    headers = adapter._auth_headers()

    assert headers["Authorization"] == "Bearer my-token"
    assert "X-Restli-Protocol-Version" in headers
    assert "LinkedIn-Version" in headers


def test_linkedin_adapter_auth_headers_no_token() -> None:
    adapter = LinkedInAdapter()
    headers = adapter._auth_headers()

    assert "Authorization" not in headers
    assert "X-Restli-Protocol-Version" in headers


@pytest.mark.asyncio
async def test_linkedin_fetch_posts() -> None:
    adapter = LinkedInAdapter(config={"keywords": ["ai"]})

    with patch("max.imports.linkedin_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_POSTS_RESPONSE)

        signals = await adapter._fetch_posts(limit=10)

    assert len(signals) == 2  # third element has empty commentary, skipped
    assert mock_fetch.call_count == 1

    first = signals[0]
    assert first.source_type == SignalSourceType.MARKET
    assert first.source_adapter == "linkedin"
    assert "AI-powered developer tools" in first.title
    assert first.url == "https://www.linkedin.com/feed/update/urn:li:share:1234567890"
    assert first.author == "Jane Smith"
    assert first.published_at == datetime(2024, 4, 25, 0, 0, tzinfo=timezone.utc)
    assert first.metadata["like_count"] == 150
    assert first.metadata["comment_count"] == 25
    assert first.metadata["share_count"] == 10
    assert first.metadata["content_type"] == "post"
    assert first.metadata["search_keyword"] == "ai"
    assert first.credibility == pytest.approx(min((150 + 25 * 2 + 10 * 3) / 500, 1.0))


@pytest.mark.asyncio
async def test_linkedin_fetch_jobs() -> None:
    adapter = LinkedInAdapter(config={"keywords": ["machine learning"]})

    with patch("max.imports.linkedin_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_JOBS_RESPONSE)

        signals = await adapter._fetch_jobs(limit=10)

    assert len(signals) == 2  # third element has empty title, skipped
    assert mock_fetch.call_count == 1

    first = signals[0]
    assert first.source_type == SignalSourceType.MARKET
    assert first.source_adapter == "linkedin"
    assert "[Job]" in first.title
    assert "Senior Machine Learning Engineer" in first.title
    assert "TechCorp" in first.title
    assert first.url == "https://www.linkedin.com/jobs/view/job-001"
    assert first.author == "TechCorp"
    assert first.metadata["company"] == "TechCorp"
    assert first.metadata["location"] == "San Francisco, CA"
    assert first.metadata["skills"] == ["Python", "PyTorch", "Kubernetes", "LLMs"]
    assert first.metadata["content_type"] == "job"
    assert first.credibility == 0.7


@pytest.mark.asyncio
async def test_linkedin_fetch_combined() -> None:
    adapter = LinkedInAdapter(config={"keywords": ["ai"]})

    with patch("max.imports.linkedin_adapter.fetch_with_retry") as mock_fetch:
        # First call is posts, second is jobs
        mock_fetch.side_effect = [
            MagicMock(json=lambda: MOCK_POSTS_RESPONSE),
            MagicMock(json=lambda: MOCK_JOBS_RESPONSE),
        ]

        signals = await adapter.fetch(limit=30)

    assert len(signals) == 4  # 2 posts + 2 jobs
    assert mock_fetch.call_count == 2


@pytest.mark.asyncio
async def test_linkedin_fetch_handles_api_errors() -> None:
    adapter = LinkedInAdapter(config={"keywords": ["ai", "devops"]})

    with patch("max.imports.linkedin_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = AdapterFetchError("linkedin", 429, "https://api.linkedin.com/v2/posts")

        signals = await adapter._fetch_posts(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_linkedin_fetch_handles_malformed_response() -> None:
    adapter = LinkedInAdapter(config={"keywords": ["ai"]})

    with patch("max.imports.linkedin_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"unexpected": "format"})

        signals = await adapter._fetch_posts(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_linkedin_fetch_respects_limit() -> None:
    adapter = LinkedInAdapter(config={"keywords": ["ai"]})

    with patch("max.imports.linkedin_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_POSTS_RESPONSE)

        signals = await adapter._fetch_posts(limit=1)

    assert len(signals) == 1


def test_parse_timestamp_epoch_ms() -> None:
    result = _parse_timestamp(1714003200000)
    assert result == datetime(2024, 4, 25, 0, 0, tzinfo=timezone.utc)


def test_parse_timestamp_iso_string() -> None:
    result = _parse_timestamp("2024-04-25T10:00:00Z")
    assert result == datetime(2024, 4, 25, 10, 0, tzinfo=timezone.utc)


def test_parse_timestamp_none() -> None:
    assert _parse_timestamp(None) is None


def test_parse_timestamp_invalid() -> None:
    assert _parse_timestamp("not-a-date") is None


def test_extract_tags_basic() -> None:
    tags = _extract_tags("Building AI tools with machine learning", "artificial intelligence")
    assert "linkedin" in tags
    assert "artificial-intelligence" in tags
    assert "ai" in tags


def test_extract_tags_cloud() -> None:
    tags = _extract_tags("Deploying to Kubernetes on AWS", "cloud native")
    assert "linkedin" in tags
    assert "cloud-native" in tags
    assert "cloud" in tags


