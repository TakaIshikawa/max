"""Tests for Agent-to-Agent specification adapter."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from max.sources.a2a_spec import A2ASpecAdapter
from max.sources.registry import get_adapter, get_adapter_metadata, list_adapters, reload_registry
from max.types.signal import SignalSourceType


@pytest.mark.asyncio
async def test_markdown_local_spec_emits_protocol_opportunity_signals(tmp_path) -> None:
    spec_path = tmp_path / "a2a-spec-2026.md"
    spec_path.write_text(
        "# Agent-to-Agent Specification\n\n"
        "## Agent Card Discovery\n\n"
        "Updated: 2026-Q1\n"
        "Evidence: Clients need a standard way to inspect agent card skills.\n"
        "Summary: Agent card discovery advertises capabilities, skills, and endpoint metadata "
        "so independent agents can route tasks across vendors.\n\n"
        "## Task lifecycle states\n\n"
        "Summary: Tasks move from submitted to working, completed, failed, or canceled states "
        "with artifacts and messages preserved for downstream synthesis.\n\n"
        "## Security requirements\n\n"
        "Summary: OAuth scopes and bearer token requirements define authorization boundaries "
        "for remote agent invocation.\n",
        encoding="utf-8",
    )
    adapter = A2ASpecAdapter(config={"local_paths": [str(spec_path)]})

    signals = await adapter.fetch(limit=10)
    repeated = await adapter.fetch(limit=10)

    assert [signal.id for signal in signals] == [signal.id for signal in repeated]
    by_section = {signal.metadata["section"]: signal for signal in signals}
    assert set(by_section) == {
        "Agent Card Discovery",
        "Task lifecycle states",
        "Security requirements",
    }
    discovery = by_section["Agent Card Discovery"]
    assert discovery.id.startswith("a2a_spec:")
    assert discovery.source_type == SignalSourceType.ROADMAP
    assert discovery.source_adapter == "a2a_spec"
    assert discovery.title == "Agent Card Discovery"
    assert "route tasks across vendors" in discovery.content
    assert discovery.metadata["categories"] == ["capability"]
    assert discovery.metadata["updated_at"] == "2026-Q1"
    assert discovery.metadata["evidence_snippet"].startswith("Clients need")
    assert discovery.metadata["signal_role"] == "solution"
    assert {"a2a", "protocol", "interoperability", "capability", "agent", "card"}.issubset(
        set(discovery.tags)
    )

    lifecycle = by_section["Task lifecycle states"]
    assert "lifecycle" in lifecycle.metadata["categories"]
    assert "artifacts and messages" in lifecycle.content

    security = by_section["Security requirements"]
    assert "security" in security.metadata["categories"]
    assert {"oauth", "authorization"}.isdisjoint(set(security.tags)) is False


@pytest.mark.asyncio
async def test_json_local_spec_emits_stable_ids_and_gap_signals(tmp_path) -> None:
    spec_path = tmp_path / "a2a-spec.json"
    spec_path.write_text(
        json.dumps(
            {
                "spec_updates": [
                    {
                        "title": "Streaming transport negotiation",
                        "section": "Transports",
                        "summary": (
                            "HTTP streaming and SSE behavior need common negotiation "
                            "so clients can select compatible transports."
                        ),
                        "updated_at": "2026-03-15",
                        "keywords": ["streaming", "sse"],
                    },
                    {
                        "title": "Conformance profile gap",
                        "area": "Interoperability",
                        "description": (
                            "The specification leaves vendor extension compatibility "
                            "ambiguous, creating a conformance testing gap."
                        ),
                        "tags": ["conformance", "extensions"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    adapter = A2ASpecAdapter(config={"local_paths": [str(spec_path)]})

    signals = await adapter.fetch(limit=10)
    repeated = await adapter.fetch(limit=10)

    assert [signal.id for signal in signals] == [signal.id for signal in repeated]
    assert [signal.title for signal in signals] == [
        "Streaming transport negotiation",
        "Conformance profile gap",
    ]
    assert "transport" in signals[0].metadata["categories"]
    assert {"a2a", "protocol", "interoperability", "transport", "streaming", "sse"}.issubset(
        set(signals[0].tags)
    )
    assert signals[1].metadata["categories"] == ["interoperability-gap"]
    assert signals[1].metadata["signal_role"] == "problem"
    assert "conformance testing gap" in signals[1].content


@pytest.mark.asyncio
async def test_keyword_section_max_items_and_examples_filter_results(tmp_path) -> None:
    spec_path = tmp_path / "a2a-spec.md"
    spec_path.write_text(
        "## Transport negotiation\n\n"
        "HTTP streaming transport resumption is required for resilient remote agents.\n\n"
        "## Transport example\n\n"
        "Example: HTTP streaming sample code demonstrates resumption.\n\n"
        "## Security scopes\n\n"
        "OAuth scope requirements define permissions for remote invocation.\n",
        encoding="utf-8",
    )
    adapter = A2ASpecAdapter(
        config={
            "local_paths": [str(spec_path)],
            "sections": ["Transport"],
            "keywords": ["resumption"],
            "max_items": 1,
            "include_examples": False,
        }
    )

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["section"] == "Transport negotiation"
    assert signals[0].metadata["matched_keywords"] == ["resumption"]
    assert signals[0].metadata["include_examples"] is False
    assert "resumption" in signals[0].tags


@pytest.mark.asyncio
async def test_plain_text_spec_snapshot_is_supported(tmp_path) -> None:
    spec_path = tmp_path / "a2a-spec.txt"
    spec_path.write_text(
        "Lifecycle state transitions remain underspecified for failed and canceled tasks. "
        "This interoperability gap makes downstream task synthesis brittle.\n\n"
        "Security requirements for bearer tokens and OAuth scopes should be discoverable.",
        encoding="utf-8",
    )
    adapter = A2ASpecAdapter(config={"local_paths": [str(spec_path)]})

    signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == [
        "Lifecycle state transitions remain underspecified for failed and canceled tasks",
        "Security requirements for bearer tokens and OAuth scopes should be",
    ]
    assert "interoperability-gap" in signals[0].metadata["categories"]
    assert "lifecycle" in signals[0].metadata["categories"]
    assert "security" in signals[1].metadata["categories"]


def test_a2a_spec_adapter_is_registered() -> None:
    with patch("max.config.MAX_ADAPTERS", "a2a_spec"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()

        assert list_adapters() == ["a2a_spec"]
        adapter = get_adapter("a2a_spec")

    assert adapter.name == "a2a_spec"


def test_a2a_spec_adapter_metadata_documents_config_keys() -> None:
    with patch("max.config.MAX_ADAPTERS", "a2a_spec"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()
        metadata = get_adapter_metadata()

    assert set(metadata) == {"a2a_spec"}
    assert metadata["a2a_spec"].config_keys == [
        "spec_urls",
        "local_paths",
        "sections",
        "keywords",
        "max_items",
        "include_examples",
    ]
    assert metadata["a2a_spec"].required_keys == []
    assert "Agent-to-Agent specification" in metadata["a2a_spec"].description
