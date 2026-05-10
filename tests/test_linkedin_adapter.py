"""Tests for LinkedIn source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.imports.linkedin_adapter import (
    LinkedInAdapter,
    _engagement_credibility,
    _extract_skills_from_job,
    _extract_tags,
    _parse_timestamp,
    _title_from_text,
)
from max.sources.base import AdapterFetchError, SourceAdapter
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────

MOCK_POSTS_RESPONSE = {
    "elements": [
        {
            "id": "urn:li:share:7001",
            "commentary": {"text": "Excited about the latest AI agent developments with MCP!"},
            "likeCount": 150,
            "commentCount": 25,
            "shareCount": 10,
            "author": {"name": "Alice Engineer"},
            "created": {"time": 1712764800000},
        },
        {
            "id": "urn:li:share:7002",
            "commentary": {"text": "Python 4.0 type system changes are a game changer for developer tools."},
            "likeCount": 300,
            "commentCount": 50,
            "shareCount": 30,
            "author": {"name": "Bob Dev"},
            "created": {"time": 1712851200000},
        },
    ],
}

MOCK_JOBS_RESPONSE = {
    "elements": [
        {
            "id": "job_001",
            "title": "Senior AI Engineer",
            "companyName": "TechCorp",
            "location": "Remote",
            "description": {"text": "Looking for expertise in Python, Kubernetes, and Docker for AI infrastructure."},
            "listedAt": 1712764800000,
        },
    ],
}


# ── Unit Tests: _extract_tags ────────────────────────────────────────


class TestExtractTags:
    def test_includes_linkedin(self) -> None:
        tags = _extract_tags("some text", "keyword")
        assert "linkedin" in tags

    def test_includes_keyword_tag(self) -> None:
        tags = _extract_tags("text", "artificial intelligence")
        assert "artificial-intelligence" in tags

    def test_keyword_detection(self) -> None:
        tags = _extract_tags("AI and machine learning trends", "tech")
        assert "ai" in tags
        assert "ml" in tags

    def test_limits_to_10(self) -> None:
        text = "ai llm mcp agent devops cloud security python typescript rust golang open source"
        tags = _extract_tags(text, "everything")
        assert len(tags) <= 10


# ── Unit Tests: _parse_timestamp ─────────────────────────────────────


class TestParseTimestamp:
    def test_valid_timestamp(self) -> None:
        dt = _parse_timestamp(1712764800000)
        assert dt is not None
        assert dt.year >= 2024

    def test_none_input(self) -> None:
        assert _parse_timestamp(None) is None

    def test_non_numeric(self) -> None:
        assert _parse_timestamp("not a number") is None  # type: ignore[arg-type]


# ── Unit Tests: _title_from_text ─────────────────────────────────────


class TestTitleFromText:
    def test_short_text(self) -> None:
        assert _title_from_text("Hello world") == "Hello world"

    def test_long_text_truncated(self) -> None:
        text = "x" * 200
        title = _title_from_text(text)
        assert len(title) <= 100
        assert title.endswith("...")


# ── Unit Tests: _engagement_credibility ──────────────────────────────


class TestEngagementCredibility:
    def test_zero_engagement(self) -> None:
        assert _engagement_credibility(0, 0, 0) == pytest.approx(0.1)

    def test_high_engagement_caps_at_1(self) -> None:
        assert _engagement_credibility(10000, 5000, 1000) == 1.0

    def test_moderate_engagement(self) -> None:
        # 150 + (25*2) + (10*3) = 230 -> 0.1 + 230/200 = 1.25 -> capped at 1.0
        cred = _engagement_credibility(150, 25, 10)
        assert cred == 1.0


# ── Unit Tests: _extract_skills_from_job ─────────────────────────────


class TestExtractSkillsFromJob:
    def test_extracts_skills(self) -> None:
        job = {"description": {"text": "Must know Python, Kubernetes, and Docker."}}
        skills = _extract_skills_from_job(job)
        assert "python" in skills
        assert "kubernetes" in skills
        assert "docker" in skills

    def test_string_description(self) -> None:
        job = {"description": "Looking for React and Node.js developers."}
        skills = _extract_skills_from_job(job)
        assert "react" in skills
        assert "node" in skills

    def test_empty_description(self) -> None:
        job = {}
        skills = _extract_skills_from_job(job)
        assert skills == []

    def test_limits_to_10(self) -> None:
        job = {
            "description": {
                "text": "python typescript javascript rust golang java kubernetes docker aws gcp azure terraform react node django fastapi flask"
            }
        }
        skills = _extract_skills_from_job(job)
        assert len(skills) <= 10


# ── Adapter Property Tests ───────────────────────────────────────────


class TestLinkedInAdapterProperties:
    def test_name(self) -> None:
        assert LinkedInAdapter().name == "linkedin"

    def test_source_type(self) -> None:
        assert LinkedInAdapter().source_type == SignalSourceType.FORUM.value

    def test_inherits_from_source_adapter(self) -> None:
        assert isinstance(LinkedInAdapter(), SourceAdapter)

    def test_default_keywords(self) -> None:
        a = LinkedInAdapter()
        assert "artificial intelligence" in a.keywords

    def test_config_overrides(self) -> None:
        a = LinkedInAdapter(config={"keywords": ["rust", "wasm"]})
        assert a.keywords == ["rust", "wasm"]

    def test_access_token_env_default(self) -> None:
        assert LinkedInAdapter().access_token_env == "LINKEDIN_ACCESS_TOKEN"

    def test_include_jobs_default(self) -> None:
        assert LinkedInAdapter().include_jobs is True

    def test_include_jobs_disabled(self) -> None:
        a = LinkedInAdapter(config={"include_jobs": False})
        assert a.include_jobs is False


# ── Adapter Fetch Tests ──────────────────────────────────────────────


class TestLinkedInAdapterFetch:
    @pytest.mark.asyncio
    async def test_fetch_returns_empty_without_token(self) -> None:
        adapter = LinkedInAdapter()

        with patch.dict("os.environ", {}, clear=True):
            signals = await adapter.fetch(limit=10)

        assert signals == []

    @pytest.mark.asyncio
    async def test_fetch_parses_posts(self) -> None:
        adapter = LinkedInAdapter(config={"keywords": ["ai"], "include_jobs": False})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_POSTS_RESPONSE
        mock_resp.status_code = 200

        with patch.dict("os.environ", {"LINKEDIN_ACCESS_TOKEN": "test-token"}):
            with patch(
                "max.imports.linkedin_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 2
        assert signals[0].source_adapter == "linkedin"
        assert signals[0].source_type == SignalSourceType.FORUM
        assert "AI agent" in signals[0].title
        assert signals[0].author == "Alice Engineer"
        assert signals[0].metadata["post_id"] == "urn:li:share:7001"
        assert signals[0].metadata["likes"] == 150

    @pytest.mark.asyncio
    async def test_fetch_parses_jobs(self) -> None:
        adapter = LinkedInAdapter(config={"keywords": ["ai"], "include_jobs": True})

        mock_posts_resp = MagicMock()
        mock_posts_resp.json.return_value = {"elements": []}
        mock_posts_resp.status_code = 200

        mock_jobs_resp = MagicMock()
        mock_jobs_resp.json.return_value = MOCK_JOBS_RESPONSE
        mock_jobs_resp.status_code = 200

        with patch.dict("os.environ", {"LINKEDIN_ACCESS_TOKEN": "test-token"}):
            with patch(
                "max.imports.linkedin_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                side_effect=[mock_posts_resp, mock_jobs_resp],
            ):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 1
        assert signals[0].source_type == SignalSourceType.MARKET
        assert "Senior AI Engineer" in signals[0].title
        assert "TechCorp" in signals[0].title
        assert signals[0].metadata["company"] == "TechCorp"
        assert "python" in signals[0].metadata["skills"]

    @pytest.mark.asyncio
    async def test_fetch_respects_limit(self) -> None:
        adapter = LinkedInAdapter(config={"keywords": ["ai"], "include_jobs": False})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_POSTS_RESPONSE
        mock_resp.status_code = 200

        with patch.dict("os.environ", {"LINKEDIN_ACCESS_TOKEN": "test-token"}):
            with patch(
                "max.imports.linkedin_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ):
                signals = await adapter.fetch(limit=1)

        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_fetch_deduplicates_posts(self) -> None:
        adapter = LinkedInAdapter(config={"keywords": ["ai", "ml"], "include_jobs": False})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_POSTS_RESPONSE
        mock_resp.status_code = 200

        with patch.dict("os.environ", {"LINKEDIN_ACCESS_TOKEN": "test-token"}):
            with patch(
                "max.imports.linkedin_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ):
                signals = await adapter.fetch(limit=10)

        # Same posts returned for both keywords, dedup by post_id
        assert len(signals) == 2


# ── Error Handling Tests ─────────────────────────────────────────────


class TestLinkedInAdapterErrors:
    @pytest.mark.asyncio
    async def test_fetch_continues_on_error(self) -> None:
        adapter = LinkedInAdapter(config={"keywords": ["bad", "good"], "include_jobs": False})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_POSTS_RESPONSE
        mock_resp.status_code = 200

        with patch.dict("os.environ", {"LINKEDIN_ACCESS_TOKEN": "test-token"}):
            with patch(
                "max.imports.linkedin_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                side_effect=[AdapterFetchError("linkedin", 500, "url"), mock_resp],
            ):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 2

    @pytest.mark.asyncio
    async def test_fetch_all_fail_returns_empty(self) -> None:
        adapter = LinkedInAdapter(config={"keywords": ["fail"], "include_jobs": False})

        with patch.dict("os.environ", {"LINKEDIN_ACCESS_TOKEN": "test-token"}):
            with patch(
                "max.imports.linkedin_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                side_effect=AdapterFetchError("linkedin", 503, "url"),
            ):
                signals = await adapter.fetch(limit=10)

        assert signals == []

    @pytest.mark.asyncio
    async def test_fetch_handles_non_dict_response(self) -> None:
        adapter = LinkedInAdapter(config={"keywords": ["test"], "include_jobs": False})

        mock_resp = MagicMock()
        mock_resp.json.return_value = "not a dict"
        mock_resp.status_code = 200

        with patch.dict("os.environ", {"LINKEDIN_ACCESS_TOKEN": "test-token"}):
            with patch(
                "max.imports.linkedin_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ):
                signals = await adapter.fetch(limit=10)

        assert signals == []
