"""Tests for the CNCF Landscape source adapter."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from max.sources.cncf_landscape import CncfLandscapeAdapter
from max.sources.registry import get_adapter_metadata, reload_registry
from max.types.signal import SignalSourceType


def test_cncf_landscape_adapter_properties_and_metadata() -> None:
    adapter = CncfLandscapeAdapter()

    assert adapter.name == "cncf_landscape"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.landscape_urls == []
    assert adapter.local_paths == []
    assert adapter.categories == []
    assert adapter.maturity_levels == []
    assert adapter.include_archived is False
    assert adapter.min_stars == 0

    reload_registry()
    metadata = get_adapter_metadata()["cncf_landscape"]
    assert metadata.config_keys == [
        "landscape_urls",
        "local_paths",
        "categories",
        "maturity_levels",
        "include_archived",
        "min_stars",
    ]
    assert metadata.required_keys == []


@pytest.mark.asyncio
async def test_cncf_landscape_reads_local_yaml_and_json_as_registry_signals(tmp_path) -> None:
    yaml_path = tmp_path / "landscape.yaml"
    yaml_path.write_text(
        """
categories:
  - name: Orchestration
    subcategories:
      - name: Scheduling
        items:
          - name: Kubernetes
            homepage: https://kubernetes.io
            repo_url: https://github.com/kubernetes/kubernetes
            maturity: graduated
            description: Production-grade container orchestration.
            stars: 112000
            crunchbase: https://www.crunchbase.com/organization/kubernetes
            tags: [containers, scheduler]
""",
        encoding="utf-8",
    )
    json_path = tmp_path / "landscape.json"
    json_path.write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "name": "Prometheus",
                        "homepage": "https://prometheus.io",
                        "repo_url": "https://github.com/prometheus/prometheus",
                        "category": "Observability",
                        "subcategory": "Monitoring",
                        "maturity": "graduated",
                        "description": "Monitoring and alerting toolkit.",
                        "stars": 59000,
                        "tags": ["metrics"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    adapter = CncfLandscapeAdapter(config={"local_paths": [str(yaml_path), str(json_path)]})

    signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == ["Kubernetes", "Prometheus"]
    assert all(signal.source_type == SignalSourceType.REGISTRY for signal in signals)
    kubernetes = signals[0]
    assert kubernetes.source_adapter == "cncf_landscape"
    assert kubernetes.url == "https://github.com/kubernetes/kubernetes"
    assert kubernetes.tags == [
        "Orchestration",
        "Scheduling",
        "graduated",
        "containers",
        "scheduler",
    ]
    assert kubernetes.metadata["category"] == "Orchestration"
    assert kubernetes.metadata["subcategory"] == "Scheduling"
    assert kubernetes.metadata["maturity"] == "graduated"
    assert kubernetes.metadata["stars"] == 112000
    assert kubernetes.metadata["repo_url"] == "https://github.com/kubernetes/kubernetes"
    assert kubernetes.metadata["landscape_url"] == str(yaml_path)


@pytest.mark.asyncio
async def test_cncf_landscape_filters_category_maturity_archived_and_min_stars(tmp_path) -> None:
    path = tmp_path / "filtered.yaml"
    path.write_text(
        """
projects:
  - name: Keep Me
    repo_url: https://github.com/example/keep
    category: Observability
    subcategory: Tracing
    maturity: incubating
    description: Kept project.
    stars: 9000
  - name: Wrong Category
    repo_url: https://github.com/example/category
    category: Runtime
    maturity: incubating
    stars: 9000
  - name: Wrong Maturity
    repo_url: https://github.com/example/maturity
    category: Observability
    maturity: sandbox
    stars: 9000
  - name: Archived
    repo_url: https://github.com/example/archived
    category: Observability
    maturity: incubating
    stars: 9000
    archived: true
  - name: Too Small
    repo_url: https://github.com/example/small
    category: Observability
    maturity: incubating
    stars: 99
""",
        encoding="utf-8",
    )
    adapter = CncfLandscapeAdapter(
        config={
            "local_paths": [str(path)],
            "categories": ["observability"],
            "maturity_levels": ["incubating"],
            "min_stars": 1000,
        }
    )

    signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == ["Keep Me"]

    include_archived = CncfLandscapeAdapter(
        config={
            "local_paths": [str(path)],
            "categories": ["observability"],
            "maturity_levels": ["incubating"],
            "min_stars": 1000,
            "include_archived": True,
        }
    )
    signals_with_archived = await include_archived.fetch(limit=10)
    assert [signal.title for signal in signals_with_archived] == ["Keep Me", "Archived"]


@pytest.mark.asyncio
async def test_cncf_landscape_fetches_mocked_http_response() -> None:
    payload = {
        "items": [
            {
                "name": "Envoy",
                "homepage": "https://www.envoyproxy.io",
                "repo_url": "https://github.com/envoyproxy/envoy",
                "category": "Network",
                "subcategory": "Service Proxy",
                "maturity": "graduated",
                "description": "Cloud-native edge and service proxy.",
                "stars": 26000,
            }
        ]
    }
    adapter = CncfLandscapeAdapter(config={"landscape_urls": ["https://example.test/landscape.json"]})

    with patch("max.sources.cncf_landscape.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(text=json.dumps(payload))

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert mock_fetch.call_args.args[0] == "https://example.test/landscape.json"
    assert signals[0].title == "Envoy"
    assert signals[0].metadata["landscape_url"] == "https://example.test/landscape.json"


@pytest.mark.asyncio
async def test_cncf_landscape_credibility_reflects_maturity_and_stars(tmp_path) -> None:
    path = tmp_path / "credibility.json"
    path.write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "name": "Graduated Popular",
                        "repo_url": "https://github.com/example/popular",
                        "maturity": "graduated",
                        "stars": 50000,
                        "description": "Popular graduated project.",
                    },
                    {
                        "name": "Sandbox Small",
                        "repo_url": "https://github.com/example/small",
                        "maturity": "sandbox",
                        "stars": 5,
                        "description": "Small sandbox project.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    adapter = CncfLandscapeAdapter(config={"local_paths": [str(path)]})

    signals = await adapter.fetch(limit=10)

    assert signals[0].credibility > signals[1].credibility
    assert signals[0].credibility >= 0.9
    assert signals[1].credibility < 0.7


@pytest.mark.asyncio
async def test_cncf_landscape_skips_malformed_documents_and_records(tmp_path, caplog) -> None:
    malformed_path = tmp_path / "broken.yaml"
    malformed_path.write_text("{not: [valid", encoding="utf-8")
    partial_path = tmp_path / "partial.json"
    partial_path.write_text(
        json.dumps(
            {
                "projects": [
                    {"description": "Missing project name."},
                    {
                        "name": "Valid",
                        "repo_url": "https://github.com/example/valid",
                        "description": "Valid project.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    adapter = CncfLandscapeAdapter(config={"local_paths": [str(malformed_path), str(partial_path)]})

    signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == ["Valid"]
    assert "malformed landscape data" in caplog.text
