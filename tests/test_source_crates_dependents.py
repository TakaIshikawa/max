"""Tests for the crates.io dependents source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import httpx
import pytest

from max.sources.base import _circuit_breakers
from max.sources.crates_dependents import CratesDependentsAdapter
from max.types.signal import SignalSourceType

_REAL_ASYNC_CLIENT = httpx.AsyncClient


@pytest.fixture(autouse=True)
def _reset_circuit_breakers() -> None:
    _circuit_breakers.clear()


def _client_factory(transport: httpx.MockTransport):
    def factory(**kwargs):
        return _REAL_ASYNC_CLIENT(transport=transport, **kwargs)

    return factory


@pytest.mark.asyncio
async def test_fetch_dependents_as_registry_adoption_signals() -> None:
    adapter = CratesDependentsAdapter(
        config={
            "crate_names": ["Serde"],
            "crates_api_url": "https://crates.test/dependents/{crate}?page={page}&per_page={per_page}",
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://crates.test/dependents/serde?page=1&per_page=10"
        return httpx.Response(
            200,
            json={
                "dependencies": [
                    {
                        "req": "^1.0",
                        "kind": "normal",
                        "optional": False,
                        "default_features": True,
                        "crate": {
                            "id": "tokio",
                            "name": "tokio",
                            "max_version": "1.48.0",
                            "description": "An event-driven platform for asynchronous I/O.",
                            "downloads": 500_000_000,
                            "recent_downloads": 25_000_000,
                            "updated_at": "2026-04-20T12:30:00Z",
                            "repository": "https://github.com/tokio-rs/tokio",
                            "homepage": "https://tokio.rs",
                            "documentation": "https://docs.rs/tokio",
                            "keywords": ["async", "io"],
                        },
                    }
                ],
                "meta": {"total": 1},
            },
        )

    transport = httpx.MockTransport(handler)
    with patch("max.sources.crates_dependents.httpx.AsyncClient", side_effect=_client_factory(transport)):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "crates-dependents:serde:tokio"
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "crates_dependents"
    assert signal.title == "tokio depends on serde"
    assert signal.url == "https://crates.io/crates/tokio"
    assert signal.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert signal.metadata["signal_role"] == "market"
    assert signal.metadata["signal_kind"] == "reverse_dependency"
    assert signal.metadata["evidence_type"] == "ecosystem_adoption"
    assert signal.metadata["package_ecosystem"] == "crates.io"
    assert signal.metadata["source_crate"] == "serde"
    assert signal.metadata["source_crate_url"] == "https://crates.io/crates/serde"
    assert signal.metadata["dependent_crate"] == "tokio"
    assert signal.metadata["dependent_crate_url"] == "https://crates.io/crates/tokio"
    assert signal.metadata["version"] == "1.48.0"
    assert signal.metadata["downloads"] == 500_000_000
    assert signal.metadata["recent_downloads"] == 25_000_000
    assert signal.metadata["repository"] == "https://github.com/tokio-rs/tokio"
    assert signal.metadata["homepage"] == "https://tokio.rs"
    assert signal.metadata["documentation"] == "https://docs.rs/tokio"
    assert signal.metadata["dependency_requirement"] == "^1.0"
    assert signal.metadata["dependency_kind"] == "normal"
    assert signal.metadata["optional"] is False
    assert signal.metadata["default_features"] is True
    assert signal.metadata["api_url"] == "https://crates.test/dependents/serde?page=1&per_page=10"
    assert {"rust", "crates.io", "registry", "reverse-dependency", "ecosystem-adoption"} <= set(
        signal.tags
    )
    assert signal.credibility >= 0.9


@pytest.mark.asyncio
async def test_empty_response_returns_no_signals() -> None:
    adapter = CratesDependentsAdapter(
        config={
            "crate_names": ["serde"],
            "crates_api_url": "https://crates.test/dependents/{crate}?page={page}&per_page={per_page}",
        }
    )

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"dependencies": []}))
    with patch("max.sources.crates_dependents.httpx.AsyncClient", side_effect=_client_factory(transport)):
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_malformed_responses_and_rows_are_skipped_without_crashing() -> None:
    adapter = CratesDependentsAdapter(
        config={
            "crate_names": ["bad-payload", "bad-rows", "valid"],
            "crates_api_url": "https://crates.test/dependents/{crate}?page={page}&per_page={per_page}",
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/bad-payload"):
            return httpx.Response(200, json="not an object")
        if request.url.path.endswith("/bad-rows"):
            return httpx.Response(200, json={"dependencies": [{"crate": {"max_version": "1.0.0"}}]})
        if request.url.path.endswith("/valid"):
            return httpx.Response(200, json={"dependencies": [{"crate": {"name": "valid-dependent"}}]})
        raise AssertionError(f"unexpected URL: {request.url}")

    transport = httpx.MockTransport(handler)
    with patch("max.sources.crates_dependents.httpx.AsyncClient", side_effect=_client_factory(transport)):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["source_crate"] == "valid"
    assert signals[0].metadata["dependent_crate"] == "valid-dependent"


@pytest.mark.asyncio
async def test_paginates_dedupes_dependents_and_respects_limits() -> None:
    adapter = CratesDependentsAdapter(
        config={
            "crate_names": ["serde", "tokio"],
            "max_dependents_per_crate": 3,
            "page_size": 2,
            "crates_api_url": "https://crates.test/dependents/{crate}?page={page}&per_page={per_page}",
        }
    )
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.path.endswith("/serde") and request.url.params["page"] == "1":
            return httpx.Response(
                200,
                json={
                    "dependencies": [
                        {"crate": {"name": "diesel", "max_version": "2.2.0"}},
                        {"crate": {"name": "Diesel", "max_version": "2.2.0"}},
                    ],
                    "meta": {"total": 4},
                },
            )
        if request.url.path.endswith("/serde") and request.url.params["page"] == "2":
            return httpx.Response(
                200,
                json={
                    "dependencies": [
                        {"crate": {"name": "sqlx"}},
                        {"crate": {"name": "axum"}},
                    ],
                    "meta": {"total": 4},
                },
            )
        if request.url.path.endswith("/tokio"):
            return httpx.Response(200, json={"dependencies": [{"crate": {"name": "tonic"}}]})
        raise AssertionError(f"unexpected URL: {request.url}")

    transport = httpx.MockTransport(handler)
    with patch("max.sources.crates_dependents.httpx.AsyncClient", side_effect=_client_factory(transport)):
        signals = await adapter.fetch(limit=4)

    assert [signal.metadata["dependent_crate"] for signal in signals] == [
        "diesel",
        "sqlx",
        "axum",
        "tonic",
    ]
    assert requested_urls == [
        "https://crates.test/dependents/serde?page=1&per_page=2",
        "https://crates.test/dependents/serde?page=2&per_page=2",
        "https://crates.test/dependents/tokio?page=1&per_page=1",
    ]


@pytest.mark.asyncio
async def test_supports_default_crates_io_reverse_dependencies_shape() -> None:
    adapter = CratesDependentsAdapter(config={"crate_names": ["serde"], "crates_api_url": "https://crates.test"})

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            "https://crates.test/crates/serde/reverse_dependencies?page=1&per_page=5"
        )
        return httpx.Response(
            200,
            json={
                "dependencies": [
                    {
                        "req": ">=1",
                        "crate": {
                            "id": "serde-json",
                            "name": "serde-json",
                            "newest_version": "1.0.145",
                            "downloads": "100000000",
                        },
                    }
                ],
                "meta": {"total": 1},
            },
        )

    transport = httpx.MockTransport(handler)
    with patch("max.sources.crates_dependents.httpx.AsyncClient", side_effect=_client_factory(transport)):
        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert signals[0].url == "https://crates.io/crates/serde-json"
    assert signals[0].metadata["source_crate"] == "serde"
    assert signals[0].metadata["dependent_crate"] == "serde-json"
    assert signals[0].metadata["version"] == "1.0.145"
    assert signals[0].metadata["downloads"] == 100_000_000
