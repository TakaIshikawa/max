"""Tests for the OpenAPI specs source adapter."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import yaml

from max.sources.openapi_specs import OpenApiSpecsAdapter
from max.types.signal import SignalSourceType


PETSTORE_SCHEMA = {
    "openapi": "3.1.0",
    "info": {
        "title": "Petstore",
        "version": "1.2.3",
        "description": "Pet commerce API for partner integrations.",
    },
    "servers": [{"url": "https://api.petstore.test/v1"}, {"url": "/sandbox"}],
    "tags": [
        {"name": "pets", "description": "Pet inventory and adoption workflows."},
        {"name": "orders", "description": "Order placement and fulfillment workflows."},
    ],
    "components": {
        "securitySchemes": {
            "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "x-api-key"},
            "OAuth2": {"type": "oauth2", "flows": {}},
        }
    },
    "paths": {
        "/pets": {
            "get": {
                "operationId": "listPets",
                "summary": "List pets",
                "tags": ["pets"],
            },
            "post": {
                "operationId": "createPet",
                "summary": "Create pet",
                "tags": ["pets"],
            },
        },
        "/orders": {
            "post": {
                "operationId": "createOrder",
                "summary": "Create order",
                "tags": ["orders"],
            }
        },
    },
}


REMOTE_SCHEMA = {
    "openapi": "3.0.3",
    "info": {
        "title": "Billing API",
        "version": "2026-01",
        "description": "Billing and subscription automation API.",
    },
    "servers": [{"url": "https://billing.example.test"}],
    "paths": {
        "/invoices": {
            "get": {
                "operationId": "listInvoices",
                "summary": "List invoices",
                "tags": ["billing"],
            }
        }
    },
}


def test_openapi_specs_adapter_properties() -> None:
    adapter = OpenApiSpecsAdapter(
        config={
            "urls": ["https://example.test/openapi.yaml"],
            "local_paths": ["/tmp/openapi.json"],
            "max_operations_per_signal": "3",
            "include_tags": ["pets"],
            "request_timeout": "12.5",
        }
    )

    assert adapter.name == "openapi_specs"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.urls == ["https://example.test/openapi.yaml"]
    assert adapter.local_paths == ["/tmp/openapi.json"]
    assert adapter.max_operations_per_signal == 3
    assert adapter.include_tags == {"pets"}
    assert adapter.request_timeout == 12.5


@pytest.mark.asyncio
async def test_openapi_specs_parses_local_json_and_yaml_documents(tmp_path) -> None:
    json_path = tmp_path / "petstore.json"
    yaml_path = tmp_path / "billing.yaml"
    json_path.write_text(json.dumps(PETSTORE_SCHEMA), encoding="utf-8")
    yaml_path.write_text(yaml.safe_dump(REMOTE_SCHEMA), encoding="utf-8")

    adapter = OpenApiSpecsAdapter(
        config={
            "local_paths": [str(json_path), str(yaml_path)],
            "max_operations_per_signal": 1,
        }
    )

    signals = await adapter.fetch(limit=10)

    assert [signal.metadata["signal_kind"] for signal in signals] == [
        "openapi_api",
        "openapi_tag_group",
        "openapi_tag_group",
        "openapi_api",
        "openapi_tag_group",
    ]
    petstore = signals[0]
    assert petstore.id.startswith("openapi_specs:")
    assert petstore.source_type == SignalSourceType.REGISTRY
    assert petstore.source_adapter == "openapi_specs"
    assert petstore.title == "Petstore OpenAPI (1.2.3)"
    assert petstore.url == str(json_path)
    assert petstore.metadata["api_title"] == "Petstore"
    assert petstore.metadata["version"] == "1.2.3"
    assert petstore.metadata["description"] == "Pet commerce API for partner integrations."
    assert petstore.metadata["server_urls"] == ["https://api.petstore.test/v1", "/sandbox"]
    assert petstore.metadata["tags"] == ["pets", "orders"]
    assert petstore.metadata["operation_count"] == 3
    assert petstore.metadata["auth_schemes"] == ["ApiKeyAuth", "OAuth2"]
    assert petstore.metadata["source_path"] == str(json_path)
    assert petstore.metadata["source"] == str(json_path)
    assert petstore.metadata["max_operations_per_signal"] == 1
    assert petstore.metadata["truncated_operations"] is True
    assert petstore.metadata["operations"] == [
        {
            "method": "GET",
            "path": "/pets",
            "operation_id": "listPets",
            "summary": "List pets",
            "description": None,
            "tags": ["pets"],
        }
    ]
    assert "Operations: 3." in petstore.content
    assert "ApiKeyAuth" in petstore.tags

    pets = signals[1]
    assert pets.title == "Petstore: pets integration surface"
    assert pets.metadata["tag"] == "pets"
    assert pets.metadata["operation_count"] == 2
    assert pets.metadata["total_operation_count"] == 3
    assert pets.metadata["operations"][0]["operation_id"] == "listPets"


@pytest.mark.asyncio
async def test_openapi_specs_fetches_remote_schema_with_mocked_http() -> None:
    adapter = OpenApiSpecsAdapter(
        config={"urls": ["https://schemas.example.test/billing.yaml"], "request_timeout": 5}
    )

    with patch("max.sources.openapi_specs.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(text=yaml.safe_dump(REMOTE_SCHEMA))

        signals = await adapter.fetch(limit=2)

    assert len(signals) == 2
    assert mock_fetch.call_args.args[0] == "https://schemas.example.test/billing.yaml"
    assert mock_fetch.call_args.kwargs["headers"] == {
        "Accept": "application/json,application/yaml,text/yaml,*/*"
    }
    assert signals[0].metadata["source_url"] == "https://schemas.example.test/billing.yaml"
    assert signals[0].metadata["operation_count"] == 1
    assert signals[1].metadata["tag"] == "billing"


@pytest.mark.asyncio
async def test_openapi_specs_include_tags_limits_tag_group_signals(tmp_path) -> None:
    path = tmp_path / "petstore.yaml"
    path.write_text(yaml.safe_dump(PETSTORE_SCHEMA), encoding="utf-8")
    adapter = OpenApiSpecsAdapter(config={"local_paths": [str(path)], "include_tags": ["orders"]})

    signals = await adapter.fetch(limit=10)

    assert [signal.metadata["signal_kind"] for signal in signals] == [
        "openapi_api",
        "openapi_tag_group",
    ]
    assert signals[1].metadata["tag"] == "orders"


@pytest.mark.asyncio
async def test_openapi_specs_handles_parse_errors_cleanly(tmp_path) -> None:
    malformed = tmp_path / "broken.yaml"
    swagger = tmp_path / "swagger.json"
    malformed.write_text("openapi: [", encoding="utf-8")
    swagger.write_text(json.dumps({"swagger": "2.0", "info": {"title": "Old"}}), encoding="utf-8")
    adapter = OpenApiSpecsAdapter(
        config={
            "local_paths": [str(malformed), str(swagger)],
            "urls": ["https://schemas.example.test/broken.yaml"],
        }
    )

    with patch("max.sources.openapi_specs.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(text="openapi: [")

        signals = await adapter.fetch(limit=10)

    assert signals == []
