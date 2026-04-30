"""Tests for the npm dependents source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import httpx
import pytest

from max.sources.base import _circuit_breakers
from max.sources.npm_dependents import NpmDependentsAdapter
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
    adapter = NpmDependentsAdapter(
        config={
            "package_names": ["React"],
            "npm_api_url": "https://npm.test/dependents/{package}?limit={limit}",
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://npm.test/dependents/react?limit=10"
        return httpx.Response(
            200,
            json={
                "dependents": [
                    {
                        "package": {
                            "name": "next",
                            "version": "15.3.0",
                            "description": "The React framework for production.",
                            "downloads": 7_500_000,
                            "weekly_downloads": 7_500_000,
                            "date": "2026-04-28T10:15:00Z",
                            "keywords": ["react", "framework"],
                            "publisher": {"username": "vercel-release-bot"},
                            "repository": {"url": "https://github.com/vercel/next.js"},
                            "homepage": "https://nextjs.org",
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    with patch("max.sources.npm_dependents.httpx.AsyncClient", side_effect=_client_factory(transport)):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "npm-dependents:react:next"
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "npm_dependents"
    assert signal.title == "next depends on react"
    assert signal.url == "https://www.npmjs.com/package/next"
    assert signal.author == "vercel-release-bot"
    assert signal.published_at == datetime(2026, 4, 28, 10, 15, tzinfo=timezone.utc)
    assert signal.metadata["signal_role"] == "market"
    assert signal.metadata["signal_kind"] == "reverse_dependency"
    assert signal.metadata["evidence_type"] == "ecosystem_adoption"
    assert signal.metadata["package_ecosystem"] == "npm"
    assert signal.metadata["source_package"] == "react"
    assert signal.metadata["source_package_url"] == "https://www.npmjs.com/package/react"
    assert signal.metadata["dependent_package"] == "next"
    assert signal.metadata["dependent_package_url"] == "https://www.npmjs.com/package/next"
    assert signal.metadata["version"] == "15.3.0"
    assert signal.metadata["downloads"] == 7_500_000
    assert signal.metadata["weekly_downloads"] == 7_500_000
    assert signal.metadata["repository_url"] == "https://github.com/vercel/next.js"
    assert signal.metadata["homepage"] == "https://nextjs.org"
    assert signal.metadata["api_url"] == "https://npm.test/dependents/react?limit=10"
    assert {"javascript", "npm", "registry", "reverse-dependency", "ecosystem-adoption"} <= set(
        signal.tags
    )
    assert signal.credibility >= 0.9


@pytest.mark.asyncio
async def test_empty_response_returns_no_signals() -> None:
    adapter = NpmDependentsAdapter(
        config={
            "package_names": ["react"],
            "npm_api_url": "https://npm.test/dependents/{package}?limit={limit}",
        }
    )

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"dependents": []}))
    with patch("max.sources.npm_dependents.httpx.AsyncClient", side_effect=_client_factory(transport)):
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_malformed_responses_and_rows_are_skipped_without_crashing() -> None:
    adapter = NpmDependentsAdapter(
        config={
            "package_names": ["bad-payload", "bad-rows", "valid"],
            "npm_api_url": "https://npm.test/dependents/{package}?limit={limit}",
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/bad-payload"):
            return httpx.Response(200, json="not an object")
        if request.url.path.endswith("/bad-rows"):
            return httpx.Response(200, json={"dependents": [{"package": {"version": "1.0.0"}}]})
        if request.url.path.endswith("/valid"):
            return httpx.Response(200, json={"dependents": [{"name": "valid-dependent"}]})
        raise AssertionError(f"unexpected URL: {request.url}")

    transport = httpx.MockTransport(handler)
    with patch("max.sources.npm_dependents.httpx.AsyncClient", side_effect=_client_factory(transport)):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["source_package"] == "valid"
    assert signals[0].metadata["dependent_package"] == "valid-dependent"


@pytest.mark.asyncio
async def test_dedupes_dependents_and_respects_global_and_per_package_limits() -> None:
    adapter = NpmDependentsAdapter(
        config={
            "package_names": ["react", "vite"],
            "max_dependents_per_package": 2,
            "npm_api_url": "https://npm.test/dependents/{package}?limit={limit}",
        }
    )
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.path.endswith("/react"):
            return httpx.Response(
                200,
                json={
                    "dependents": [
                        {"name": "next", "version": "15.3.0"},
                        {"package": {"name": "Next", "version": "15.3.0"}},
                        {"name": "gatsby", "version": "5.14.0"},
                        {"name": "remix", "version": "2.16.0"},
                    ]
                },
            )
        if request.url.path.endswith("/vite"):
            return httpx.Response(
                200,
                json={"dependents": [{"name": "vitest"}, {"name": "storybook"}]},
            )
        raise AssertionError(f"unexpected URL: {request.url}")

    transport = httpx.MockTransport(handler)
    with patch("max.sources.npm_dependents.httpx.AsyncClient", side_effect=_client_factory(transport)):
        signals = await adapter.fetch(limit=3)

    assert [signal.metadata["dependent_package"] for signal in signals] == [
        "next",
        "gatsby",
        "vitest",
    ]
    assert requested_urls == [
        "https://npm.test/dependents/react?limit=2",
        "https://npm.test/dependents/vite?limit=1",
    ]


@pytest.mark.asyncio
async def test_supports_npm_search_compatible_object_shape() -> None:
    adapter = NpmDependentsAdapter(
        config={
            "package_names": ["@modelcontextprotocol/sdk"],
            "npm_api_url": "https://npm.test",
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert (
            str(request.url)
            == "https://npm.test/-/v1/search?text=dependencies:@modelcontextprotocol/sdk&size=5"
        )
        return httpx.Response(
            200,
            json={
                "objects": [
                    {
                        "package": {
                            "name": "@acme/mcp-server",
                            "version": "0.8.0",
                            "downloads_weekly": "12000",
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    with patch("max.sources.npm_dependents.httpx.AsyncClient", side_effect=_client_factory(transport)):
        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert signals[0].url == "https://www.npmjs.com/package/@acme/mcp-server"
    assert signals[0].metadata["source_package"] == "@modelcontextprotocol/sdk"
    assert signals[0].metadata["dependent_package"] == "@acme/mcp-server"
    assert signals[0].metadata["weekly_downloads"] == 12_000
