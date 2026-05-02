"""Tests for the RubyGems maintainer activity source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.base import _circuit_breakers
from max.sources.rubygems_maintainer_activity import RubyGemsMaintainerActivityAdapter
from max.types.signal import SignalSourceType


@pytest.fixture(autouse=True)
def _reset_circuit_breakers() -> None:
    _circuit_breakers.clear()


def _response(payload: object, *, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


def _mock_client(request):
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(side_effect=request)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


def _rails_payload() -> dict:
    return {
        "name": "rails",
        "version": "7.1.3",
        "authors": "David Heinemeier Hansson, Rails core team",
        "downloads": 512345678,
        "version_downloads": 123456,
        "version_created_at": "2026-04-15T10:20:30.000Z",
        "licenses": ["MIT"],
        "info": "Full-stack web application framework.",
        "project_uri": "https://rubygems.org/gems/rails",
        "gem_uri": "https://rubygems.org/gems/rails-7.1.3.gem",
        "homepage_uri": "https://rubyonrails.org",
        "source_code_uri": "https://github.com/rails/rails",
        "documentation_uri": "https://api.rubyonrails.org",
        "bug_tracker_uri": "https://github.com/rails/rails/issues",
        "changelog_uri": "https://github.com/rails/rails/releases",
    }


def _owners_payload() -> list[dict[str, str]]:
    return [
        {"handle": "dhh", "email": "dhh@example.test"},
        {"handle": "fxn"},
    ]


def test_adapter_properties_and_custom_config() -> None:
    adapter = RubyGemsMaintainerActivityAdapter(
        config={
            "gems": ["Rails", "rails"],
            "packages": ["Sidekiq"],
            "package_names": ["rake"],
            "rubygems_api_url": "https://example.test/api/v1/",
            "max_results": "7",
            "timeout": "12.5",
        }
    )

    assert adapter.name == "rubygems_maintainer_activity"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.gems == ["rails", "sidekiq", "rake"]
    assert adapter.rubygems_api_url == "https://example.test/api/v1"
    assert adapter.max_items == 7
    assert adapter.timeout == 12.5


@pytest.mark.asyncio
async def test_fetches_gem_maintainer_activity_signal_with_metadata() -> None:
    adapter = RubyGemsMaintainerActivityAdapter(
        config={"gems": ["rails"], "rubygems_api_url": "https://example.test/api/v1"}
    )
    requested_urls: list[str] = []

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        assert method == "GET"
        assert kwargs["headers"]["User-Agent"] == "max-rubygems-maintainer-activity-adapter/0.1"
        requested_urls.append(url)
        if url.endswith("/gems/rails.json"):
            return _response(_rails_payload())
        if url.endswith("/gems/rails/owners.json"):
            return _response(_owners_payload())
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.rubygems_maintainer_activity.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert requested_urls == [
        "https://example.test/api/v1/gems/rails.json",
        "https://example.test/api/v1/gems/rails/owners.json",
    ]
    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "rubygems-maintainer-activity:rails"
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "rubygems_maintainer_activity"
    assert signal.title == "rails RubyGems maintainer activity"
    assert "latest version 7.1.3" in signal.content
    assert "Total downloads: 512,345,678" in signal.content
    assert signal.url == "https://rubygems.org/gems/rails"
    assert signal.author == "David Heinemeier Hansson"
    assert signal.published_at is not None
    assert {"ruby", "rubygems", "registry", "maintainer-activity", "package-health", "rails"} <= set(signal.tags)
    assert signal.metadata["signal_role"] == "market"
    assert signal.metadata["signal_kind"] == "maintainer_activity"
    assert signal.metadata["evidence_type"] == "package_health"
    assert signal.metadata["package_ecosystem"] == "rubygems"
    assert signal.metadata["gem_name"] == "rails"
    assert signal.metadata["package_name"] == "rails"
    assert signal.metadata["version"] == "7.1.3"
    assert signal.metadata["latest_version"] == "7.1.3"
    assert signal.metadata["authors"] == ["David Heinemeier Hansson", "Rails core team"]
    assert signal.metadata["maintainers"] == [
        {"handle": "dhh", "email": "dhh@example.test", "name": "dhh"},
        {"handle": "fxn", "name": "fxn"},
    ]
    assert signal.metadata["maintainer_count"] == 2
    assert signal.metadata["downloads"] == 512345678
    assert signal.metadata["download_count"] == 512345678
    assert signal.metadata["licenses"] == ["MIT"]
    assert signal.metadata["latest_release_at"] == "2026-04-15T10:20:30+00:00"
    assert isinstance(signal.metadata["release_age_days"], int)
    assert signal.metadata["project_links"]["source_code"] == "https://github.com/rails/rails"
    assert signal.metadata["source_code_uri"] == "https://github.com/rails/rails"
    assert signal.metadata["api_url"] == "https://example.test/api/v1/gems/rails.json"


@pytest.mark.asyncio
async def test_owner_failure_does_not_drop_gem_signal() -> None:
    adapter = RubyGemsMaintainerActivityAdapter(config={"gems": ["rails"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/gems/rails.json"):
            return _response(_rails_payload())
        if url.endswith("/gems/rails/owners.json"):
            return _response({"message": "not found"}, status_code=404)
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.rubygems_maintainer_activity.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["owners"] == []
    assert signals[0].metadata["maintainer_count"] == 2
    assert signals[0].metadata["authors"] == ["David Heinemeier Hansson", "Rails core team"]


@pytest.mark.asyncio
async def test_network_failures_and_malformed_payloads_are_skipped() -> None:
    adapter = RubyGemsMaintainerActivityAdapter(
        config={
            "gems": ["broken", "malformed", "rails"],
            "rubygems_api_url": "https://example.test/api/v1",
        }
    )

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/gems/broken.json"):
            raise httpx.RequestError("network down")
        if url.endswith("/gems/malformed.json"):
            return _response({"name": "malformed", "info": "missing release and download fields"})
        if url.endswith("/gems/rails.json"):
            return _response(_rails_payload())
        if url.endswith("/gems/rails/owners.json"):
            return _response([])
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.rubygems_maintainer_activity.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].id == "rubygems-maintainer-activity:rails"


@pytest.mark.asyncio
async def test_empty_fetch_behavior() -> None:
    adapter = RubyGemsMaintainerActivityAdapter(config={"gems": ["rails"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        return _response([])

    with patch("max.sources.rubygems_maintainer_activity.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        assert await adapter.fetch(limit=10) == []
        assert await adapter.fetch(limit=0) == []
