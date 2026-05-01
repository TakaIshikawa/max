"""Tests for the PyPI classifier trend source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.base import _circuit_breakers
from max.sources.pypi_classifiers import PyPIClassifiersAdapter
from max.types.signal import SignalSourceType


@pytest.fixture(autouse=True)
def _reset_circuit_breakers() -> None:
    _circuit_breakers.clear()


def _response(payload: dict, *, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


def _mock_client(request):
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(side_effect=request)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


def _payload(
    name: str,
    classifiers: list[str],
    *,
    package_url: str | None = None,
    project_urls: dict[str, str] | None = None,
    classifier_growth: dict[str, int | float] | None = None,
) -> dict:
    payload = {
        "info": {
            "name": name,
            "classifiers": classifiers,
            "package_url": package_url or f"https://pypi.org/project/{name.lower()}/",
            "project_urls": project_urls or {},
        }
    }
    if classifier_growth is not None:
        payload["classifier_growth"] = classifier_growth
    return payload


@pytest.mark.asyncio
async def test_fetches_top_classifier_trend_signals_from_package_metadata() -> None:
    ml = "Topic :: Scientific/Engineering :: Artificial Intelligence"
    typing = "Typing :: Typed"
    web = "Framework :: FastAPI"
    adapter = PyPIClassifiersAdapter(
        config={"packages": ["FastAPI", "LangChain", "TypedLib"], "base_url": "https://example.test/pypi"}
    )

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        assert method == "GET"
        if url == "https://example.test/pypi/fastapi/json":
            return _response(
                _payload(
                    "FastAPI",
                    [web, typing],
                    project_urls={"Source": "https://github.com/fastapi/fastapi"},
                )
            )
        if url == "https://example.test/pypi/langchain/json":
            return _response(
                _payload(
                    "LangChain",
                    [ml, typing],
                    project_urls={"Homepage": "https://python.langchain.com/"},
                )
            )
        if url == "https://example.test/pypi/typedlib/json":
            return _response(_payload("TypedLib", [typing]))
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.pypi_classifiers.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["classifier_name"] for signal in signals] == [typing, web, ml]
    first = signals[0]
    assert first.source_adapter == "pypi_classifiers"
    assert first.source_type == SignalSourceType.TRENDING
    assert first.title == f"PyPI classifier trend: {typing}"
    assert first.metadata["count"] == 3
    assert first.metadata["representative_packages"] == ["FastAPI", "LangChain", "TypedLib"]
    assert first.metadata["package_names"] == ["FastAPI", "LangChain", "TypedLib"]
    assert first.metadata["source_urls"][:2] == [
        "https://pypi.org/project/fastapi/",
        "https://github.com/fastapi/fastapi",
    ]
    assert {"python", "pypi", "classifier", "trend", "typing", "typed"} <= set(first.tags)
    assert "FastAPI, LangChain, TypedLib" in first.content


@pytest.mark.asyncio
async def test_empty_package_list_returns_no_signals_without_fetching() -> None:
    adapter = PyPIClassifiersAdapter(config={"packages": []})

    with patch("max.sources.pypi_classifiers.httpx.AsyncClient") as mock_cls:
        signals = await adapter.fetch(limit=10)

    assert signals == []
    mock_cls.assert_not_called()


@pytest.mark.asyncio
async def test_packages_with_missing_classifiers_are_skipped() -> None:
    adapter = PyPIClassifiersAdapter(config={"packages": ["missing", "valid"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/missing/json"):
            return _response({"info": {"name": "missing"}})
        if url.endswith("/valid/json"):
            return _response(_payload("valid", ["Topic :: Software Development :: Libraries"]))
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.pypi_classifiers.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["classifier_name"] == "Topic :: Software Development :: Libraries"
    assert signals[0].metadata["count"] == 1
    assert signals[0].metadata["representative_packages"] == ["valid"]


@pytest.mark.asyncio
async def test_growth_metadata_ranks_a_classifier_ahead_of_raw_count() -> None:
    ai = "Topic :: Scientific/Engineering :: Artificial Intelligence"
    web = "Framework :: FastAPI"
    adapter = PyPIClassifiersAdapter(config={"packages": ["one", "two", "three"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/one/json"):
            return _response(_payload("one", [web, ai], classifier_growth={ai: 6}))
        if url.endswith("/two/json"):
            return _response(_payload("two", [web]))
        if url.endswith("/three/json"):
            return _response(_payload("three", [web]))
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.pypi_classifiers.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["classifier_name"] for signal in signals] == [ai, web]
    assert signals[0].metadata["growth"] == 6
    assert signals[0].metadata["count"] == 1
    assert "Growth metadata score: 6." in signals[0].content


@pytest.mark.asyncio
async def test_classifier_ties_use_stable_alphabetical_ordering() -> None:
    alpha = "Framework :: A"
    beta = "Framework :: B"
    adapter = PyPIClassifiersAdapter(config={"packages": ["first", "second"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/first/json"):
            return _response(_payload("first", [beta, alpha]))
        if url.endswith("/second/json"):
            return _response(_payload("second", [beta, alpha]))
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.pypi_classifiers.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["classifier_name"] for signal in signals] == [alpha, beta]
    assert [signal.metadata["representative_packages"] for signal in signals] == [
        ["first", "second"],
        ["first", "second"],
    ]
