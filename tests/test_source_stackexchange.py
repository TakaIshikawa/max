"""Tests for Stack Exchange source adapter."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.stackexchange import StackExchangeAdapter
from max.types.signal import SignalSourceType


def _response(items: list[dict], *, has_more: bool = False) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "items": items,
        "has_more": has_more,
        "quota_remaining": 9000,
    }
    return resp


def _question(
    question_id: int,
    *,
    title: str = "How should I debug Kubernetes agent failures?",
    link: str | None = None,
    tags: list[str] | None = None,
    score: int = 12,
    creation_date: int | None = None,
    site: str | None = None,
) -> dict:
    return {
        "question_id": question_id,
        "title": title,
        "body": "<p>Need a practical debugging strategy for <b>agent</b> failures.</p>",
        "link": (
            f"https://devops.stackexchange.com/questions/{question_id}/debug-agent?utm=1"
            if link is None
            else link
        ),
        "tags": tags or ["kubernetes", "debugging"],
        "score": score,
        "view_count": 250,
        "answer_count": 3,
        "comment_count": 4,
        "is_answered": True,
        "creation_date": creation_date or int(datetime.now(timezone.utc).timestamp()),
        "owner": {"display_name": "site_user"},
        **({"site": site} if site else {}),
    }


@pytest.mark.asyncio
@patch("max.sources.stackexchange._get_api_key", return_value=None)
async def test_fetch_tagged_questions_across_sites_deduplicates_and_normalizes(_mock_key) -> None:
    adapter = StackExchangeAdapter(config={
        "sites": ["devops", "security"],
        "tags": ["kubernetes", "incident-response"],
        "min_score": 5,
    })
    responses = [
        _response([_question(101), _question(101)]),
        _response([_question(202, title="How to triage leaked API tokens?", site="security")]),
    ]

    with patch(
        "max.sources.stackexchange.fetch_with_retry",
        new_callable=AsyncMock,
        side_effect=responses,
    ) as mock_fetch:
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    first = signals[0]
    assert first.id == "stackexchange:devops:101"
    assert first.source_adapter == "stackexchange"
    assert first.source_type == SignalSourceType.FORUM
    assert first.url == "https://devops.stackexchange.com/questions/101/debug-agent"
    assert "How should I debug" in first.content
    assert "Need a practical debugging strategy" in first.content
    assert first.author == "site_user"
    assert first.metadata["score"] == 12
    assert first.metadata["comment_count"] == 4
    assert "stackexchange" in first.tags
    assert "devops" in first.tags

    first_params = mock_fetch.call_args_list[0].kwargs["params"]
    assert first_params["site"] == "devops"
    assert first_params["tagged"] == "kubernetes;incident-response"
    assert first_params["min"] == 5


@pytest.mark.asyncio
@patch("max.sources.stackexchange._get_api_key", return_value=None)
async def test_fetch_query_mode_uses_search_advanced_and_optional_tags(_mock_key) -> None:
    adapter = StackExchangeAdapter(config={
        "sites": ["dba"],
        "queries": ["slow postgres backups"],
        "tags": ["postgresql"],
    })

    with patch(
        "max.sources.stackexchange.fetch_with_retry",
        new_callable=AsyncMock,
        return_value=_response([_question(301)]),
    ) as mock_fetch:
        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    call = mock_fetch.call_args
    assert call.args[0] == "https://api.stackexchange.com/2.3/search/advanced"
    params = call.kwargs["params"]
    assert params["site"] == "dba"
    assert params["q"] == "slow postgres backups"
    assert params["tagged"] == "postgresql"


@pytest.mark.asyncio
@patch("max.sources.stackexchange._get_api_key", return_value=None)
async def test_fetch_query_mode_does_not_apply_default_tags(_mock_key) -> None:
    adapter = StackExchangeAdapter(config={"sites": ["softwareengineering"], "queries": ["roadmap"]})

    with patch(
        "max.sources.stackexchange.fetch_with_retry",
        new_callable=AsyncMock,
        return_value=_response([]),
    ) as mock_fetch:
        await adapter.fetch(limit=5)

    params = mock_fetch.call_args.kwargs["params"]
    assert params["q"] == "roadmap"
    assert "tagged" not in params


@pytest.mark.asyncio
@patch("max.sources.stackexchange._get_api_key", return_value=None)
async def test_fetch_paginates_until_limit(_mock_key) -> None:
    adapter = StackExchangeAdapter(config={"sites": ["serverfault"], "tags": ["nginx"]})

    with patch(
        "max.sources.stackexchange.fetch_with_retry",
        new_callable=AsyncMock,
        side_effect=[
            _response([_question(1), _question(2)], has_more=True),
            _response([_question(3), _question(4)], has_more=True),
        ],
    ) as mock_fetch:
        signals = await adapter.fetch(limit=3)

    assert [signal.metadata["question_id"] for signal in signals] == [1, 2, 3]
    assert mock_fetch.call_args_list[0].kwargs["params"]["page"] == 1
    assert mock_fetch.call_args_list[1].kwargs["params"]["page"] == 2


@pytest.mark.asyncio
@patch("max.sources.stackexchange._get_api_key", return_value=None)
async def test_fetch_filters_min_score_max_age_and_skips_malformed_items(_mock_key) -> None:
    now = datetime.now(timezone.utc)
    adapter = StackExchangeAdapter(config={
        "sites": ["security"],
        "tags": ["oauth"],
        "min_score": 10,
        "max_age_days": 3,
    })
    items = [
        _question(1, score=9),
        _question(2, score=15, creation_date=int((now - timedelta(days=10)).timestamp())),
        {"question_id": 3, "score": 20},
        ["not", "a", "dict"],
        _question(4, score=20, link="", site="security"),
    ]

    with patch(
        "max.sources.stackexchange.fetch_with_retry",
        new_callable=AsyncMock,
        return_value=_response(items),
    ) as mock_fetch:
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].id == "stackexchange:security:4"
    assert signals[0].url == "https://security.stackexchange.com/questions/4"
    params = mock_fetch.call_args.kwargs["params"]
    assert "fromdate" in params
    assert params["min"] == 10
