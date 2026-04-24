"""Tests for agent failure dataset source adapter."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.agent_failure_dataset import AgentFailureDatasetAdapter
from max.sources.base import AdapterFetchError
from max.sources.errors import SourceParseError
from max.types.signal import SignalSourceType


@pytest.mark.asyncio
async def test_csv_fixture_rows_produce_failure_data_signals(tmp_path) -> None:
    fixture = tmp_path / "agent_failures.csv"
    fixture.write_text(
        "workflow,failure_type,severity,model,framework,reproduction_url,failure_rate,notes\n"
        "browser checkout,tool misuse,high,Claude 3.5,LangGraph,"
        "https://example.com/repro,42%,Agent clicked stale selector\n",
        encoding="utf-8",
    )
    adapter = AgentFailureDatasetAdapter(config={"local_paths": [str(fixture)]})

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id.startswith("agent_failure_dataset:")
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "agent_failure_dataset"
    assert signal.title == "Agent failure: browser checkout - tool misuse"
    assert signal.url == "https://example.com/repro"
    assert signal.metadata == {
        "task": "browser checkout",
        "workflow": "browser checkout",
        "failure_type": "tool misuse",
        "severity": 3.0,
        "severity_label": "high",
        "model": "Claude 3.5",
        "framework": "LangGraph",
        "reproduction_url": "https://example.com/repro",
        "success_rate": None,
        "failure_rate": 0.42,
        "notes": "Agent clicked stale selector",
        "signal_role": "problem",
    }
    assert "high-severity" in signal.tags
    assert signal.signal_role == "problem"


@pytest.mark.asyncio
async def test_jsonl_fixture_rows_parse_success_rate_and_aliases(tmp_path) -> None:
    fixture = tmp_path / "failures.jsonl"
    fixture.write_text(
        json.dumps(
            {
                "task": "multi-step refund",
                "type": "planning",
                "severity_score": 2.5,
                "llm": "gpt-4.1",
                "agent_framework": "AutoGen",
                "successRate": 0.31,
                "summary": "Agent loses state across handoffs",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    adapter = AgentFailureDatasetAdapter(config={"local_paths": [str(fixture)]})

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.metadata["task"] == "multi-step refund"
    assert signal.metadata["failure_type"] == "planning"
    assert signal.metadata["severity"] == 2.5
    assert signal.metadata["model"] == "gpt-4.1"
    assert signal.metadata["framework"] == "AutoGen"
    assert signal.metadata["success_rate"] == 0.31
    assert signal.metadata["failure_rate"] is None
    assert "Agent loses state across handoffs" in signal.content


@pytest.mark.asyncio
async def test_filters_by_failure_type_and_min_severity(tmp_path) -> None:
    fixture = tmp_path / "failures.json"
    fixture.write_text(
        json.dumps(
            {
                "rows": [
                    {"task": "A", "failure_type": "tool misuse", "severity": "critical"},
                    {"task": "B", "failure_type": "planning", "severity": "critical"},
                    {"task": "C", "failure_type": "tool misuse", "severity": "medium"},
                ]
            }
        ),
        encoding="utf-8",
    )
    adapter = AgentFailureDatasetAdapter(
        config={
            "local_paths": [str(fixture)],
            "failure_type_filters": ["tool misuse"],
            "min_severity": 3,
        }
    )

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["task"] == "A"
    assert signals[0].metadata["severity"] == 4.0


@pytest.mark.asyncio
async def test_malformed_rows_are_skipped_and_logged(tmp_path, caplog) -> None:
    fixture = tmp_path / "failures.csv"
    fixture.write_text(
        "task,failure_type,severity,notes\n"
        "usable,tool misuse,3,kept\n"
        ",planning,4,missing task\n"
        "missing type,,4,missing failure type\n"
        "bad severity,tool misuse,unknown,bad severity\n",
        encoding="utf-8",
    )
    adapter = AgentFailureDatasetAdapter(config={"local_paths": [str(fixture)]})

    signals = await adapter.fetch(limit=10)

    assert [signal.metadata["task"] for signal in signals] == ["usable"]
    assert "skipping malformed row" in caplog.text


@pytest.mark.asyncio
async def test_malformed_json_raises_source_parse_error(tmp_path) -> None:
    fixture = tmp_path / "bad.json"
    fixture.write_text("{not json", encoding="utf-8")
    adapter = AgentFailureDatasetAdapter(config={"local_paths": [str(fixture)]})

    with pytest.raises(SourceParseError, match="Malformed agent failure JSON"):
        await adapter.fetch(limit=10)


@pytest.mark.asyncio
async def test_dataset_url_fetch_errors_are_logged_and_skipped(caplog) -> None:
    adapter = AgentFailureDatasetAdapter(
        config={"dataset_urls": ["https://example.com/failures.jsonl"], "format": "jsonl"}
    )

    async def mock_fetch(url: str, client, *, adapter_name: str):
        raise AdapterFetchError(adapter_name, 500, url)

    with patch("max.sources.agent_failure_dataset.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=10)

    assert signals == []
    assert "failed to fetch dataset URL" in caplog.text


@pytest.mark.asyncio
async def test_dataset_url_rows_are_fetched_and_parsed() -> None:
    adapter = AgentFailureDatasetAdapter(
        config={"dataset_urls": ["https://example.com/failures.json"], "format": "json"}
    )
    response = MagicMock()
    response.text = json.dumps(
        [{"workflow": "agent eval", "failureType": "memory", "impact": "low"}]
    )

    with patch(
        "max.sources.agent_failure_dataset.fetch_with_retry",
        new=AsyncMock(return_value=response),
    ) as mock_fetch:
        signals = await adapter.fetch(limit=10)

    assert mock_fetch.call_args.args[0] == "https://example.com/failures.json"
    assert len(signals) == 1
    assert signals[0].metadata["failure_type"] == "memory"
    assert signals[0].metadata["severity"] == 1.0
