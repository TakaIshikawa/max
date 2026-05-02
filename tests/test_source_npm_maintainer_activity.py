"""Tests for the npm maintainer activity source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import httpx
import pytest

from max.sources.base import _circuit_breakers
from max.sources.npm_maintainer_activity import NpmMaintainerActivityAdapter
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
async def test_fetch_configured_packages_as_maintainer_activity_signals() -> None:
    adapter = NpmMaintainerActivityAdapter(
        config={
            "packages": ["React"],
            "npm_api_url": "https://npm.test",
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://npm.test/react"
        return httpx.Response(
            200,
            json={
                "name": "react",
                "description": "React is a JavaScript library for building user interfaces.",
                "dist-tags": {"latest": "19.1.0"},
                "versions": {
                    "19.1.0": {
                        "_npmUser": {
                            "name": "react-release-bot",
                            "email": "release@example.com",
                        },
                        "repository": {
                            "type": "git",
                            "url": "https://github.com/facebook/react.git",
                        },
                        "license": "MIT",
                    },
                    "19.0.0": {},
                },
                "time": {
                    "created": "2011-10-26T17:46:21.942Z",
                    "modified": "2026-04-25T09:30:00.000Z",
                    "19.1.0": "2026-04-25T09:30:00.000Z",
                },
                "maintainers": [
                    {"name": "react-core", "email": "core@example.com"},
                    {"username": "release-captain"},
                ],
                "homepage": "https://react.dev",
                "keywords": ["react", "ui"],
                "readme": "# React",
            },
        )

    transport = httpx.MockTransport(handler)
    with patch(
        "max.sources.npm_maintainer_activity.httpx.AsyncClient",
        side_effect=_client_factory(transport),
    ):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "npm-maintainer-activity:react"
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "npm_maintainer_activity"
    assert signal.title == "react npm maintainer activity"
    assert signal.url == "https://www.npmjs.com/package/react"
    assert signal.author == "react-release-bot"
    assert signal.published_at == datetime(2026, 4, 25, 9, 30, tzinfo=timezone.utc)
    assert signal.metadata["signal_role"] == "market"
    assert signal.metadata["signal_kind"] == "maintainer_activity"
    assert signal.metadata["evidence_type"] == "package_health"
    assert signal.metadata["package_ecosystem"] == "npm"
    assert signal.metadata["package_name"] == "react"
    assert signal.metadata["npm_name"] == "react"
    assert signal.metadata["latest_version"] == "19.1.0"
    assert signal.metadata["maintainer_count"] == 2
    assert signal.metadata["publisher"] == {
        "name": "react-release-bot",
        "email": "release@example.com",
    }
    assert signal.metadata["repository_url"] == "https://github.com/facebook/react.git"
    assert signal.metadata["homepage"] == "https://react.dev"
    assert signal.metadata["license"] == "MIT"
    assert signal.metadata["modified_at"] == "2026-04-25T09:30:00+00:00"
    assert signal.metadata["created_at"] == "2011-10-26T17:46:21.942000+00:00"
    assert signal.metadata["version_count"] == 2
    assert signal.metadata["health_indicators"] == {
        "maintainer_count": 2,
        "has_maintainers": True,
        "has_repository": True,
        "has_homepage": True,
        "has_license": True,
        "has_readme": True,
        "deprecated": False,
        "version_count": 2,
    }
    assert {"javascript", "npm", "registry", "maintainer-activity", "package-health"} <= set(
        signal.tags
    )
    assert signal.credibility > 0.6


@pytest.mark.asyncio
async def test_search_terms_discover_packages_then_fetch_metadata_with_dedupe() -> None:
    adapter = NpmMaintainerActivityAdapter(
        config={
            "packages": ["react"],
            "queries": ["ui framework"],
            "max_results_per_query": 3,
            "npm_api_url": "https://npm.test",
        }
    )
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.path == "/-/v1/search":
            assert request.url.params["text"] == "ui framework"
            assert request.url.params["size"] == "3"
            return httpx.Response(
                200,
                json={
                    "objects": [
                        {"package": {"name": "React"}},
                        {"package": {"name": "vite"}},
                        {"package": {"name": "Vite"}},
                    ]
                },
            )
        if request.url.path == "/react":
            return httpx.Response(200, json=_minimal_package("react"))
        if request.url.path == "/vite":
            return httpx.Response(200, json=_minimal_package("vite"))
        raise AssertionError(f"unexpected URL: {request.url}")

    transport = httpx.MockTransport(handler)
    with patch(
        "max.sources.npm_maintainer_activity.httpx.AsyncClient",
        side_effect=_client_factory(transport),
    ):
        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["npm_name"] for signal in signals] == ["react", "vite"]
    assert signals[0].metadata["search_query"] is None
    assert signals[1].metadata["search_query"] == "ui framework"
    assert requested_urls == [
        "https://npm.test/-/v1/search?text=ui+framework&size=3",
        "https://npm.test/react",
        "https://npm.test/vite",
    ]


@pytest.mark.asyncio
async def test_missing_optional_fields_still_emit_health_signal() -> None:
    adapter = NpmMaintainerActivityAdapter(
        config={"packages": ["left-pad"], "npm_api_url": "https://npm.test"}
    )

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "name": "left-pad",
                "description": "String left pad.",
                "dist-tags": {"latest": "1.3.0"},
                "versions": {"1.3.0": {}},
                "time": {"1.3.0": "2020-01-01T00:00:00Z"},
            },
        )
    )
    with patch(
        "max.sources.npm_maintainer_activity.httpx.AsyncClient",
        side_effect=_client_factory(transport),
    ):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.author is None
    assert signal.published_at == datetime(2020, 1, 1, tzinfo=timezone.utc)
    assert signal.metadata["maintainers"] == []
    assert signal.metadata["maintainer_count"] == 0
    assert signal.metadata["repository_url"] is None
    assert signal.metadata["homepage"] is None
    assert signal.metadata["health_indicators"]["has_maintainers"] is False
    assert signal.metadata["health_indicators"]["has_repository"] is False


@pytest.mark.asyncio
async def test_malformed_search_metadata_and_http_errors_are_skipped_without_crashing() -> None:
    adapter = NpmMaintainerActivityAdapter(
        config={
            "packages": ["bad-payload", "valid", "unavailable"],
            "queries": ["bad-search"],
            "npm_api_url": "https://npm.test",
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/-/v1/search":
            return httpx.Response(200, json=["not", "a", "dict"])
        if request.url.path == "/bad-payload":
            return httpx.Response(200, json="not a package")
        if request.url.path == "/unavailable":
            return httpx.Response(503, json={})
        if request.url.path == "/valid":
            return httpx.Response(200, json=_minimal_package("valid"))
        raise AssertionError(f"unexpected URL: {request.url}")

    transport = httpx.MockTransport(handler)
    with patch(
        "max.sources.npm_maintainer_activity.httpx.AsyncClient",
        side_effect=_client_factory(transport),
    ):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["npm_name"] == "valid"


@pytest.mark.asyncio
async def test_repository_string_deprecated_and_malformed_timestamps_are_handled() -> None:
    adapter = NpmMaintainerActivityAdapter(
        config={"packages": ["old-package"], "npm_api_url": "https://npm.test"}
    )

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "name": "old-package",
                "dist-tags": {"latest": "2.0.0"},
                "versions": {
                    "2.0.0": {
                        "deprecated": "Use maintained-package instead.",
                        "repository": "git+https://github.com/acme/old-package.git",
                    }
                },
                "time": {
                    "created": "not-a-date",
                    "modified": "also-not-a-date",
                    "2.0.0": "still-not-a-date",
                },
                "maintainers": "malformed",
                "keywords": "not-a-list",
            },
        )
    )
    with patch(
        "max.sources.npm_maintainer_activity.httpx.AsyncClient",
        side_effect=_client_factory(transport),
    ):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.published_at is None
    assert signal.metadata["repository_url"] == "git+https://github.com/acme/old-package.git"
    assert signal.metadata["deprecated"] == "Use maintained-package instead."
    assert signal.metadata["maintainers"] == []
    assert "deprecated" in signal.tags


def _minimal_package(name: str) -> dict:
    return {
        "name": name,
        "description": f"{name} package.",
        "dist-tags": {"latest": "1.0.0"},
        "versions": {"1.0.0": {"_npmUser": {"name": f"{name}-publisher"}}},
        "time": {"modified": "2026-04-20T00:00:00Z"},
        "maintainers": [{"name": f"{name}-maintainer"}],
    }
