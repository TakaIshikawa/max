"""Tests for Stack Overflow import adapter — Q&A signal collection."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.imports.stackoverflow_adapter import (
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
            "body": "<p>I'm trying to connect <b>LangChain</b> agents to MCP servers.</p>",
            "link": "https://stackoverflow.com/questions/101",
            "tags": ["python", "langchain", "mcp"],
            "score": 45,
            "view_count": 1200,
            "answer_count": 2,
            "is_answered": True,
            "accepted_answer_id": 1001,
            "creation_date": 1713100000,
            "owner": {"display_name": "dev_user"},
        },
        {
            "question_id": 102,
            "title": "OpenAI embeddings vs Anthropic embeddings for RAG?",
            "body": "<p>What are the trade-offs?</p>",
            "link": "https://stackoverflow.com/questions/102",
            "tags": ["openai", "anthropic", "embedding", "rag"],
            "score": 120,
            "view_count": 5000,
            "answer_count": 5,
            "is_answered": True,
            "creation_date": 1713200000,
            "owner": {"display_name": "ml_engineer"},
        },
    ],
    "quota_remaining": 9500,
}

MOCK_SE_EMPTY = {"items": [], "quota_remaining": 9999}


def _mock_response(payload: dict, *, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = payload
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


# ── Unit tests ───────────────────────────────────────────────────────


def test_strip_html() -> None:
    assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_strip_html_empty() -> None:
    assert _strip_html("") == ""


def test_extract_tags_includes_so_tags() -> None:
    tags = _extract_tags("Some title", ["python", "langchain"])
    assert "python" in tags
    assert "langchain" in tags
    assert "stackoverflow" in tags


def test_extract_tags_keyword_matching() -> None:
    tags = _extract_tags("How to build an LLM agent with RAG", [])
    assert "llm" in tags
    assert "agent" in tags
    assert "rag" in tags


# ── Adapter property tests ───────────────────────────────────────────


def test_adapter_name() -> None:
    adapter = StackOverflowAdapter()
    assert adapter.name == "stackoverflow_import"


def test_adapter_source_type() -> None:
    adapter = StackOverflowAdapter()
    assert adapter.source_type == SignalSourceType.FORUM.value


def test_adapter_default_tags() -> None:
    adapter = StackOverflowAdapter()
    assert "langchain" in adapter.tags
    assert "llm" in adapter.tags


def test_adapter_custom_tags() -> None:
    adapter = StackOverflowAdapter(config={"tags": ["react", "nextjs"]})
    assert adapter.tags == ["react", "nextjs"]


def test_adapter_min_score_default() -> None:
    adapter = StackOverflowAdapter()
    assert adapter.min_score == 5


def test_adapter_min_score_custom() -> None:
    adapter = StackOverflowAdapter(config={"min_score": 20})
    assert adapter.min_score == 20


# ── Fetch tests with mocked API ─────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_parses_questions() -> None:
    adapter = StackOverflowAdapter(config={"tags": ["python"]})

    with patch(
        "max.imports.stackoverflow_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_SE_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    sig = signals[0]
    assert sig.title == "How to use LangChain with MCP servers?"
    assert sig.source_adapter == "stackoverflow_import"
    assert sig.source_type == SignalSourceType.FORUM
    assert sig.url == "https://stackoverflow.com/questions/101"
    assert sig.author == "dev_user"
    assert sig.metadata["question_id"] == 101
    assert sig.metadata["score"] == 45
    assert sig.metadata["view_count"] == 1200
    assert sig.metadata["answer_count"] == 2
    assert sig.metadata["is_answered"] is True
    assert sig.metadata["has_accepted_answer"] is True


@pytest.mark.asyncio
async def test_fetch_respects_limit() -> None:
    adapter = StackOverflowAdapter(config={"tags": ["python"]})

    with patch(
        "max.imports.stackoverflow_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_SE_RESPONSE)
        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_deduplicates() -> None:
    dup_response = {
        "items": [MOCK_SE_RESPONSE["items"][0], MOCK_SE_RESPONSE["items"][0]],
        "quota_remaining": 9000,
    }
    adapter = StackOverflowAdapter(config={"tags": ["python"]})

    with patch(
        "max.imports.stackoverflow_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(dup_response)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_handles_api_error() -> None:
    adapter = StackOverflowAdapter(config={"tags": ["python"]})

    with patch(
        "max.imports.stackoverflow_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.side_effect = Exception("API error")
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_empty_response() -> None:
    adapter = StackOverflowAdapter(config={"tags": ["python"]})

    with patch(
        "max.imports.stackoverflow_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_SE_EMPTY)
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_credibility_capped() -> None:
    high_score = {**MOCK_SE_RESPONSE["items"][0], "score": 50000}
    response = {"items": [high_score], "quota_remaining": 9000}
    adapter = StackOverflowAdapter(config={"tags": ["python"]})

    with patch(
        "max.imports.stackoverflow_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(response)
        signals = await adapter.fetch(limit=10)

    assert signals[0].credibility == 1.0
