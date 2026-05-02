"""Tests for the Kubernetes Enhancement Proposal source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.base import AdapterFetchError
from max.sources.kubernetes_keps import (
    RAW_BASE,
    TREE_URL,
    KubernetesKepsAdapter,
    _extract_summary_sections,
    _kep_directories,
    _parse_kep_index,
)
from max.types.signal import SignalSourceType


TREE = {
    "tree": [
        {"type": "tree", "path": "keps/sig-api-machinery/1234-server-side-apply"},
        {"type": "blob", "path": "keps/sig-api-machinery/1234-server-side-apply/kep.yaml"},
        {"type": "blob", "path": "keps/sig-api-machinery/1234-server-side-apply/README.md"},
        {"type": "blob", "path": "keps/sig-node/5678-node-swap/kep.yaml"},
        {"type": "blob", "path": "keps/sig-node/5678-node-swap/README.md"},
        {"type": "blob", "path": "keps/sig-storage/9999-old-feature/kep.yaml"},
        {"type": "blob", "path": "keps/sig-storage/9999-old-feature/README.md"},
        {"type": "blob", "path": "docs/not-a-kep/README.md"},
    ]
}

KEP_1234_YAML = """
title: Server Side Apply
kep-number: 1234
owning-sig: sig-api-machinery
stage: beta
status: implementable
creation-date: 2024-01-15
"""

KEP_1234_README = """
# Server Side Apply

## Summary

Adds a structured field ownership and apply workflow for Kubernetes API objects.

## Motivation

Controllers and humans need safer coordination.
"""

KEP_5678_YAML = """
title: Node Swap Support
kep-number: 5678
owning-sig: sig-node
stage: alpha
status: provisional
last-updated: 2025-02-10T12:30:00Z
"""

KEP_5678_README = """
# Node Swap Support

## Summary

Enables controlled swap use for node memory management.
"""

KEP_9999_YAML = """
title: Old Storage Feature
kep-number: 9999
owning-sig: sig-storage
stage: stable
status: withdrawn
"""

KEP_9999_README = """
# Old Storage Feature

## Summary

Archived storage roadmap item.
"""

KEP_INDEX = """
| KEP | Title | SIG | Stage | Status | Summary | URL |
| --- | --- | --- | --- | --- | --- | --- |
| 1234 | [Server Side Apply](https://github.com/kubernetes/enhancements/tree/master/keps/sig-api-machinery/1234-server-side-apply) | sig-api-machinery | beta | implementable | Structured field ownership for API objects. | https://github.com/kubernetes/enhancements/tree/master/keps/sig-api-machinery/1234-server-side-apply |
| 5678 | Node Swap Support | sig-node | alpha | provisional | Controlled swap use for node memory management. | https://github.com/kubernetes/enhancements/tree/master/keps/sig-node/5678-node-swap |
| 5678 | Duplicate Node Swap | sig-node | alpha | provisional | Duplicate row should be skipped. | https://example.test/duplicate |
| 9999 | Old Storage Feature | sig-storage | stable | withdrawn | Archived storage roadmap item. | https://github.com/kubernetes/enhancements/tree/master/keps/sig-storage/9999-old-feature |
|  | Sparse row | sig-empty | beta | implementable | Missing KEP id. | https://example.test/sparse |
| 2468 |  | sig-empty | beta | implementable | Missing title. | https://example.test/no-title |
"""


def _response(*, payload: dict | None = None, text: str = "") -> MagicMock:
    response = MagicMock()
    response.json.return_value = payload if payload is not None else {}
    response.text = text
    response.headers = {}
    return response


def _mock_fetch_response(url: str, *args, **kwargs) -> MagicMock:  # noqa: ARG001
    paths = {
        f"{RAW_BASE}/keps/sig-api-machinery/1234-server-side-apply/kep.yaml": KEP_1234_YAML,
        f"{RAW_BASE}/keps/sig-api-machinery/1234-server-side-apply/README.md": KEP_1234_README,
        f"{RAW_BASE}/keps/sig-node/5678-node-swap/kep.yaml": KEP_5678_YAML,
        f"{RAW_BASE}/keps/sig-node/5678-node-swap/README.md": KEP_5678_README,
        f"{RAW_BASE}/keps/sig-storage/9999-old-feature/kep.yaml": KEP_9999_YAML,
        f"{RAW_BASE}/keps/sig-storage/9999-old-feature/README.md": KEP_9999_README,
    }
    if url == TREE_URL:
        return _response(payload=TREE)
    return _response(text=paths[url])


def test_kep_directories_are_sorted_and_limited_to_kep_files() -> None:
    assert _kep_directories(TREE["tree"]) == [
        "keps/sig-api-machinery/1234-server-side-apply",
        "keps/sig-node/5678-node-swap",
        "keps/sig-storage/9999-old-feature",
    ]


def test_extract_summary_sections_from_markdown() -> None:
    sections = _extract_summary_sections(KEP_1234_README)

    assert sections["summary"] == (
        "Adds a structured field ownership and apply workflow for Kubernetes API objects."
    )
    assert sections["motivation"] == "Controllers and humans need safer coordination."


def test_parse_kep_index_accepts_markdown_table_rows() -> None:
    items = _parse_kep_index(KEP_INDEX)

    assert [item["kep_number"] for item in items[:3]] == ["1234", "5678", "5678"]
    assert items[0]["title"] == "Server Side Apply"
    assert items[0]["area"] == "sig-api-machinery"
    assert items[0]["stage"] == "beta"
    assert items[0]["status"] == "implementable"
    assert items[0]["url"].endswith("1234-server-side-apply")


@pytest.mark.asyncio
async def test_kubernetes_keps_fetch_emits_normalized_signals() -> None:
    adapter = KubernetesKepsAdapter(config={"max_results": 10})

    with patch(
        "max.sources.kubernetes_keps.fetch_with_retry",
        side_effect=_mock_fetch_response,
    ) as mock_fetch:
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_args_list[0].args[0] == TREE_URL
    assert mock_fetch.call_args_list[0].kwargs["params"] == {"recursive": "1"}

    first = signals[0]
    assert first.id.startswith("kubernetes_keps:")
    assert first.source_type == SignalSourceType.ROADMAP
    assert first.source_adapter == "kubernetes_keps"
    assert first.title == "KEP-1234: Server Side Apply"
    assert first.content == (
        "Adds a structured field ownership and apply workflow for Kubernetes API objects."
    )
    assert first.url == (
        "https://github.com/kubernetes/enhancements/tree/master/"
        "keps/sig-api-machinery/1234-server-side-apply"
    )
    assert first.author == "sig-api-machinery"
    assert first.published_at is not None
    assert first.metadata["kep_number"] == "1234"
    assert first.metadata["area"] == "sig-api-machinery"
    assert first.metadata["stage"] == "beta"
    assert first.metadata["status"] == "implementable"
    assert first.metadata["owning_sig"] == "sig-api-machinery"
    assert first.metadata["signal_role"] == "solution"
    assert first.metadata["summary"] == first.content
    assert first.metadata["summary_sections"]["motivation"] == (
        "Controllers and humans need safer coordination."
    )
    assert "standards" in first.tags


@pytest.mark.asyncio
async def test_kubernetes_keps_index_filters_sparse_duplicates_keywords_and_max_items() -> None:
    adapter = KubernetesKepsAdapter(
        config={
            "content": KEP_INDEX,
            "sigs": ["sig-node", "sig-api-machinery"],
            "statuses": ["alpha", "implementable"],
            "keywords": ["swap", "ownership"],
            "max_items": 5,
        }
    )

    signals = await adapter.fetch(limit=10)

    assert [signal.metadata["kep_number"] for signal in signals] == ["1234", "5678"]
    assert [signal.title for signal in signals] == [
        "KEP-1234: Server Side Apply",
        "KEP-5678: Node Swap Support",
    ]
    assert len({signal.id for signal in signals}) == 2
    assert signals[0].metadata["matched_keywords"] == ["ownership"]
    assert signals[1].metadata["matched_keywords"] == ["swap"]
    assert all(signal.metadata["signal_role"] == "solution" for signal in signals)


@pytest.mark.asyncio
async def test_kubernetes_keps_fetches_configured_index_url() -> None:
    adapter = KubernetesKepsAdapter(config={"index_url": "https://example.test/kep-index.md"})

    with patch(
        "max.sources.kubernetes_keps.fetch_with_retry",
        return_value=_response(text=KEP_INDEX),
    ) as mock_fetch:
        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["kep_number"] for signal in signals] == ["1234", "5678"]
    assert mock_fetch.call_args.args[0] == "https://example.test/kep-index.md"
    assert mock_fetch.call_args.kwargs["adapter_name"] == "kubernetes_keps"


@pytest.mark.asyncio
async def test_kubernetes_keps_index_fetch_errors_are_logged_and_skipped(caplog) -> None:
    adapter = KubernetesKepsAdapter(config={"index_url": "https://example.test/missing.md"})

    with patch(
        "max.sources.kubernetes_keps.fetch_with_retry",
        side_effect=AdapterFetchError("kubernetes_keps", 500, "https://example.test/missing.md"),
    ), caplog.at_level("WARNING"):
        signals = await adapter.fetch(limit=10)

    assert signals == []
    assert "failed to fetch Kubernetes KEP index" in caplog.text


@pytest.mark.asyncio
async def test_kubernetes_keps_honors_area_stage_and_limit_filters() -> None:
    adapter = KubernetesKepsAdapter(
        config={"areas": ["sig-node"], "stages": ["alpha"], "max_results": 5}
    )

    with patch(
        "max.sources.kubernetes_keps.fetch_with_retry",
        side_effect=_mock_fetch_response,
    ):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].title == "KEP-5678: Node Swap Support"
    assert signals[0].metadata["area"] == "sig-node"
    assert signals[0].metadata["stage"] == "alpha"


@pytest.mark.asyncio
async def test_kubernetes_keps_can_include_archived_items() -> None:
    adapter = KubernetesKepsAdapter(
        config={"areas": ["sig-storage"], "stages": ["withdrawn"], "include_archived": True}
    )

    with patch(
        "max.sources.kubernetes_keps.fetch_with_retry",
        side_effect=_mock_fetch_response,
    ):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].title == "KEP-9999: Old Storage Feature"
    assert signals[0].metadata["status"] == "withdrawn"


@pytest.mark.asyncio
async def test_kubernetes_keps_signal_ids_are_deterministic() -> None:
    adapter = KubernetesKepsAdapter(config={"max_results": 10})

    with patch(
        "max.sources.kubernetes_keps.fetch_with_retry",
        side_effect=_mock_fetch_response,
    ):
        first = await adapter.fetch(limit=10)
        second = await adapter.fetch(limit=10)

    assert [signal.id for signal in first] == [signal.id for signal in second]


@pytest.mark.asyncio
async def test_kubernetes_keps_supports_configured_token() -> None:
    adapter = KubernetesKepsAdapter(config={"github_token": "configured-token"})

    with patch(
        "max.sources.kubernetes_keps.fetch_with_retry",
        side_effect=_mock_fetch_response,
    ), patch("max.sources.kubernetes_keps.httpx.AsyncClient") as mock_client:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = client

        await adapter.fetch(limit=1)

    headers = mock_client.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer configured-token"
