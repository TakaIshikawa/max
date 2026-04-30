"""Tests for the Artifact Hub source adapter."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from max.sources.artifact_hub import ArtifactHubAdapter
from max.types.signal import SignalSourceType


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def json(self) -> object:
        return self._payload


def _package(**overrides: object) -> dict:
    data = {
        "package_id": "pkg-1",
        "name": "cert-manager",
        "normalized_name": "cert-manager",
        "package_type": "helm",
        "stars": 42,
        "description": "X.509 certificate management for Kubernetes.",
        "version": "1.15.0",
        "app_version": "v1.15.0",
        "updated_at": "2025-01-02T03:04:05Z",
        "repository": {
            "repository_id": "repo-1",
            "name": "jetstack",
            "url": "https://charts.jetstack.io",
            "official": True,
            "verified_publisher": True,
            "organization_name": "cert-manager",
        },
        "category": "security",
    }
    data.update(overrides)
    return data


@pytest.mark.asyncio
async def test_artifact_hub_fetch_builds_search_query_params() -> None:
    adapter = ArtifactHubAdapter(
        config={
            "base_url": "https://artifacthub.example",
            "queries": ["service mesh"],
            "categories": ["networking"],
            "package_types": ["helm", "olm"],
            "sort": "stars",
        }
    )

    with patch(
        "max.sources.artifact_hub.fetch_with_retry",
        return_value=FakeResponse({"packages": [_package()]}),
    ) as mock_fetch:
        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert mock_fetch.call_args.args[0] == "https://artifacthub.example/api/v1/packages/search"
    params = mock_fetch.call_args.kwargs["params"]
    assert params["ts_query_web"] == "service mesh"
    assert params["category"] == ["networking"]
    assert params["kind"] == ["helm", "olm"]
    assert params["sort"] == "stars"
    assert params["facets"] == "false"
    assert params["limit"] == 1
    assert params["offset"] == 0
    assert mock_fetch.call_args.kwargs["adapter_name"] == "artifact_hub"


@pytest.mark.asyncio
async def test_artifact_hub_normalizes_package_and_repository_metadata() -> None:
    adapter = ArtifactHubAdapter(config={"queries": ["cert-manager"], "package_types": ["helm"]})

    with patch(
        "max.sources.artifact_hub.fetch_with_retry",
        return_value=FakeResponse({"packages": [_package()]}),
    ):
        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "artifact_hub:pkg-1|helm|cert-manager"
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "artifact_hub"
    assert signal.title == "cert-manager (helm)@1.15.0"
    assert signal.url == "https://artifacthub.io/packages/helm/jetstack/cert-manager"
    assert signal.author == "cert-manager"
    assert signal.published_at is not None
    assert {"artifact-hub", "cloud-native", "helm", "security", "cert-manager"}.issubset(
        set(signal.tags)
    )
    assert signal.metadata["package_type"] == "helm"
    assert signal.metadata["stars"] == 42
    assert signal.metadata["official"] is True
    assert signal.metadata["verified_publisher"] is True
    assert signal.metadata["repository"] == {
        "id": "repo-1",
        "name": "jetstack",
        "url": "https://charts.jetstack.io",
        "official": True,
        "verified_publisher": True,
        "organization": "cert-manager",
        "publisher": "cert-manager",
    }
    assert signal.metadata["popularity"] == {"stars": 42, "official": True}
    assert signal.metadata["maintenance"]["version"] == "1.15.0"
    assert signal.metadata["maintenance"]["updated_at"] == "2025-01-02T03:04:05+00:00"


@pytest.mark.asyncio
async def test_artifact_hub_missing_optional_fields_do_not_break_signal_creation() -> None:
    adapter = ArtifactHubAdapter(config={"queries": ["policy"], "package_types": []})
    sparse_package = {
        "name": "minimal-policy",
        "description": "A sparse Artifact Hub package.",
    }

    with patch(
        "max.sources.artifact_hub.fetch_with_retry",
        return_value=FakeResponse({"packages": [sparse_package]}),
    ):
        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.title == "minimal-policy"
    assert signal.url == "https://artifacthub.io/packages/search?ts_query_web=minimal-policy"
    assert signal.author is None
    assert signal.metadata["stars"] is None
    assert signal.metadata["official"] is None
    assert signal.metadata["repository"]["url"] is None
    assert signal.metadata["maintenance"]["updated_at"] is None


@pytest.mark.asyncio
async def test_artifact_hub_honors_limit_and_deduplicates_packages() -> None:
    adapter = ArtifactHubAdapter(config={"queries": ["observability", "security"], "package_types": ["helm"]})
    first = _package(package_id="pkg-1", name="prometheus", normalized_name="prometheus")
    duplicate = _package(package_id="pkg-1", name="prometheus", normalized_name="prometheus")
    second = _package(package_id="pkg-2", name="grafana", normalized_name="grafana")

    with patch(
        "max.sources.artifact_hub.fetch_with_retry",
        return_value=FakeResponse({"packages": [first, duplicate, second]}),
    ) as mock_fetch:
        signals = await adapter.fetch(limit=2)

    assert [signal.metadata["name"] for signal in signals] == ["prometheus", "grafana"]
    assert mock_fetch.call_count == 1
    assert mock_fetch.call_args.kwargs["params"]["limit"] == 2


@pytest.mark.asyncio
async def test_artifact_hub_max_results_caps_requested_limit() -> None:
    adapter = ArtifactHubAdapter(
        config={"queries": ["kubernetes"], "package_types": ["helm"], "max_results": 1}
    )

    with patch(
        "max.sources.artifact_hub.fetch_with_retry",
        return_value=FakeResponse({"packages": [_package(), _package(package_id="pkg-2")]}),
    ) as mock_fetch:
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert mock_fetch.call_args.kwargs["params"]["limit"] == 1
