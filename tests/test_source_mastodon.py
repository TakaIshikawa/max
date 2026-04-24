"""Tests for the Mastodon source adapter."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.mastodon import MastodonAdapter
from max.types.signal import SignalSourceType


def _response(payload: object) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


def _status(
    status_id: str,
    *,
    content: str = "<p>Fediverse devtools pain point #DevTools</p>",
    favourites: int = 12,
    reblogs: int = 3,
    replies: int = 2,
    created_at: str = "2026-04-22T09:30:00Z",
    reblog: object = None,
) -> dict:
    return {
        "id": status_id,
        "uri": f"https://mastodon.example/users/alice/statuses/{status_id}",
        "url": f"https://mastodon.example/@alice/{status_id}",
        "created_at": created_at,
        "content": content,
        "account": {
            "id": "42",
            "username": "alice",
            "acct": "alice",
            "display_name": "Alice",
        },
        "favourites_count": favourites,
        "reblogs_count": reblogs,
        "replies_count": replies,
        "language": "en",
        "tags": [{"name": "DevTools"}, {"name": "AI"}],
        "sensitive": False,
        "reblog": reblog,
    }


def test_mastodon_adapter_properties_and_config() -> None:
    adapter = MastodonAdapter(
        config={
            "instances": ["mastodon.example"],
            "hashtags": ["#Python"],
            "watchlist_terms": ["MCP"],
            "accounts": ["@alice"],
            "exclude_reblogs": False,
            "min_favourites": "5",
            "max_age_days": "14",
            "access_token_env": "CUSTOM_MASTODON_TOKEN",
        }
    )

    assert adapter.name == "mastodon"
    assert adapter.source_type == SignalSourceType.FORUM.value
    assert adapter.instances == ["mastodon.example"]
    assert adapter.hashtags == ["Python", "MCP"]
    assert adapter.accounts == ["@alice"]
    assert adapter.exclude_reblogs is False
    assert adapter.min_favourites == 5
    assert adapter.max_age_days == 14
    assert adapter.access_token_env == "CUSTOM_MASTODON_TOKEN"


@pytest.mark.asyncio
async def test_mastodon_fetches_hashtag_statuses_and_normalizes_metadata() -> None:
    adapter = MastodonAdapter(
        config={
            "instances": ["mastodon.example"],
            "hashtags": ["devtools"],
            "accounts": [],
        }
    )
    requested: list[tuple[str, dict]] = []

    async def mock_fetch(url: str, client, *, adapter_name: str, params: dict):
        requested.append((url, params))
        assert adapter_name == "mastodon"
        return _response([_status("100")])

    with patch("max.sources.mastodon.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=10)

    assert requested == [
        ("https://mastodon.example/api/v1/timelines/tag/devtools", {"limit": 10})
    ]
    assert len(signals) == 1
    signal = signals[0]
    assert signal.source_type == SignalSourceType.FORUM
    assert signal.source_adapter == "mastodon"
    assert signal.title == "Fediverse devtools pain point #DevTools"
    assert signal.content == "Fediverse devtools pain point #DevTools"
    assert signal.url == "https://mastodon.example/@alice/100"
    assert signal.author == "alice@mastodon.example"
    assert signal.published_at == datetime(2026, 4, 22, 9, 30, tzinfo=timezone.utc)
    assert signal.credibility == pytest.approx(0.60)
    assert {"mastodon", "fediverse", "hashtag", "devtools", "ai"}.issubset(signal.tags)
    assert signal.metadata == {
        "instance": "mastodon.example",
        "status_id": "100",
        "account_handle": "alice@mastodon.example",
        "favourites": 12,
        "reblogs": 3,
        "replies": 2,
        "language": "en",
        "hashtags": ["devtools", "ai"],
        "sensitive": False,
        "timeline": "hashtag",
        "query": "devtools",
        "uri": "https://mastodon.example/users/alice/statuses/100",
        "url": "https://mastodon.example/@alice/100",
    }


@pytest.mark.asyncio
async def test_mastodon_fetches_account_statuses_after_lookup() -> None:
    adapter = MastodonAdapter(
        config={
            "instances": ["https://mastodon.example"],
            "hashtags": [],
            "accounts": ["@alice@mastodon.example"],
        }
    )
    requested: list[tuple[str, dict]] = []

    async def mock_fetch(url: str, client, *, adapter_name: str, params: dict):
        requested.append((url, params))
        if url.endswith("/api/v1/accounts/lookup"):
            return _response({"id": "42", "acct": "alice"})
        return _response([_status("200", content="<p>Account timeline signal</p>")])

    with patch("max.sources.mastodon.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=10)

    assert requested == [
        ("https://mastodon.example/api/v1/accounts/lookup", {"acct": "alice"}),
        (
            "https://mastodon.example/api/v1/accounts/42/statuses",
            {"limit": 10, "exclude_reblogs": True},
        ),
    ]
    assert len(signals) == 1
    assert signals[0].title == "Account timeline signal"
    assert signals[0].metadata["timeline"] == "account"
    assert signals[0].metadata["query"] == "@alice@mastodon.example"


@pytest.mark.asyncio
async def test_mastodon_filters_age_reblogs_and_min_favourites() -> None:
    adapter = MastodonAdapter(
        config={
            "instances": ["mastodon.example"],
            "hashtags": ["devtools"],
            "accounts": [],
            "min_favourites": 5,
            "max_age_days": 30,
            "exclude_reblogs": True,
        }
    )
    old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    recent_date = datetime.now(timezone.utc).isoformat()
    statuses = [
        _status("old", created_at=old_date, favourites=20),
        _status("low-favs", favourites=4),
        _status("reblog", favourites=20, reblog={"id": "boosted"}),
        _status("kept", created_at=recent_date, favourites=5),
    ]

    async def mock_fetch(url: str, client, *, adapter_name: str, params: dict):
        return _response(statuses)

    with patch("max.sources.mastodon.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["status_id"] for signal in signals] == ["kept"]


@pytest.mark.asyncio
async def test_mastodon_deduplicates_across_hashtag_and_account_timelines() -> None:
    adapter = MastodonAdapter(
        config={
            "instances": ["mastodon.example"],
            "hashtags": ["devtools"],
            "accounts": ["42"],
        }
    )

    async def mock_fetch(url: str, client, *, adapter_name: str, params: dict):
        return _response([_status("100")])

    with patch("max.sources.mastodon.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["status_id"] for signal in signals] == ["100"]


@pytest.mark.asyncio
async def test_mastodon_uses_optional_access_token_env(monkeypatch) -> None:
    monkeypatch.setenv("CUSTOM_MASTODON_TOKEN", "secret-token")
    adapter = MastodonAdapter(
        config={
            "instances": ["mastodon.example"],
            "hashtags": ["devtools"],
            "accounts": [],
            "access_token_env": "CUSTOM_MASTODON_TOKEN",
        }
    )

    async def mock_fetch(url: str, client, *, adapter_name: str, params: dict):
        return _response([])

    with patch("max.sources.mastodon.fetch_with_retry", mock_fetch), \
         patch("max.sources.mastodon.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        await adapter.fetch(limit=1)

    headers = mock_cls.call_args.kwargs["headers"]
    assert headers["Accept"] == "application/json"
    assert headers["Authorization"] == "Bearer secret-token"


@pytest.mark.asyncio
async def test_mastodon_does_not_require_credentials(monkeypatch) -> None:
    monkeypatch.delenv("MASTODON_ACCESS_TOKEN", raising=False)
    adapter = MastodonAdapter(
        config={
            "instances": ["mastodon.example"],
            "hashtags": ["devtools"],
            "accounts": [],
        }
    )

    async def mock_fetch(url: str, client, *, adapter_name: str, params: dict):
        return _response([])

    with patch("max.sources.mastodon.fetch_with_retry", mock_fetch), \
         patch("max.sources.mastodon.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        await adapter.fetch(limit=1)

    assert "Authorization" not in mock_cls.call_args.kwargs["headers"]
