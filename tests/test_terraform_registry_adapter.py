"""Tests for the Terraform Registry import adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.imports.terraform_registry_adapter import (
    TERRAFORM_REGISTRY_BASE_URL,
    TerraformRegistryAdapter,
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
        }
    ]
}


def _response(payload: object) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


def test_terraform_registry_adapter_properties_and_config() -> None:
    adapter = TerraformRegistryAdapter(
        config={
            "base_url": "https://example.test/",
            "queries": ["security"],
            "watchlist_terms": ["data"],
            "namespaces": ["hashicorp", "integrations", "hashicorp"],
        }
    )

    assert adapter.name == "terraform_registry_import"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.base_url == "https://example.test"
    assert adapter.module_queries == ["security", "data"]
    assert adapter.provider_namespaces == ["hashicorp", "integrations"]


@pytest.mark.asyncio
async def test_fetch_module_signals() -> None:
    adapter = TerraformRegistryAdapter(config={"module_queries": ["vpc"], "provider_namespaces": []})

    with patch("max.imports.terraform_registry_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = _response(MODULE_RESPONSE)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_args.args[0] == f"{TERRAFORM_REGISTRY_BASE_URL}/v1/modules/search"
    assert mock_fetch.call_args.kwargs["adapter_name"] == "terraform_registry_import"
    assert mock_fetch.call_args.kwargs["params"] == {"q": "vpc", "limit": 10, "offset": 0}

    first = signals[0]
    assert first.source_type == SignalSourceType.REGISTRY
    assert first.source_adapter == "terraform_registry_import"
    assert first.title == "terraform-aws-modules/vpc/aws@5.8.1"
    assert first.content == "Terraform module for AWS VPC resources."
    assert first.url == "https://registry.terraform.io/modules/terraform-aws-modules/vpc/aws"
    assert first.author == "terraform-aws-modules"
    assert first.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert first.tags == ["module", "aws", "vpc"]
    assert first.metadata["type"] == "module"
    assert first.metadata["namespace"] == "terraform-aws-modules"
    assert first.metadata["provider"] == "aws"
    assert first.metadata["downloads"] == 2_500_000
    assert first.metadata["published_at"] == "2026-04-20T12:30:00+00:00"
    assert first.metadata["search_query"] == "vpc"


@pytest.mark.asyncio
async def test_fetch_provider_signals() -> None:
    adapter = TerraformRegistryAdapter(config={"module_queries": [], "provider_namespaces": ["hashicorp"]})

    with patch("max.imports.terraform_registry_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = _response(PROVIDER_RESPONSE)

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert mock_fetch.call_args.args[0] == f"{TERRAFORM_REGISTRY_BASE_URL}/v1/providers/hashicorp"
    assert mock_fetch.call_args.kwargs["params"] == {"limit": 5, "offset": 0}

    signal = signals[0]
    assert signal.title == "hashicorp/aws@5.96.0"
    assert signal.url == "https://registry.terraform.io/providers/hashicorp/aws"
    assert signal.author == "hashicorp"
    assert signal.tags == ["provider", "aws"]
    assert signal.metadata["type"] == "provider"
    assert signal.metadata["name"] == "aws"
    assert signal.metadata["downloads"] == 1_200_000_000
    assert signal.metadata["provider_namespace"] == "hashicorp"


@pytest.mark.asyncio
async def test_fetch_paginates_and_respects_limit() -> None:
    adapter = TerraformRegistryAdapter(config={"module_queries": ["data"], "provider_namespaces": []})
    first_page = {"meta": {"next_offset": 1}, "modules": [{"id": "ns/one/aws", "description": "one"}]}
    second_page = {"modules": [{"id": "ns/two/aws", "description": "two"}]}

    with patch("max.imports.terraform_registry_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [_response(first_page), _response(second_page)]

        signals = await adapter.fetch(limit=2)

    assert [signal.metadata["name"] for signal in signals] == ["one", "two"]
    assert [call.kwargs["params"]["offset"] for call in mock_fetch.call_args_list] == [0, 1]


@pytest.mark.asyncio
async def test_fetch_skips_malformed_items_and_deduplicates() -> None:
    adapter = TerraformRegistryAdapter(config={"module_queries": ["security"], "provider_namespaces": []})
    payload = {
        "modules": [
            {"name": "missing-provider"},
            {"id": "hashicorp/consul/aws", "version": "1.0.0", "download_count": "12"},
            {"id": "hashicorp/consul/aws", "version": "1.0.0", "download_count": "12"},
            "not a module",
        ]
    }

    with patch("max.imports.terraform_registry_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = _response(payload)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["name"] == "consul"
    assert signals[0].metadata["downloads"] == 12


@pytest.mark.asyncio
async def test_fetch_returns_partial_results_after_failure() -> None:
    adapter = TerraformRegistryAdapter(config={"module_queries": ["vpc"], "provider_namespaces": ["hashicorp"]})

    with patch("max.imports.terraform_registry_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [_response(MODULE_RESPONSE), RuntimeError("failed")]

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert {signal.metadata["type"] for signal in signals} == {"module"}


@pytest.mark.asyncio
async def test_fetch_handles_empty_malformed_and_zero_limit() -> None:
    adapter = TerraformRegistryAdapter(config={"module_queries": ["none", "bad"], "provider_namespaces": []})

    with patch("max.imports.terraform_registry_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            _response({"modules": []}),
            MagicMock(json=MagicMock(side_effect=ValueError("bad json"))),
        ]

        assert await adapter.fetch(limit=10) == []

    assert await adapter.fetch(limit=0) == []
