"""Tests for the OpenCollective source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.opencollective import OpenCollectiveAdapter
from max.sources.registry import get_adapter, get_adapter_metadata, list_adapters, reload_registry


def _collective(
    slug: str,
    *,
    name: str | None = None,
    backers: int = 10,
    total: float = 1_000,
) -> dict:
    return {
        "id": f"oc-{slug}",
        "slug": slug,
        "name": name or slug.title(),
        "description": f"{name or slug.title()} open source funding profile",
        "website": f"https://example.com/{slug}",
        "type": "COLLECTIVE",
        "tags": ["open source", "developer tools"],
        "currency": "USD",
        "balance": {"value": total / 2, "currency": "USD"},
        "totalAmountReceived": {"value": total, "currency": "USD"},
        "yearlyBudget": {"value": 12_000, "currency": "USD"},
        "members": {"totalCount": backers},
        "transactions": {
            "totalCount": 42,
            "nodes": [
                {
                    "createdAt": "2026-04-20T10:00:00Z",
                    "amount": {"value": 25, "currency": "USD"},
                }
            ],
        },
    }


def _response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


@pytest.mark.asyncio
async def test_opencollective_fetches_configured_slugs() -> None:
    adapter = OpenCollectiveAdapter(config={"slugs": ["webpack"], "search_terms": []})

    async def mock_post(url: str, *, json: dict) -> MagicMock:
        assert url == "https://api.opencollective.com/graphql/v2"
        assert json["variables"] == {"slug": "webpack"}
        return _response({"data": {"account": _collective("webpack", name="webpack")}})

    with patch("max.sources.opencollective.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.source_adapter == "opencollective"
    assert signal.source_type.value == "funding"
    assert signal.title == "webpack has OpenCollective funding momentum"
    assert signal.url == "https://opencollective.com/webpack"
    assert signal.published_at is not None
    assert signal.metadata["slug"] == "webpack"
    assert signal.metadata["backers_count"] == 10
    assert signal.metadata["total_amount_received"] == 1000
    assert signal.metadata["signal_role"] == "market"
    assert "opencollective" in signal.tags


@pytest.mark.asyncio
async def test_opencollective_fetches_search_results() -> None:
    adapter = OpenCollectiveAdapter(
        config={"search_terms": ["observability"], "max_results_per_query": 3}
    )

    async def mock_post(url: str, *, json: dict) -> MagicMock:
        assert json["variables"] == {"query": "observability", "limit": 3}
        return _response(
            {
                "data": {
                    "accounts": {
                        "nodes": [
                            _collective("prometheus", name="Prometheus", backers=250),
                            _collective("grafana", name="Grafana", backers=300),
                        ]
                    }
                }
            }
        )

    with patch("max.sources.opencollective.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        signals = await adapter.fetch(limit=5)

    assert [signal.metadata["slug"] for signal in signals] == ["prometheus", "grafana"]
    assert all(signal.metadata["source_query"] == "observability" for signal in signals)


@pytest.mark.asyncio
async def test_opencollective_dedupes_by_collective_url_and_respects_limit() -> None:
    adapter = OpenCollectiveAdapter(
        config={"slugs": ["babel"], "search_terms": ["javascript"], "max_results_per_query": 5}
    )

    async def mock_post(url: str, *, json: dict) -> MagicMock:
        variables = json["variables"]
        if variables == {"slug": "babel"}:
            return _response({"data": {"account": _collective("babel", name="Babel")}})
        return _response(
            {
                "data": {
                    "accounts": {
                        "nodes": [
                            _collective("babel", name="Babel"),
                            _collective("webpack", name="webpack"),
                        ]
                    }
                }
            }
        )

    with patch("max.sources.opencollective.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        signals = await adapter.fetch(limit=2)

    assert [signal.metadata["slug"] for signal in signals] == ["babel", "webpack"]


@pytest.mark.asyncio
async def test_opencollective_degrades_gracefully_on_api_errors() -> None:
    adapter = OpenCollectiveAdapter(config={"slugs": ["missing"], "search_terms": []})

    async def mock_post(url: str, *, json: dict) -> MagicMock:
        raise httpx.TimeoutException("request timed out")

    with patch("max.sources.opencollective.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        signals = await adapter.fetch(limit=5)

    assert signals == []


def test_opencollective_adapter_properties_and_config_aliases() -> None:
    adapter = OpenCollectiveAdapter(
        config={
            "collectives": "webpack,babel",
            "queries": ["javascript"],
            "api_url": "https://example.test/graphql",
            "timeout": "7",
        }
    )

    assert adapter.name == "opencollective"
    assert adapter.source_type == "funding"
    assert adapter.slugs == ["webpack", "babel"]
    assert adapter.search_terms == ["javascript"]
    assert adapter.graphql_url == "https://example.test/graphql"
    assert adapter.timeout == 7


def test_opencollective_adapter_is_registered_with_metadata() -> None:
    with patch("max.config.MAX_ADAPTERS", "opencollective"), patch(
        "max.config.MAX_ADAPTERS_EXCLUDE",
        "",
    ):
        reload_registry()
        try:
            assert list_adapters() == ["opencollective"]
            adapter = get_adapter("opencollective")
            metadata = get_adapter_metadata()["opencollective"]
        finally:
            reload_registry()

    assert adapter.name == "opencollective"
    assert metadata.config_keys == [
        "slugs",
        "collectives",
        "search_terms",
        "queries",
        "max_results_per_query",
        "graphql_url",
        "api_url",
        "timeout",
    ]
    assert metadata.required_keys == []
    assert "OpenCollective project funding" in metadata.description
