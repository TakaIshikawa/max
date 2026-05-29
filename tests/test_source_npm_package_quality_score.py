from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from max.sources.npm_package_quality_score import NpmPackageQualityScoreAdapter


def _response(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload, request=httpx.Request("GET", "https://npms.test"))


@pytest.mark.asyncio
async def test_npm_quality_supports_direct_lookup_and_scores() -> None:
    adapter = NpmPackageQualityScoreAdapter(config={"packages": ["demo"], "npms_api_url": "https://npms.test"})
    payload = {"package": {"name": "demo", "version": "1.0.0", "license": "MIT", "links": {"npm": "https://npm/demo", "repository": "https://repo"}}, "score": {"final": 0.82, "detail": {"quality": 0.9, "popularity": 0.7, "maintenance": 0.8}}}
    with patch("max.sources.npm_package_quality_score.httpx.AsyncClient") as cls:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.get = AsyncMock(return_value=_response(payload))
        cls.return_value = client
        signals = await adapter.fetch(limit=5)
    assert signals[0].metadata["quality"] == 0.9
    assert signals[0].metadata["popularity"] == 0.7
    assert signals[0].metadata["maintenance"] == 0.8
    assert signals[0].metadata["final_score"] == 0.82


@pytest.mark.asyncio
async def test_npm_quality_query_results_default_missing_scores() -> None:
    adapter = NpmPackageQualityScoreAdapter(config={"queries": ["demo"], "max_packages": 1})
    with patch("max.sources.npm_package_quality_score.httpx.AsyncClient") as cls:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.get = AsyncMock(return_value=_response({"results": [{"package": {"name": "demo"}}]}))
        cls.return_value = client
        signals = await adapter.fetch(limit=5)
    assert signals[0].metadata["package"] == "demo"
    assert signals[0].metadata["final_score"] == 0.0
