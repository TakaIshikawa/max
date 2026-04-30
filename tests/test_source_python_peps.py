"""Tests for the Python PEP source adapter."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from max.sources.python_peps import DEFAULT_INDEX_URL, PythonPepsAdapter, _parse_pep_index
from max.types.signal import SignalSourceType


PEP_INDEX = {
    "peps": {
        "621": {
            "number": 621,
            "title": "Storing project metadata in pyproject.toml",
            "status": "Final",
            "type": "Standards Track",
            "topic": "Packaging",
            "url": "https://peps.python.org/pep-0621/",
            "created": "11-Nov-2020",
            "authors": ["Brett Cannon", "Dustin Ingram"],
            "abstract": "Defines how package metadata is stored in pyproject.toml.",
        },
        "722": {
            "title": "Dependency specification for single-file scripts",
            "status": "Accepted",
            "type": "Standards Track",
            "topic": "Packaging",
            "url": "/pep-0722/",
            "created": "2023-07-01",
            "authors": "Ofek Lev",
            "abstract": "Tooling can discover script dependencies without packaging a project.",
        },
        "594": {
            "number": "PEP 594",
            "title": "Removing dead batteries from the standard library",
            "status": "Final",
            "type": "Standards Track",
            "topic": "Standard Library",
            "abstract": "Compatibility work for removed modules.",
        },
        "9999": {
            "number": 9999,
            "title": "Rejected packaging idea",
            "status": "Rejected",
            "type": "Informational",
            "topic": "Packaging",
        },
    }
}


def _response(text: str) -> MagicMock:
    response = MagicMock()
    response.text = text
    response.headers = {}
    return response


def test_parse_pep_index_accepts_peps_json_mapping() -> None:
    items = _parse_pep_index(json.dumps(PEP_INDEX))

    assert [str(item["number"]) for item in items[:2]] == ["621", "722"]
    assert items[0]["title"] == "Storing project metadata in pyproject.toml"


@pytest.mark.asyncio
async def test_python_peps_fetch_emits_normalized_deterministic_signals() -> None:
    adapter = PythonPepsAdapter(config={"content": json.dumps(PEP_INDEX), "max_results": 10})

    signals = await adapter.fetch(limit=10)
    repeated = await adapter.fetch(limit=10)

    assert [signal.id for signal in signals] == [signal.id for signal in repeated]
    assert [signal.metadata["pep_number"] for signal in signals] == ["621", "722"]

    first = signals[0]
    assert first.id.startswith("python_peps:")
    assert first.source_type == SignalSourceType.ROADMAP
    assert first.source_adapter == "python_peps"
    assert first.title == "PEP 621: Storing project metadata in pyproject.toml"
    assert first.url == "https://peps.python.org/pep-0621/"
    assert first.author == "Brett Cannon, Dustin Ingram"
    assert first.published_at is not None
    assert first.metadata["status"] == "Final"
    assert first.metadata["type"] == "Standards Track"
    assert first.metadata["topic"] == "Packaging"
    assert first.metadata["url"] == first.url
    assert {"standards", "python", "pep", "final", "status-final", "packaging"}.issubset(
        set(first.metadata["normalized_tags"])
    )
    assert first.tags == first.metadata["normalized_tags"]
    assert "pyproject" in first.tags

    second = signals[1]
    assert second.title == "PEP 722: Dependency specification for single-file scripts"
    assert second.url == "https://peps.python.org/pep-0722/"
    assert {"accepted", "status-accepted", "dependency"}.issubset(set(second.tags))


@pytest.mark.asyncio
async def test_python_peps_honors_status_topic_keyword_and_limit_filters() -> None:
    adapter = PythonPepsAdapter(
        config={
            "content": json.dumps(PEP_INDEX),
            "statuses": ["accepted", "final"],
            "topics": ["packaging"],
            "keywords": ["dependency"],
            "max_results": 5,
        }
    )

    signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].metadata["pep_number"] == "722"
    assert signals[0].metadata["matched_keywords"] == ["dependency"]


@pytest.mark.asyncio
async def test_python_peps_fetches_configured_index_url_with_injected_fetch() -> None:
    adapter = PythonPepsAdapter(config={"index_url": "https://example.test/peps.json"})

    with patch(
        "max.sources.python_peps.fetch_with_retry",
        return_value=_response(json.dumps(PEP_INDEX)),
    ) as mock_fetch:
        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["pep_number"] for signal in signals] == ["621", "722"]
    assert mock_fetch.call_args.args[0] == "https://example.test/peps.json"
    assert mock_fetch.call_args.kwargs["adapter_name"] == "python_peps"


@pytest.mark.asyncio
async def test_python_peps_defaults_to_peps_api_url() -> None:
    adapter = PythonPepsAdapter()

    with patch(
        "max.sources.python_peps.fetch_with_retry",
        return_value=_response(json.dumps(PEP_INDEX)),
    ) as mock_fetch:
        await adapter.fetch(limit=1)

    assert mock_fetch.call_args.args[0] == DEFAULT_INDEX_URL
