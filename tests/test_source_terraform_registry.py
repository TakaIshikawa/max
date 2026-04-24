"""Tests for the Terraform Registry source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.terraform_registry import (
    TERRAFORM_REGISTRY_BASE_URL,
    TerraformRegistryAdapter,
    _DEFAULT_MODULE_QUERIES,
    _DEFAULT_PROVIDER_NAMESPACES,
)
from max.types.signal import SignalSourceType


MODULE_RESPONSE = {
    "modules": [
        {
            "id": "terraform-aws-modules/vpc/aws",
            "namespace": "terraform-aws-modules",
            "name": "vpc",
            "provider": "aws",
            "version": "5.8.1",
            "downloads": 2_500_000,
            "verified": True,
            "description": "Terraform module for AWS VPC resources.",
            "published_at": "2026-04-20T12:30:00Z",
        },
        {
            "id": "cloudposse/security-group/aws",
            "owner": "cloudposse",
            "name": "security-group",
            "provider": "aws",
            "latest_version": "2.2.0",
            "download_count": 410_000,
            "verified": "false",
            "description": "Manage AWS security groups.",
            "source_url": "https://registry.terraform.io/modules/cloudposse/security-group/aws",
        },
    ]
}

PROVIDER_RESPONSE = {
    "providers": [
        {
            "id": "hashicorp/aws",
            "namespace": "hashicorp",
            "type": "aws",
            "version": "5.96.0",
            "downloads": 1_200_000_000,
            "verified": True,
            "description": "AWS provider.",
            "published_at": "2026-04-18T09:00:00Z",
        },
        {
            "id": "hashicorp/kubernetes",
            "namespace": "hashicorp",
            "name": "kubernetes",
            "version": "2.36.0",
            "downloads_count": 280_000_000,
            "verified": True,
            "description": "Kubernetes provider.",
        },
    ]
}


def test_terraform_registry_adapter_properties() -> None:
    adapter = TerraformRegistryAdapter()

    assert adapter.name == "terraform_registry"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.base_url == TERRAFORM_REGISTRY_BASE_URL
    assert adapter.module_queries == _DEFAULT_MODULE_QUERIES
    assert adapter.provider_namespaces == _DEFAULT_PROVIDER_NAMESPACES


def test_terraform_registry_custom_config_aliases_and_watchlist() -> None:
    adapter = TerraformRegistryAdapter(
        config={
            "base_url": "https://example.test/",
            "queries": ["security"],
            "watchlist_terms": ["data"],
            "namespaces": ["hashicorp", "integrations", "hashicorp"],
        }
    )

    assert adapter.base_url == "https://example.test"
    assert adapter.module_queries == ["security", "data"]
    assert adapter.provider_namespaces == ["hashicorp", "integrations"]


@pytest.mark.asyncio
async def test_terraform_registry_fetch_emits_module_signals() -> None:
    adapter = TerraformRegistryAdapter(config={"module_queries": ["vpc"], "provider_namespaces": []})

    with patch("max.sources.terraform_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MODULE_RESPONSE)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_args.args[0] == f"{TERRAFORM_REGISTRY_BASE_URL}/v1/modules/search"
    assert mock_fetch.call_args.kwargs["params"] == {"q": "vpc", "limit": 10, "offset": 0}

    first = signals[0]
    assert first.source_type == SignalSourceType.REGISTRY
    assert first.source_adapter == "terraform_registry"
    assert first.title == "terraform-aws-modules/vpc/aws@5.8.1"
    assert first.content == "Terraform module for AWS VPC resources."
    assert first.url == "https://registry.terraform.io/modules/terraform-aws-modules/vpc/aws"
    assert first.author == "terraform-aws-modules"
    assert first.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert first.tags == ["module", "aws", "vpc"]
    assert first.credibility > 0.9
    assert first.metadata["type"] == "module"
    assert first.metadata["namespace"] == "terraform-aws-modules"
    assert first.metadata["name"] == "vpc"
    assert first.metadata["provider"] == "aws"
    assert first.metadata["version"] == "5.8.1"
    assert first.metadata["downloads"] == 2_500_000
    assert first.metadata["verified"] is True
    assert first.metadata["description"] == "Terraform module for AWS VPC resources."
    assert first.metadata["published_at"] == "2026-04-20T12:30:00+00:00"
    assert first.metadata["source_url"] == first.url
    assert first.metadata["search_query"] == "vpc"


@pytest.mark.asyncio
async def test_terraform_registry_fetch_emits_provider_signals() -> None:
    adapter = TerraformRegistryAdapter(config={"module_queries": [], "provider_namespaces": ["hashicorp"]})

    with patch("max.sources.terraform_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: PROVIDER_RESPONSE)

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 2
    assert mock_fetch.call_args.args[0] == f"{TERRAFORM_REGISTRY_BASE_URL}/v1/providers/hashicorp"
    assert mock_fetch.call_args.kwargs["params"] == {"limit": 5, "offset": 0}

    first = signals[0]
    assert first.title == "hashicorp/aws@5.96.0"
    assert first.content == "AWS provider."
    assert first.url == "https://registry.terraform.io/providers/hashicorp/aws"
    assert first.author == "hashicorp"
    assert first.published_at == datetime(2026, 4, 18, 9, tzinfo=timezone.utc)
    assert first.tags == ["provider", "aws"]
    assert first.metadata["type"] == "provider"
    assert first.metadata["namespace"] == "hashicorp"
    assert first.metadata["name"] == "aws"
    assert first.metadata["provider"] == "aws"
    assert first.metadata["version"] == "5.96.0"
    assert first.metadata["downloads"] == 1_200_000_000
    assert first.metadata["verified"] is True
    assert first.metadata["source_url"] == first.url
    assert first.metadata["provider_namespace"] == "hashicorp"


@pytest.mark.asyncio
async def test_terraform_registry_paginates_module_search() -> None:
    adapter = TerraformRegistryAdapter(config={"module_queries": ["data"], "provider_namespaces": []})
    first_page = {"meta": {"next_offset": 1}, "modules": [{"id": "ns/one/aws", "description": "one"}]}
    second_page = {"meta": {"next_offset": 2}, "modules": [{"id": "ns/two/aws", "description": "two"}]}
    empty_page = {"modules": []}

    with patch("max.sources.terraform_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: first_page),
            MagicMock(json=lambda: second_page),
            MagicMock(json=lambda: empty_page),
        ]

        signals = await adapter.fetch(limit=3)

    assert [signal.metadata["name"] for signal in signals] == ["one", "two"]
    assert [call.kwargs["params"]["offset"] for call in mock_fetch.call_args_list] == [0, 1, 2]


@pytest.mark.asyncio
async def test_terraform_registry_skips_malformed_items_and_deduplicates() -> None:
    adapter = TerraformRegistryAdapter(config={"module_queries": ["security"], "provider_namespaces": []})
    first_response = {
        "modules": [
            {"name": "missing-provider"},
            {"id": "hashicorp/consul/aws", "version": "1.0.0"},
        ]
    }
    second_response = {"modules": [{"id": "hashicorp/vault/aws", "version": "2.0.0"}]}

    with patch("max.sources.terraform_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: {**first_response, "meta": {"next_offset": 2}}),
            MagicMock(json=lambda: second_response),
        ]

        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["name"] for signal in signals] == ["consul", "vault"]


@pytest.mark.asyncio
async def test_terraform_registry_respects_limit_across_module_and_provider_results() -> None:
    adapter = TerraformRegistryAdapter(
        config={"module_queries": ["security"], "provider_namespaces": ["hashicorp"]}
    )

    with patch("max.sources.terraform_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MODULE_RESPONSE)

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].metadata["type"] == "module"
    assert signals[0].metadata["name"] == "vpc"
    assert mock_fetch.call_count == 1
    assert mock_fetch.call_args.kwargs["params"] == {"q": "security", "limit": 1, "offset": 0}


def test_terraform_registry_registry_discovery() -> None:
    from max.sources.registry import get_adapter, get_adapter_metadata, reload_registry

    reload_registry()
    adapter = get_adapter("terraform_registry")
    metadata = get_adapter_metadata()["terraform_registry"]

    assert isinstance(adapter, TerraformRegistryAdapter)
    assert metadata.config_keys == [
        "base_url",
        "queries",
        "module_queries",
        "provider_namespaces",
        "namespaces",
    ]
    assert "Terraform Registry" in metadata.description
