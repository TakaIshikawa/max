"""Tests for the Docker Hub tag velocity source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.base import AdapterFetchError, _circuit_breakers
from max.sources.dockerhub_tag_velocity import DockerHubTagVelocityAdapter
from max.types.signal import SignalSourceType


@pytest.fixture(autouse=True)
def _reset_circuit_breakers() -> None:
    _circuit_breakers.clear()


def _response(payload: object) -> MagicMock:
    response = MagicMock()
    response.json.return_value = payload
    return response


def test_dockerhub_tag_velocity_adapter_properties() -> None:
    adapter = DockerHubTagVelocityAdapter(
        config={"repositories": ["_/nginx"], "max_tags_per_repository": 3, "page_size": 2}
    )

    assert adapter.name == "dockerhub_tag_velocity"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.repositories == ["_/nginx"]
    assert adapter.max_tags_per_repository == 3
    assert adapter.page_size == 2


@pytest.mark.asyncio
async def test_fetches_recent_tags_as_registry_signals() -> None:
    adapter = DockerHubTagVelocityAdapter(config={"repositories": ["_/nginx"]})

    with patch("max.sources.dockerhub_tag_velocity.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = _response(
            {
                "count": 2,
                "next": None,
                "results": [
                    {
                        "name": "latest",
                        "last_updated": "2026-04-21T09:00:00Z",
                        "images": [
                            {
                                "digest": "sha256:abc123",
                                "image_id": "img-latest-amd64",
                                "architecture": "amd64",
                                "os": "linux",
                            }
                        ],
                        "full_size": 72_000_000,
                    },
                    {
                        "name": "alpine",
                        "tag_last_pushed": "2026-04-20T08:30:00Z",
                        "digest": "sha256:def456",
                    },
                ],
            }
        )

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert "namespaces/library/repositories/nginx/tags" in mock_fetch.call_args.args[0]
    assert mock_fetch.call_args.kwargs["params"] == {"page_size": 10}

    first = signals[0]
    assert first.id == "dockerhub_tag_velocity:library/nginx:latest"
    assert first.source_type == SignalSourceType.REGISTRY
    assert first.source_adapter == "dockerhub_tag_velocity"
    assert first.title == "library/nginx:latest Docker Hub tag update"
    assert first.url == "https://hub.docker.com/_/nginx/tags?name=latest"
    assert first.published_at == datetime(2026, 4, 21, 9, 0, tzinfo=timezone.utc)
    assert first.metadata["repository_name"] == "library/nginx"
    assert first.metadata["namespace"] == "library"
    assert first.metadata["name"] == "nginx"
    assert first.metadata["tag_name"] == "latest"
    assert first.metadata["last_updated"] == "2026-04-21T09:00:00+00:00"
    assert first.metadata["digest"] == "sha256:abc123"
    assert first.metadata["image_id"] == "img-latest-amd64"
    assert first.metadata["source_url"] == "https://hub.docker.com/_/nginx/tags?name=latest"
    assert first.metadata["api_url"].endswith("/namespaces/library/repositories/nginx/tags")
    assert first.metadata["full_size"] == 72_000_000
    assert {"docker", "dockerhub", "container", "tag", "release", "library/nginx", "latest"} <= set(
        first.tags
    )

    second = signals[1]
    assert second.id == "dockerhub_tag_velocity:library/nginx:alpine"
    assert second.published_at == datetime(2026, 4, 20, 8, 30, tzinfo=timezone.utc)
    assert second.metadata["digest"] == "sha256:def456"
    assert second.metadata["image_id"] is None


@pytest.mark.asyncio
async def test_paginates_until_configured_limits_are_reached() -> None:
    adapter = DockerHubTagVelocityAdapter(
        config={"repositories": ["team/app"], "max_tags_per_repository": 3, "page_size": 2}
    )

    with patch("max.sources.dockerhub_tag_velocity.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            _response(
                {
                    "next": "https://hub.docker.com/v2/namespaces/team/repositories/app/tags?page=2",
                    "results": [
                        {"name": "v3", "last_updated": "2026-04-22T10:00:00Z"},
                        {"name": "v2", "last_updated": "2026-04-21T10:00:00Z"},
                    ],
                }
            ),
            _response(
                {
                    "next": None,
                    "results": [
                        {"name": "v1", "last_updated": "2026-04-20T10:00:00Z"},
                        {"name": "old", "last_updated": "2026-03-01T10:00:00Z"},
                    ],
                }
            ),
        ]

        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["tag_name"] for signal in signals] == ["v3", "v2", "v1"]
    assert mock_fetch.call_count == 2
    assert mock_fetch.call_args_list[0].kwargs["params"] == {"page_size": 2}
    assert mock_fetch.call_args_list[1].args[0] == (
        "https://hub.docker.com/v2/namespaces/team/repositories/app/tags?page=2"
    )
    assert mock_fetch.call_args_list[1].kwargs["params"] == {}


@pytest.mark.asyncio
async def test_overall_limit_stops_across_repositories() -> None:
    adapter = DockerHubTagVelocityAdapter(
        config={"repositories": ["library/nginx", "library/postgres"], "max_tags_per_repository": 5}
    )

    with patch("max.sources.dockerhub_tag_velocity.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = _response(
            {
                "next": None,
                "results": [
                    {"name": "latest", "last_updated": "2026-04-22T10:00:00Z"},
                    {"name": "alpine", "last_updated": "2026-04-21T10:00:00Z"},
                ],
            }
        )

        signals = await adapter.fetch(limit=1)

    assert [signal.id for signal in signals] == ["dockerhub_tag_velocity:library/nginx:latest"]
    assert mock_fetch.call_count == 1
    assert mock_fetch.call_args.kwargs["params"] == {"page_size": 1}


@pytest.mark.asyncio
async def test_empty_and_malformed_tag_responses_are_skipped() -> None:
    adapter = DockerHubTagVelocityAdapter(config={"repositories": ["library/nginx", "team/app"]})

    with patch("max.sources.dockerhub_tag_velocity.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            _response({"next": None, "results": []}),
            _response({"next": None, "results": [{"last_updated": "2026-04-22T10:00:00Z"}]}),
        ]

        signals = await adapter.fetch(limit=10)

    assert signals == []
    assert mock_fetch.call_count == 2


@pytest.mark.asyncio
async def test_api_error_does_not_fail_whole_fetch() -> None:
    adapter = DockerHubTagVelocityAdapter(config={"repositories": ["unavailable/app", "team/app"]})

    with patch("max.sources.dockerhub_tag_velocity.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            AdapterFetchError(
                "dockerhub_tag_velocity",
                503,
                "https://hub.docker.com/v2/namespaces/unavailable/repositories/app/tags",
            ),
            _response(
                {
                    "next": None,
                    "results": [{"name": "latest", "last_updated": "2026-04-22T10:00:00Z"}],
                }
            ),
        ]

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].id == "dockerhub_tag_velocity:team/app:latest"
