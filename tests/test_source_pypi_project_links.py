from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from max.sources.pypi_project_links import PyPIProjectLinksAdapter


def _response(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload, request=httpx.Request("GET", "https://pypi.test/demo/json"))


@pytest.mark.asyncio
async def test_pypi_project_links_emit_categorized_metadata() -> None:
    adapter = PyPIProjectLinksAdapter(config={"packages": ["demo"], "pypi_api_url": "https://pypi.test", "timeout": 3})
    payload = {"info": {"name": "demo", "version": "1.2.3", "summary": "Demo package", "project_urls": {"Documentation": "https://docs", "Source": "https://src", "Issues": "https://issues"}, "classifiers": ["Topic :: Software"], "license": "MIT", "requires_python": ">=3.11"}}
    with patch("max.sources.pypi_project_links.httpx.AsyncClient") as cls:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.get = AsyncMock(return_value=_response(payload))
        cls.return_value = client
        signals = await adapter.fetch(limit=5)
    client.get.assert_awaited_once_with("https://pypi.test/demo/json")
    assert signals[0].metadata["documentation_url"] == "https://docs"
    assert signals[0].metadata["source_url"] == "https://src"
    assert signals[0].metadata["issue_tracker_url"] == "https://issues"


@pytest.mark.asyncio
async def test_pypi_project_links_emit_without_project_urls() -> None:
    adapter = PyPIProjectLinksAdapter(config={"package_names": ["demo"]})
    with patch("max.sources.pypi_project_links.httpx.AsyncClient") as cls:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.get = AsyncMock(return_value=_response({"info": {"name": "demo", "version": "1"}}))
        cls.return_value = client
        signals = await adapter.fetch(limit=5)
    assert signals[0].metadata["package"] == "demo"
    assert signals[0].metadata["project_urls"] == {}
