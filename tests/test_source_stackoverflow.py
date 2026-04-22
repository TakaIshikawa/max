"""Tests for StackOverflow source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.stackoverflow import (
    StackOverflowAdapter,
    _extract_tags,
    _strip_html,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────


MOCK_SE_RESPONSE = {
    "items": [
        {
            "question_id": 101,
            "title": "How to use LangChain with MCP servers?",
            "body": "<p>I'm trying to connect <b>LangChain</b> agents to MCP servers but keep getting timeout errors.</p>",
            "link": "https://stackoverflow.com/questions/101",
            "tags": ["python", "langchain", "mcp"],
            "score": 45,
            "view_count": 1200,
            "answer_count": 2,
            "is_answered": True,
            "creation_date": 1713100000,
            "owner": {"display_name": "dev_user"},
        },
        {
            "question_id": 102,
            "title": "OpenAI embeddings vs Anthropic embeddings for RAG?",
            "body": "<p>What are the trade-offs between OpenAI and Anthropic embedding models for RAG pipelines?</p>",
            "link": "https://stackoverflow.com/questions/102",
            "tags": ["openai", "anthropic", "embedding", "rag"],
            "score": 120,
            "view_count": 5000,
            "answer_count": 5,
            "is_answered": True,
            "creation_date": 1713200000,
            "owner": {"display_name": "ml_engineer"},
        },
        {
            "question_id": 103,
            "title": "LLM agent keeps hallucinating tool calls",
            "body": "<p>My LLM agent generates invalid tool calls. How to constrain?</p>",
            "link": "https://stackoverflow.com/questions/103",
            "tags": ["llm", "ai-agent"],
            "score": 8,
            "view_count": 300,
            "answer_count": 0,
            "is_answered": False,
            "creation_date": 1713300000,
            "owner": {"display_name": "agent_builder"},
        },
    ],
    "quota_remaining": 9500,
}


# ── Unit Tests ────────────────────────────────────────────────────────


class TestStripHtml:
    def test_removes_tags(self) -> None:
        assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_collapses_whitespace(self) -> None:
        assert _strip_html("<p>Hello</p>\n\n<p>World</p>") == "Hello World"

    def test_empty_string(self) -> None:
        assert _strip_html("") == ""


class TestExtractTags:
    def test_includes_so_tags(self) -> None:
        tags = _extract_tags("some title", ["python", "langchain", "mcp"])
        assert "python" in tags
        assert "langchain" in tags
        assert "mcp" in tags

    def test_extracts_keywords_from_title(self) -> None:
        tags = _extract_tags("How to build RAG with embedding models", [])
        assert "rag" in tags
        assert "embedding" in tags

    def test_always_includes_stackoverflow_tag(self) -> None:
        tags = _extract_tags("random title", [])
        assert "stackoverflow" in tags

    def test_limits_to_10(self) -> None:
        so_tags = [f"tag-{i}" for i in range(15)]
        tags = _extract_tags("llm agent mcp rag embedding", so_tags)
        assert len(tags) <= 10


# ── Adapter Tests ────────────────────────────────────────────────────


class TestStackOverflowAdapter:
    def test_name(self) -> None:
        adapter = StackOverflowAdapter()
        assert adapter.name == "stackoverflow"

    def test_source_type(self) -> None:
        adapter = StackOverflowAdapter()
        assert adapter.source_type == SignalSourceType.FORUM.value

    def test_config_defaults(self) -> None:
        adapter = StackOverflowAdapter()
        assert adapter.min_score == 5
        assert adapter.unanswered_only is False

    def test_config_overrides(self) -> None:
        adapter = StackOverflowAdapter(config={
            "tags": ["rust", "wasm"],
            "min_score": 10,
            "unanswered_only": True,
        })
        assert adapter.tags == ["rust", "wasm"]
        assert adapter.min_score == 10
        assert adapter.unanswered_only is True

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_fetch_parses_questions(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={"tags": ["langchain", "mcp"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_SE_RESPONSE
        mock_resp.status_code = 200

        with patch("max.sources.stackoverflow.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert len(signals) == 3
        assert signals[0].source_adapter == "stackoverflow"
        assert signals[0].title == "How to use LangChain with MCP servers?"
        assert "langchain" in signals[0].tags
        assert signals[0].metadata["question_id"] == 101

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_fetch_credibility_from_score(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={"tags": ["test"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_SE_RESPONSE
        mock_resp.status_code = 200

        with patch("max.sources.stackoverflow.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        # score=45 → 45/200 = 0.225
        assert signals[0].credibility == pytest.approx(0.225)
        # score=120 → 120/200 = 0.6
        assert signals[1].credibility == pytest.approx(0.6)

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_fetch_respects_limit(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={"tags": ["test"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_SE_RESPONSE
        mock_resp.status_code = 200

        with patch("max.sources.stackoverflow.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=2)

        assert len(signals) == 2

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_fetch_deduplicates_across_batches(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={"tags": ["a", "b", "c", "d", "e", "f"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_SE_RESPONSE
        mock_resp.status_code = 200

        with patch("max.sources.stackoverflow.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        # Same response returned for both batches, dedup by question_id
        assert len(signals) == 3

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_fetch_strips_html_from_body(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={"tags": ["test"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_SE_RESPONSE
        mock_resp.status_code = 200

        with patch("max.sources.stackoverflow.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=1)

        # HTML tags should be stripped from content
        assert "<p>" not in signals[0].content
        assert "<b>" not in signals[0].content
        assert "LangChain" in signals[0].content

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value="test-key")
    async def test_fetch_passes_api_key(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={"tags": ["test"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"items": [], "quota_remaining": 9999}
        mock_resp.status_code = 200

        with patch("max.sources.stackoverflow.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp) as mock_fetch:
            await adapter.fetch(limit=5)

        # Check that api key was included in params
        call_kwargs = mock_fetch.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params", {})
        assert params.get("key") == "test-key"
