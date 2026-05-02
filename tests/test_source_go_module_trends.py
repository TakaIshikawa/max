"""Tests for the Go module trends source adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from max.sources.go_module_trends import (
    GO_PROXY_INDEX_URL,
    GoModuleTrendsAdapter,
)
from max.types.signal import SignalSourceType


MOCK_INDEX = "\n".join(
    [
        '{"Path":"github.com/stretchr/testify","Version":"v1.10.0","Timestamp":"2025-01-08T12:34:56Z"}',
        '{"Path":"golang.org/x/sync","Version":"v0.12.0","Timestamp":"2025-01-09T00:00:00Z"}',
    ]
)


def test_go_module_trends_adapter_properties() -> None:
    adapter = GoModuleTrendsAdapter()

    assert adapter.name == "go_module_trends"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.module_paths == []
    assert adapter.max_results == 30
    assert adapter.index_url == GO_PROXY_INDEX_URL
    assert adapter.proxy_base_url == "https://proxy.golang.org"


@pytest.mark.asyncio
async def test_go_module_trends_fetch_emits_normalized_index_signals() -> None:
    adapter = GoModuleTrendsAdapter(config={"max_results": 2})

    with patch("max.sources.go_module_trends.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(
            headers={"content-type": "application/json"},
            text=MOCK_INDEX,
            json=MagicMock(side_effect=ValueError("json lines")),
        )

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_args.args[0] == GO_PROXY_INDEX_URL
    assert mock_fetch.call_args.kwargs["params"] == {"limit": 2}

    first = signals[0]
    assert first.id.startswith("go_module_trends:")
    assert first.source_type == SignalSourceType.REGISTRY
    assert first.source_adapter == "go_module_trends"
    assert first.title == "github.com/stretchr/testify@v1.10.0"
    assert first.url == "https://pkg.go.dev/github.com/stretchr/testify@v1.10.0"
    assert first.published_at.isoformat() == "2025-01-08T12:34:56+00:00"
    assert first.tags == ["go", "golang", "go-module", "module-activity", "github.com"]
    assert first.metadata["package_ecosystem"] == "go"
    assert first.metadata["registry"] == "go_proxy"
    assert first.metadata["module_path"] == "github.com/stretchr/testify"
    assert first.metadata["package_name"] == "github.com/stretchr/testify"
    assert first.metadata["version"] == "v1.10.0"
    assert first.metadata["timestamp"] == "2025-01-08T12:34:56+00:00"
    assert first.metadata["module_url"] == "https://pkg.go.dev/github.com/stretchr/testify@v1.10.0"
    assert first.metadata["source_url"] == "https://pkg.go.dev/github.com/stretchr/testify@v1.10.0"
    assert first.metadata["proxy_url"] == (
        "https://proxy.golang.org/github.com/stretchr/testify/@v/v1.10.0.info"
    )
    assert first.metadata["lookup_type"] == "index"


@pytest.mark.asyncio
async def test_go_module_trends_fetch_returns_empty_for_empty_response() -> None:
    adapter = GoModuleTrendsAdapter(config={"max_results": 5})

    with patch("max.sources.go_module_trends.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(
            headers={"content-type": "application/json"},
            text="",
            json=MagicMock(side_effect=ValueError("empty")),
        )

        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_go_module_trends_skips_malformed_records(caplog) -> None:
    adapter = GoModuleTrendsAdapter(config={"max_results": 4})
    payload = "\n".join(
        [
            '{"Path":"github.com/valid/module","Version":"v0.1.0","Timestamp":"2025-02-01T00:00:00Z"}',
            '{"Path":"github.com/missing/version","Timestamp":"2025-02-01T00:00:00Z"}',
            '{"Version":"v1.0.0","Timestamp":"2025-02-01T00:00:00Z"}',
            "not-json",
        ]
    )

    with patch("max.sources.go_module_trends.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(
            headers={"content-type": "text/plain"},
            text=payload,
            json=MagicMock(side_effect=ValueError("not json")),
        )

        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["module_path"] for signal in signals] == ["github.com/valid/module"]
    assert "skipping malformed Go module record" in caplog.text


@pytest.mark.asyncio
async def test_go_module_trends_parses_module_list_response() -> None:
    adapter = GoModuleTrendsAdapter(
        config={
            "module_paths": ["github.com/Example/Tool"],
            "max_results": 0,
        }
    )

    with patch("max.sources.go_module_trends.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(
            headers={"content-type": "text/plain"},
            text="v1.0.0\nv1.1.0\n",
            json=MagicMock(side_effect=ValueError("plain text")),
        )

        signals = await adapter.fetch(limit=2)

    assert [signal.title for signal in signals] == [
        "github.com/Example/Tool@v1.0.0",
        "github.com/Example/Tool@v1.1.0",
    ]
    assert mock_fetch.call_args.args[0] == "https://proxy.golang.org/github.com/!example/!tool/@v/list"
    assert signals[0].metadata["lookup_type"] == "module_list"
    assert signals[0].metadata["timestamp"] is None


@pytest.mark.asyncio
async def test_go_module_trends_signal_ids_are_deterministic() -> None:
    adapter = GoModuleTrendsAdapter(config={"max_results": 2})

    with patch("max.sources.go_module_trends.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(
            headers={"content-type": "application/json"},
            text=MOCK_INDEX,
            json=MagicMock(side_effect=ValueError("json lines")),
        )
        first = await adapter.fetch(limit=10)
        second = await adapter.fetch(limit=10)

    assert [signal.id for signal in first] == [signal.id for signal in second]
