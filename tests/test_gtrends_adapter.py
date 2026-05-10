"""Tests for Google Trends import adapter — search interest signal collection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from max.imports.gtrends_adapter import (
    GTrendsAdapter,
    _build_tags,
)
from max.types.signal import SignalSourceType


# ── Unit tests ───────────────────────────────────────────────────────


def test_build_tags_known_keywords() -> None:
    tags = _build_tags("AI agent framework")
    assert "ai" in tags
    assert "agent" in tags
    assert "gtrends" in tags


def test_build_tags_no_match() -> None:
    tags = _build_tags("cooking recipes")
    assert tags == ["gtrends"]


# ── Adapter property tests ───────────────────────────────────────────


def test_adapter_name() -> None:
    adapter = GTrendsAdapter()
    assert adapter.name == "gtrends_import"


def test_adapter_source_type() -> None:
    adapter = GTrendsAdapter()
    assert adapter.source_type == SignalSourceType.TRENDING.value


def test_adapter_default_keywords() -> None:
    adapter = GTrendsAdapter()
    assert "AI agent" in adapter.keywords
    assert "LLM framework" in adapter.keywords


def test_adapter_custom_keywords() -> None:
    adapter = GTrendsAdapter(config={"keywords": ["React", "Vue"]})
    assert adapter.keywords == ["React", "Vue"]


def test_adapter_timeframe_default() -> None:
    adapter = GTrendsAdapter()
    assert adapter.timeframe == "today 3-m"


def test_adapter_timeframe_custom() -> None:
    adapter = GTrendsAdapter(config={"timeframe": "today 12-m"})
    assert adapter.timeframe == "today 12-m"


def test_adapter_geo_default() -> None:
    adapter = GTrendsAdapter()
    assert adapter.geo == ""


def test_adapter_geo_custom() -> None:
    adapter = GTrendsAdapter(config={"geo": "US"})
    assert adapter.geo == "US"


# ── Fetch tests with mocked pytrends ────────────────────────────────


class FakeDataFrame:
    """Minimal DataFrame stand-in for tests without pandas."""

    def __init__(self, data: dict):
        self._data = data
        self.columns = list(data.keys())
        self.empty = len(data) == 0 or all(len(v) == 0 for v in data.values())

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __getitem__(self, key: str):
        if key not in self._data:
            raise KeyError(key)
        return FakeSeries(self._data[key])

    def drop(self, columns=None):
        if columns:
            new_data = {k: v for k, v in self._data.items() if k not in columns}
            result = FakeDataFrame(new_data)
            result.columns = [c for c in self.columns if c not in columns]
            return result
        return self


class FakeSeries:
    """Minimal Series stand-in for tests without pandas."""

    def __init__(self, values: list):
        self._values = values
        self.iloc = self

    def __getitem__(self, idx: int):
        return self._values[idx]

    def __len__(self) -> int:
        return len(self._values)

    def mean(self) -> float:
        return sum(self._values) / len(self._values) if self._values else 0.0

    def max(self) -> int:
        return max(self._values) if self._values else 0


class FakeEmptyDataFrame:
    """Empty DataFrame stand-in."""

    empty = True
    columns: list = []


@pytest.mark.asyncio
async def test_fetch_returns_empty_without_pytrends() -> None:
    adapter = GTrendsAdapter()

    with patch(
        "builtins.__import__",
        side_effect=ImportError("No module named 'pytrends'"),
    ):
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_parses_trend_data() -> None:
    adapter = GTrendsAdapter(config={"keywords": ["AI agent"]})

    interest_df = FakeDataFrame({"AI agent": [30, 45, 60, 75, 80], "isPartial": [0, 0, 0, 0, 1]})

    rising_df = MagicMock()
    rising_df.empty = False
    row0 = MagicMock()
    row0.get.side_effect = lambda k, d=None: "AI agent framework" if k == "query" else 500
    row1 = MagicMock()
    row1.get.side_effect = lambda k, d=None: "best AI agent" if k == "query" else 300
    rising_df.head.return_value.iterrows.return_value = [(0, row0), (1, row1)]

    mock_pytrends = MagicMock()
    mock_pytrends.build_payload.return_value = None
    mock_pytrends.interest_over_time.return_value = interest_df
    mock_pytrends.related_queries.return_value = {
        "AI agent": {"rising": rising_df, "top": None}
    }

    mock_trendreq_cls = MagicMock(return_value=mock_pytrends)

    with patch.dict("sys.modules", {
        "pytrends": MagicMock(),
        "pytrends.request": MagicMock(TrendReq=mock_trendreq_cls),
    }):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    sig = signals[0]
    assert sig.title == "AI agent"
    assert sig.source_adapter == "gtrends_import"
    assert sig.source_type == SignalSourceType.TRENDING
    assert sig.metadata["current_interest"] == 80
    assert sig.metadata["max_interest"] == 80
    assert sig.metadata["keyword"] == "AI agent"
    assert sig.metadata["data_points"] == 5
    assert len(sig.metadata["related_rising"]) == 2


@pytest.mark.asyncio
async def test_fetch_handles_empty_interest() -> None:
    adapter = GTrendsAdapter(config={"keywords": ["niche topic"]})

    mock_pytrends = MagicMock()
    mock_pytrends.build_payload.return_value = None
    mock_pytrends.interest_over_time.return_value = FakeEmptyDataFrame()

    mock_trendreq_cls = MagicMock(return_value=mock_pytrends)

    with patch.dict("sys.modules", {
        "pytrends": MagicMock(),
        "pytrends.request": MagicMock(TrendReq=mock_trendreq_cls),
    }):
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_handles_api_error() -> None:
    adapter = GTrendsAdapter(config={"keywords": ["test"]})

    mock_pytrends = MagicMock()
    mock_pytrends.build_payload.return_value = None
    mock_pytrends.interest_over_time.side_effect = Exception("Rate limited")

    mock_trendreq_cls = MagicMock(return_value=mock_pytrends)

    with patch.dict("sys.modules", {
        "pytrends": MagicMock(),
        "pytrends.request": MagicMock(TrendReq=mock_trendreq_cls),
    }):
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_respects_limit() -> None:
    adapter = GTrendsAdapter(config={"keywords": ["kw1", "kw2", "kw3"]})

    interest_df = FakeDataFrame({
        "kw1": [50, 60],
        "kw2": [40, 50],
        "kw3": [30, 40],
        "isPartial": [0, 0],
    })

    mock_pytrends = MagicMock()
    mock_pytrends.build_payload.return_value = None
    mock_pytrends.interest_over_time.return_value = interest_df
    mock_pytrends.related_queries.return_value = {}

    mock_trendreq_cls = MagicMock(return_value=mock_pytrends)

    with patch.dict("sys.modules", {
        "pytrends": MagicMock(),
        "pytrends.request": MagicMock(TrendReq=mock_trendreq_cls),
    }):
        signals = await adapter.fetch(limit=2)

    assert len(signals) == 2


@pytest.mark.asyncio
async def test_fetch_credibility_from_interest() -> None:
    adapter = GTrendsAdapter(config={"keywords": ["trending topic"]})

    interest_df = FakeDataFrame({"trending topic": [100]})

    mock_pytrends = MagicMock()
    mock_pytrends.build_payload.return_value = None
    mock_pytrends.interest_over_time.return_value = interest_df
    mock_pytrends.related_queries.return_value = {}

    mock_trendreq_cls = MagicMock(return_value=mock_pytrends)

    with patch.dict("sys.modules", {
        "pytrends": MagicMock(),
        "pytrends.request": MagicMock(TrendReq=mock_trendreq_cls),
    }):
        signals = await adapter.fetch(limit=10)

    assert signals[0].credibility == 1.0
