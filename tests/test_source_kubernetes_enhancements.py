from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.kubernetes_enhancements import KubernetesEnhancementsAdapter
from max.types.signal import SignalSourceType


def _response(payload: object) -> MagicMock:
    response = MagicMock()
    response.json.return_value = payload
    return response


@pytest.mark.asyncio
async def test_fetch_normalizes_enhancement_metadata() -> None:
    adapter = KubernetesEnhancementsAdapter(config={"feed_url": "https://example.test/kep.json"})
    payload = {"enhancements": [{"title": "Sidecar containers", "issue_url": "https://github.com/kubernetes/enhancements/issues/753", "sig": "sig-node", "stage": "stable", "milestone": "v1.31", "summary": "Graduate sidecars."}]}

    with patch("max.sources.kubernetes_enhancements.fetch_with_retry", new_callable=AsyncMock, return_value=_response(payload)):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].source_type == SignalSourceType.NEWS
    assert signals[0].source_adapter == "kubernetes_enhancements"
    assert signals[0].metadata["stage"] == "stable"
    assert signals[0].metadata["sig"] == "sig-node"
    assert signals[0].metadata["milestone"] == "v1.31"
    assert signals[0].metadata["canonical_url"].endswith("/753")


@pytest.mark.asyncio
async def test_missing_optional_fields_and_malformed_payload_return_empty_or_safe_signal() -> None:
    adapter = KubernetesEnhancementsAdapter()
    payload = [{"title": "KEP without extras", "url": "https://example.test/kep"}]

    with patch("max.sources.kubernetes_enhancements.fetch_with_retry", new_callable=AsyncMock, return_value=_response(payload)):
        signals = await adapter.fetch(limit=10)

    assert signals[0].metadata["stage"] is None
    assert signals[0].content == "KEP without extras"

    with patch("max.sources.kubernetes_enhancements.fetch_with_retry", new_callable=AsyncMock, return_value=_response({"bad": "shape"})):
        assert await adapter.fetch(limit=10) == []


@pytest.mark.asyncio
async def test_stable_deterministic_ids_and_limit() -> None:
    adapter = KubernetesEnhancementsAdapter()
    payload = {"items": [{"title": "A", "url": "https://example.test/a"}, {"title": "B", "url": "https://example.test/b"}]}

    with patch("max.sources.kubernetes_enhancements.fetch_with_retry", new_callable=AsyncMock, return_value=_response(payload)):
        first = await adapter.fetch(limit=1)
    with patch("max.sources.kubernetes_enhancements.fetch_with_retry", new_callable=AsyncMock, return_value=_response(payload)):
        second = await adapter.fetch(limit=1)

    assert len(first) == 1
    assert first[0].id == second[0].id
