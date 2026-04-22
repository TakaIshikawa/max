"""Tests for the Hugging Face Hub source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from max.sources.huggingface import (
    HUGGINGFACE_DATASETS,
    HUGGINGFACE_MODELS,
    HUGGINGFACE_SPACES,
    HuggingFaceAdapter,
    _DEFAULT_QUERIES,
    _DEFAULT_RESOURCE_TYPES,
)
from max.types.signal import SignalSourceType


MODEL_RESULT = {
    "id": "Qwen/Qwen2.5-Coder-7B-Instruct",
    "author": "Qwen",
    "description": "Code-focused instruction model.",
    "downloads": 1250000,
    "likes": 4200,
    "lastModified": "2026-04-20T12:00:00Z",
    "pipeline_tag": "text-generation",
    "library_name": "transformers",
    "tags": ["code", "agent"],
}

DATASET_RESULT = {
    "id": "HuggingFaceH4/ultrachat_200k",
    "description": "Instruction tuning conversations.",
    "downloads": 72000,
    "likes": 540,
    "lastModified": "2026-04-18T08:30:00Z",
    "tags": ["chat", "alignment"],
}

SPACE_RESULT = {
    "id": "agents-course/leaderboard",
    "author": "agents-course",
    "cardData": {"description": "Leaderboard for agent evaluations.", "tags": ["agents"]},
    "likes": 88,
    "lastModified": "2026-04-19T10:15:00Z",
    "sdk": "gradio",
    "tags": ["leaderboard"],
}


def test_huggingface_adapter_properties() -> None:
    adapter = HuggingFaceAdapter()

    assert adapter.name == "huggingface"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.queries == _DEFAULT_QUERIES
    assert adapter.resource_types == _DEFAULT_RESOURCE_TYPES
    assert adapter.sort == "downloads"
    assert adapter.limit_per_query == 10


def test_huggingface_adapter_custom_config_and_aliases() -> None:
    adapter = HuggingFaceAdapter(
        config={
            "queries": ["agent evals"],
            "watchlist_terms": ["mcp"],
            "resource_types": ["models", "dataset", "spaces", "models", "bad"],
            "sort": "likes",
            "limit_per_query": 3,
        }
    )

    assert adapter.queries == ["agent evals", "mcp"]
    assert adapter.resource_types == ["model", "dataset", "space"]
    assert adapter.sort == "likes"
    assert adapter.limit_per_query == 3


@pytest.mark.asyncio
async def test_huggingface_fetches_models_datasets_and_spaces() -> None:
    adapter = HuggingFaceAdapter(
        config={"queries": ["agent"], "resource_types": ["model", "dataset", "space"]}
    )

    with patch("max.sources.huggingface.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: [MODEL_RESULT]),
            MagicMock(json=lambda: [DATASET_RESULT]),
            MagicMock(json=lambda: [SPACE_RESULT]),
        ]

        signals = await adapter.fetch(limit=10)

    assert [call.args[0] for call in mock_fetch.call_args_list] == [
        HUGGINGFACE_MODELS,
        HUGGINGFACE_DATASETS,
        HUGGINGFACE_SPACES,
    ]
    assert mock_fetch.call_args_list[0].kwargs["params"] == {
        "search": "agent",
        "sort": "downloads",
        "direction": "-1",
        "limit": 10,
        "full": "true",
    }

    model, dataset, space = signals
    assert model.source_type == SignalSourceType.REGISTRY
    assert model.source_adapter == "huggingface"
    assert model.title == "Qwen/Qwen2.5-Coder-7B-Instruct"
    assert model.url == "https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct"
    assert model.author == "Qwen"
    assert model.published_at == datetime(2026, 4, 20, 12, tzinfo=timezone.utc)
    assert model.tags == ["model", "code", "agent", "text-generation", "transformers"]
    assert model.credibility > 0.8
    assert model.metadata["resource_type"] == "model"
    assert model.metadata["downloads"] == 1250000
    assert model.metadata["likes"] == 4200
    assert model.metadata["last_modified"] == "2026-04-20T12:00:00+00:00"
    assert model.metadata["search_query"] == "agent"

    assert dataset.url == "https://huggingface.co/datasets/HuggingFaceH4/ultrachat_200k"
    assert dataset.author == "HuggingFaceH4"
    assert dataset.tags == ["dataset", "chat", "alignment", "agent"]
    assert dataset.metadata["resource_type"] == "dataset"

    assert space.url == "https://huggingface.co/spaces/agents-course/leaderboard"
    assert space.content == "Leaderboard for agent evaluations."
    assert space.tags == ["space", "leaderboard", "agents", "gradio", "agent"]
    assert space.metadata["sdk"] == "gradio"


@pytest.mark.asyncio
async def test_huggingface_deduplicates_across_queries_per_resource_type() -> None:
    adapter = HuggingFaceAdapter(config={"queries": ["agent", "llm"], "resource_types": ["model"]})

    with patch("max.sources.huggingface.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: [MODEL_RESULT]),
            MagicMock(json=lambda: [{**MODEL_RESULT, "likes": 9999}]),
        ]

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert mock_fetch.call_count == 2
    assert signals[0].metadata["likes"] == 4200
    assert signals[0].metadata["search_query"] == "agent"


@pytest.mark.asyncio
async def test_huggingface_respects_resource_filter_limit_per_query_and_sort() -> None:
    adapter = HuggingFaceAdapter(
        config={
            "queries": ["eval"],
            "resource_types": ["spaces"],
            "sort": "likes",
            "limit_per_query": 2,
        }
    )

    with patch("max.sources.huggingface.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: [SPACE_RESULT])

        signals = await adapter.fetch(limit=20)

    assert len(signals) == 1
    assert mock_fetch.call_count == 1
    assert mock_fetch.call_args.args[0] == HUGGINGFACE_SPACES
    assert mock_fetch.call_args.kwargs["params"]["sort"] == "likes"
    assert mock_fetch.call_args.kwargs["params"]["limit"] == 2


@pytest.mark.asyncio
async def test_huggingface_handles_fetch_failures() -> None:
    adapter = HuggingFaceAdapter(config={"queries": ["agent"], "resource_types": ["model"]})

    with patch("max.sources.huggingface.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = httpx.RequestError("network unavailable")

        signals = await adapter.fetch(limit=5)

    assert signals == []


@pytest.mark.asyncio
async def test_huggingface_accepts_wrapped_items_response() -> None:
    adapter = HuggingFaceAdapter(config={"queries": ["agent"], "resource_types": ["model"]})

    with patch("max.sources.huggingface.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"items": [MODEL_RESULT]})

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert signals[0].title == "Qwen/Qwen2.5-Coder-7B-Instruct"


def test_huggingface_registry_discovery() -> None:
    from max.sources.registry import get_adapter, get_adapter_metadata, reload_registry

    reload_registry()
    adapter = get_adapter("huggingface")
    metadata = get_adapter_metadata()["huggingface"]

    assert isinstance(adapter, HuggingFaceAdapter)
    assert metadata.config_keys == ["queries", "resource_types", "sort", "limit_per_query"]
    assert "Hugging Face Hub" in metadata.description
