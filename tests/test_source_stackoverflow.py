"""Comprehensive tests for StackOverflow source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.base import (
    AdapterCircuitOpenError,
    AdapterFetchError,
    AdapterRateLimitError,
    SourceAdapter,
)
from max.sources.stackoverflow import (
    StackOverflowAdapter,
    _build_answer_metadata,
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
            "accepted_answer_id": 1001,
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

MOCK_SE_EMPTY = {
    "items": [],
    "quota_remaining": 9999,
}

MOCK_SE_NO_OWNER = {
    "items": [
        {
            "question_id": 201,
            "title": "Anonymous question about agents",
            "body": "<p>Some body text.</p>",
            "link": "https://stackoverflow.com/questions/201",
            "tags": ["llm"],
            "score": 10,
            "view_count": 50,
            "answer_count": 0,
            "is_answered": False,
            "creation_date": 1713400000,
        },
    ],
    "quota_remaining": 9000,
}


# ── Unit Tests: _strip_html ─────────────────────────────────────────


class TestStripHtml:
    def test_removes_tags(self) -> None:
        assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_collapses_whitespace(self) -> None:
        assert _strip_html("<p>Hello</p>\n\n<p>World</p>") == "Hello World"

    def test_empty_string(self) -> None:
        assert _strip_html("") == ""

    def test_no_html(self) -> None:
        assert _strip_html("plain text") == "plain text"

    def test_nested_tags(self) -> None:
        result = _strip_html("<div><p>nested <em>text</em></p></div>")
        assert "nested" in result
        assert "text" in result
        assert "<" not in result


# ── Unit Tests: _extract_tags ────────────────────────────────────────


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

    def test_lowercases_tags(self) -> None:
        tags = _extract_tags("title", ["Python", "LangChain"])
        assert "python" in tags
        assert "langchain" in tags

    def test_keyword_openai(self) -> None:
        tags = _extract_tags("Using OpenAI API", [])
        assert "openai" in tags

    def test_keyword_anthropic(self) -> None:
        tags = _extract_tags("Anthropic Claude integration", [])
        assert "anthropic" in tags
        assert "claude" in tags

    def test_keyword_vector(self) -> None:
        tags = _extract_tags("Vector database comparison", [])
        assert "vector" in tags


# ── Unit Tests: _build_answer_metadata ───────────────────────────────


class TestBuildAnswerMetadata:
    def test_empty_answers(self) -> None:
        meta = _build_answer_metadata([], None)
        assert meta["has_accepted_answer"] is False
        assert meta["accepted_answer_id"] is None
        assert meta["answer_excerpts"] == []
        assert meta["top_answer"] is None

    def test_with_accepted_answer(self) -> None:
        answers = [
            {
                "answer_id": 1001,
                "score": 10,
                "is_accepted": True,
                "body": "<p>Accepted answer body.</p>",
                "owner": {"display_name": "helper"},
            }
        ]
        meta = _build_answer_metadata(answers, 1001)
        assert meta["has_accepted_answer"] is True
        assert meta["accepted_answer_id"] == 1001
        assert len(meta["answer_excerpts"]) == 1
        assert meta["answer_excerpts"][0]["is_accepted"] is True
        assert meta["top_answer"]["answer_id"] == 1001

    def test_top_answer_by_score(self) -> None:
        answers = [
            {"answer_id": 10, "score": 5, "is_accepted": False, "body": "<p>Low.</p>", "owner": {"display_name": "a"}},
            {"answer_id": 20, "score": 50, "is_accepted": False, "body": "<p>High.</p>", "owner": {"display_name": "b"}},
        ]
        meta = _build_answer_metadata(answers, None)
        assert meta["top_answer"]["answer_id"] == 20
        assert meta["top_answer"]["score"] == 50

    def test_discovers_accepted_from_flag(self) -> None:
        """When accepted_answer_id is None but an answer has is_accepted=True."""
        answers = [
            {"answer_id": 99, "score": 3, "is_accepted": True, "body": "<p>ok</p>", "owner": {"display_name": "x"}},
        ]
        meta = _build_answer_metadata(answers, None)
        assert meta["has_accepted_answer"] is True
        assert meta["accepted_answer_id"] == 99

    def test_strips_html_in_excerpts(self) -> None:
        answers = [
            {"answer_id": 1, "score": 1, "is_accepted": False, "body": "<p>Clean <b>text</b>.</p>", "owner": {"display_name": "a"}},
        ]
        meta = _build_answer_metadata(answers, None)
        assert "<p>" not in meta["answer_excerpts"][0]["excerpt"]
        assert "<b>" not in meta["answer_excerpts"][0]["excerpt"]


# ── Adapter Property Tests ───────────────────────────────────────────


class TestStackOverflowAdapterProperties:
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
        assert adapter.include_answers is False
        assert adapter.max_answers_per_question == 2

    def test_config_overrides(self) -> None:
        adapter = StackOverflowAdapter(config={
            "tags": ["rust", "wasm"],
            "min_score": 10,
            "unanswered_only": True,
            "include_answers": True,
            "max_answers_per_question": 4,
        })
        assert adapter.tags == ["rust", "wasm"]
        assert adapter.min_score == 10
        assert adapter.unanswered_only is True
        assert adapter.include_answers is True
        assert adapter.max_answers_per_question == 4

    def test_inherits_from_source_adapter(self) -> None:
        assert isinstance(StackOverflowAdapter(), SourceAdapter)

    def test_no_config(self) -> None:
        adapter = StackOverflowAdapter()
        assert adapter._config == {}

    def test_max_answers_per_question_non_int_defaults(self) -> None:
        """Non-integer value for max_answers_per_question defaults to 2."""
        adapter = StackOverflowAdapter(config={"max_answers_per_question": "invalid"})
        assert adapter.max_answers_per_question == 2

    def test_max_answers_per_question_bool_defaults(self) -> None:
        """Bool value for max_answers_per_question defaults to 2."""
        adapter = StackOverflowAdapter(config={"max_answers_per_question": True})
        assert adapter.max_answers_per_question == 2

    def test_max_answers_per_question_negative_clamped(self) -> None:
        """Negative value for max_answers_per_question is clamped to 0."""
        adapter = StackOverflowAdapter(config={"max_answers_per_question": -1})
        assert adapter.max_answers_per_question == 0


# ── Adapter Fetch Tests ──────────────────────────────────────────────


class TestStackOverflowAdapterFetch:
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
        assert signals[0].source_type == SignalSourceType.FORUM
        assert signals[0].title == "How to use LangChain with MCP servers?"
        assert "langchain" in signals[0].tags
        assert signals[0].metadata["question_id"] == 101
        assert signals[0].metadata["answer_count"] == 2
        assert signals[0].metadata["has_accepted_answer"] is True
        assert signals[0].metadata["answer_excerpts"] == []
        assert signals[0].metadata["top_answer"] is None

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_fetch_credibility_from_score(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={"tags": ["test"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_SE_RESPONSE
        mock_resp.status_code = 200

        with patch("max.sources.stackoverflow.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        # score=45 -> 45/200 = 0.225
        assert signals[0].credibility == pytest.approx(0.225)
        # score=120 -> 120/200 = 0.6
        assert signals[1].credibility == pytest.approx(0.6)
        # score=8 -> 8/200 = 0.04
        assert signals[2].credibility == pytest.approx(0.04)

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_fetch_credibility_caps_at_1(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={"tags": ["test"]})

        high_score_response = {
            "items": [{
                "question_id": 999,
                "title": "Very popular question",
                "body": "<p>body</p>",
                "link": "https://stackoverflow.com/questions/999",
                "tags": ["test"],
                "score": 500,
                "view_count": 10000,
                "answer_count": 10,
                "is_answered": True,
                "creation_date": 1713100000,
                "owner": {"display_name": "user"},
            }],
            "quota_remaining": 9000,
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = high_score_response
        mock_resp.status_code = 200

        with patch("max.sources.stackoverflow.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        # score=500 -> min(500/200, 1.0) = 1.0
        assert signals[0].credibility == pytest.approx(1.0)

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
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_fetch_body_truncated_to_1000(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={"tags": ["test"]})

        long_body_response = {
            "items": [{
                "question_id": 301,
                "title": "Long question",
                "body": f"<p>{'x' * 3000}</p>",
                "link": "https://stackoverflow.com/questions/301",
                "tags": ["test"],
                "score": 10,
                "view_count": 100,
                "answer_count": 0,
                "is_answered": False,
                "creation_date": 1713100000,
                "owner": {"display_name": "user"},
            }],
            "quota_remaining": 9000,
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = long_body_response
        mock_resp.status_code = 200

        with patch("max.sources.stackoverflow.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert len(signals[0].content) <= 1000

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value="test-key")
    async def test_fetch_passes_api_key(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={"tags": ["test"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_SE_EMPTY
        mock_resp.status_code = 200

        with patch("max.sources.stackoverflow.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp) as mock_fetch:
            await adapter.fetch(limit=5)

        # Check that api key was included in params
        call_kwargs = mock_fetch.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params", {})
        assert params.get("key") == "test-key"

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_fetch_missing_owner(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={"tags": ["test"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_SE_NO_OWNER
        mock_resp.status_code = 200

        with patch("max.sources.stackoverflow.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert len(signals) == 1
        assert signals[0].author is None

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_fetch_published_at_from_timestamp(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={"tags": ["test"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_SE_RESPONSE
        mock_resp.status_code = 200

        with patch("max.sources.stackoverflow.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=1)

        expected = datetime.fromtimestamp(1713100000, tz=timezone.utc)
        assert signals[0].published_at == expected

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_fetch_metadata_fields(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={"tags": ["test"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_SE_RESPONSE
        mock_resp.status_code = 200

        with patch("max.sources.stackoverflow.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=1)

        meta = signals[0].metadata
        assert meta["question_id"] == 101
        assert meta["score"] == 45
        assert meta["view_count"] == 1200
        assert meta["answer_count"] == 2
        assert meta["is_answered"] is True
        assert meta["has_accepted_answer"] is True
        assert meta["accepted_answer_id"] == 1001

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_fetch_calls_api_with_correct_params(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={"tags": ["langchain", "mcp"], "min_score": 10})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_SE_EMPTY
        mock_resp.status_code = 200

        with patch("max.sources.stackoverflow.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp) as mock_fetch:
            await adapter.fetch(limit=10)

        call_args = mock_fetch.call_args
        assert call_args.args[0] == "https://api.stackexchange.com/2.3/questions"
        params = call_args.kwargs.get("params") or call_args[1].get("params", {})
        assert params["tagged"] == "langchain;mcp"
        assert params["sort"] == "votes"
        assert params["site"] == "stackoverflow"
        assert params["filter"] == "withbody"
        assert params["min"] == 10
        assert call_args.kwargs.get("adapter_name") == "stackoverflow"

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_fetch_unanswered_only_param(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={"tags": ["test"], "unanswered_only": True})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_SE_EMPTY
        mock_resp.status_code = 200

        with patch("max.sources.stackoverflow.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp) as mock_fetch:
            await adapter.fetch(limit=10)

        params = mock_fetch.call_args.kwargs.get("params") or {}
        assert params.get("accepted") == "False"

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_fetch_empty_response(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={"tags": ["test"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_SE_EMPTY
        mock_resp.status_code = 200

        with patch("max.sources.stackoverflow.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert signals == []


# ── Answer Fetch Tests ───────────────────────────────────────────────


class TestStackOverflowAdapterAnswers:
    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_fetch_includes_answer_metadata_when_configured(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={
            "tags": ["langchain"],
            "include_answers": True,
            "max_answers_per_question": 2,
        })

        question_resp = MagicMock()
        question_resp.json.return_value = {"items": [MOCK_SE_RESPONSE["items"][0]]}

        answer_resp = MagicMock()
        answer_resp.json.return_value = {
            "items": [
                {
                    "answer_id": 1002,
                    "question_id": 101,
                    "body": "<p>Use an async MCP client and set an explicit timeout.</p>",
                    "score": 18,
                    "is_accepted": False,
                    "owner": {"display_name": "answerer"},
                },
                {
                    "answer_id": 1001,
                    "question_id": 101,
                    "body": "<p>The accepted fix is to keep one server session per agent.</p>",
                    "score": 12,
                    "is_accepted": True,
                    "owner": {"display_name": "maintainer"},
                },
            ]
        }

        with patch(
            "max.sources.stackoverflow.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[question_resp, answer_resp],
        ) as mock_fetch:
            signals = await adapter.fetch(limit=1)

        assert len(signals) == 1
        assert signals[0].content == "I'm trying to connect LangChain agents to MCP servers but keep getting timeout errors."
        assert "accepted fix" not in signals[0].content
        assert signals[0].metadata["has_accepted_answer"] is True
        assert signals[0].metadata["accepted_answer_id"] == 1001
        assert signals[0].metadata["answer_excerpts"] == [
            {
                "answer_id": 1002,
                "score": 18,
                "is_accepted": False,
                "author": "answerer",
                "excerpt": "Use an async MCP client and set an explicit timeout.",
            },
            {
                "answer_id": 1001,
                "score": 12,
                "is_accepted": True,
                "author": "maintainer",
                "excerpt": "The accepted fix is to keep one server session per agent.",
            },
        ]
        assert signals[0].metadata["top_answer"] == {
            "answer_id": 1002,
            "score": 18,
            "is_accepted": False,
            "author": "answerer",
        }

        answer_call = mock_fetch.call_args_list[1]
        assert answer_call.args[0] == "https://api.stackexchange.com/2.3/questions/101/answers"
        assert answer_call.kwargs["params"]["pagesize"] == 2

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_fetch_gets_accepted_answer_when_missing_from_top(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={
            "tags": ["langchain"],
            "include_answers": True,
            "max_answers_per_question": 1,
        })

        question_resp = MagicMock()
        question_resp.json.return_value = {"items": [MOCK_SE_RESPONSE["items"][0]]}

        top_answer_resp = MagicMock()
        top_answer_resp.json.return_value = {
            "items": [
                {
                    "answer_id": 1002,
                    "body": "<p>Top voted answer.</p>",
                    "score": 18,
                    "is_accepted": False,
                    "owner": {"display_name": "answerer"},
                }
            ]
        }

        accepted_answer_resp = MagicMock()
        accepted_answer_resp.json.return_value = {
            "items": [
                {
                    "answer_id": 1001,
                    "body": "<p>Accepted answer.</p>",
                    "score": 12,
                    "is_accepted": True,
                    "owner": {"display_name": "maintainer"},
                }
            ]
        }

        with patch(
            "max.sources.stackoverflow.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[question_resp, top_answer_resp, accepted_answer_resp],
        ) as mock_fetch:
            signals = await adapter.fetch(limit=1)

        assert [answer["answer_id"] for answer in signals[0].metadata["answer_excerpts"]] == [
            1002,
            1001,
        ]
        assert mock_fetch.call_args_list[2].args[0] == "https://api.stackexchange.com/2.3/answers/1001"

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_no_answers_fetched_when_disabled(self, _mock_key) -> None:
        """When include_answers=False, no answer API calls are made."""
        adapter = StackOverflowAdapter(config={
            "tags": ["test"],
            "include_answers": False,
        })

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_SE_RESPONSE
        mock_resp.status_code = 200

        with patch("max.sources.stackoverflow.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp) as mock_fetch:
            signals = await adapter.fetch(limit=10)

        # Only 1 call for questions, no answer calls
        assert mock_fetch.call_count == 1
        assert all(s.metadata["answer_excerpts"] == [] for s in signals)

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_no_answers_fetched_when_zero_answer_count(self, _mock_key) -> None:
        """No answer fetch when question has 0 answers."""
        adapter = StackOverflowAdapter(config={
            "tags": ["test"],
            "include_answers": True,
        })

        no_answer_response = {
            "items": [MOCK_SE_RESPONSE["items"][2]],  # answer_count=0
            "quota_remaining": 9000,
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = no_answer_response
        mock_resp.status_code = 200

        with patch("max.sources.stackoverflow.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp) as mock_fetch:
            signals = await adapter.fetch(limit=10)

        assert mock_fetch.call_count == 1
        assert signals[0].metadata["answer_excerpts"] == []


# ── Error Handling Tests ─────────────────────────────────────────────


class TestStackOverflowAdapterErrors:
    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_fetch_continues_on_batch_error(self, _mock_key) -> None:
        """Adapter continues with next batch when one fails."""
        adapter = StackOverflowAdapter(config={"tags": ["a", "b", "c", "d", "e", "f"]})

        mock_good_resp = MagicMock()
        mock_good_resp.json.return_value = MOCK_SE_RESPONSE
        mock_good_resp.status_code = 200

        with patch(
            "max.sources.stackoverflow.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[AdapterFetchError("stackoverflow", 500, "url"), mock_good_resp],
        ):
            signals = await adapter.fetch(limit=10)

        assert len(signals) == 3

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_fetch_continues_on_rate_limit(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={"tags": ["a", "b", "c", "d", "e", "f"]})

        mock_good_resp = MagicMock()
        mock_good_resp.json.return_value = MOCK_SE_RESPONSE
        mock_good_resp.status_code = 200

        with patch(
            "max.sources.stackoverflow.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[AdapterRateLimitError("stackoverflow", "url"), mock_good_resp],
        ):
            signals = await adapter.fetch(limit=10)

        assert len(signals) == 3

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_fetch_continues_on_circuit_open(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={"tags": ["a", "b", "c", "d", "e", "f"]})

        mock_good_resp = MagicMock()
        mock_good_resp.json.return_value = MOCK_SE_RESPONSE
        mock_good_resp.status_code = 200

        with patch(
            "max.sources.stackoverflow.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[AdapterCircuitOpenError("stackoverflow", retry_after=300.0), mock_good_resp],
        ):
            signals = await adapter.fetch(limit=10)

        assert len(signals) == 3

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_fetch_continues_on_timeout(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={"tags": ["a", "b", "c", "d", "e", "f"]})

        mock_good_resp = MagicMock()
        mock_good_resp.json.return_value = MOCK_SE_RESPONSE
        mock_good_resp.status_code = 200

        with patch(
            "max.sources.stackoverflow.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[httpx.TimeoutException("timeout"), mock_good_resp],
        ):
            signals = await adapter.fetch(limit=10)

        assert len(signals) == 3

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_fetch_all_batches_fail_returns_empty(self, _mock_key) -> None:
        adapter = StackOverflowAdapter(config={"tags": ["test"]})

        with patch(
            "max.sources.stackoverflow.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=AdapterFetchError("stackoverflow", 503, "url"),
        ):
            signals = await adapter.fetch(limit=10)

        assert signals == []

    @pytest.mark.asyncio
    @patch("max.sources.stackoverflow._get_api_key", return_value=None)
    async def test_answer_fetch_failure_continues(self, _mock_key) -> None:
        """When answer fetch fails, question signal is still created with empty answers."""
        adapter = StackOverflowAdapter(config={
            "tags": ["test"],
            "include_answers": True,
        })

        question_resp = MagicMock()
        question_resp.json.return_value = {"items": [MOCK_SE_RESPONSE["items"][0]]}

        with patch(
            "max.sources.stackoverflow.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[question_resp, AdapterFetchError("stackoverflow", 500, "url")],
        ):
            signals = await adapter.fetch(limit=10)

        assert len(signals) == 1
        assert signals[0].metadata["answer_excerpts"] == []


# ── API Key Resolution Tests ────────────────────────────────────────


class TestGetApiKey:
    @patch.dict("os.environ", {"STACKEXCHANGE_KEY": "env-se-key"})
    def test_from_env(self) -> None:
        from max.sources.stackoverflow import _get_api_key
        assert _get_api_key() == "env-se-key"

    @patch.dict("os.environ", {}, clear=True)
    @patch("subprocess.run")
    def test_from_vault(self, mock_run) -> None:
        from max.sources.stackoverflow import _get_api_key
        mock_run.return_value = MagicMock(returncode=0, stdout="vault-se-key\n")
        assert _get_api_key() == "vault-se-key"

    @patch.dict("os.environ", {}, clear=True)
    @patch("subprocess.run")
    def test_vault_failure_returns_none(self, mock_run) -> None:
        from max.sources.stackoverflow import _get_api_key
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert _get_api_key() is None

    @patch.dict("os.environ", {}, clear=True)
    @patch("subprocess.run", side_effect=FileNotFoundError("vault not found"))
    def test_vault_exception_returns_none(self, _mock_run) -> None:
        from max.sources.stackoverflow import _get_api_key
        assert _get_api_key() is None
