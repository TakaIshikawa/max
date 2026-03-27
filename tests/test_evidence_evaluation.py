"""Tests for evidence-grounded evaluation — prompts, engine, and chain resolution."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from max.evaluation.prompts import build_evaluation_prompt
from max.pipeline.runner import _resolve_evidence_chain
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test_evidence.db")
    s = Store(db_path=db_path)
    yield s
    s.close()


def _make_signal(id: str, title: str, content: str) -> Signal:
    return Signal(
        id=id,
        source_type=SignalSourceType.FORUM,
        source_adapter="test",
        title=title,
        content=content,
        url=f"https://example.com/{id}",
        tags=["test"],
        credibility=0.7,
    )


def _make_insight(id: str, title: str, evidence: list[str]) -> Insight:
    return Insight(
        id=id,
        category=InsightCategory.GAP,
        title=title,
        summary=f"Summary for {title}",
        evidence=evidence,
        confidence=0.8,
        domains=["testing"],
    )


def _make_unit(
    id: str,
    inspiring_insights: list[str] | None = None,
    evidence_signals: list[str] | None = None,
) -> BuildableUnit:
    return BuildableUnit(
        id=id,
        title="Test Unit",
        one_liner="Test one liner",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Test problem",
        solution="Test solution",
        value_proposition="Test value",
        inspiring_insights=inspiring_insights or [],
        evidence_signals=evidence_signals or [],
    )


# ── Prompt tests ──────────────────────────────────────────────────


def test_evaluation_prompt_without_evidence():
    prompt = build_evaluation_prompt('{"title": "Test"}')
    assert "SUPPORTING EVIDENCE" not in prompt
    assert "fact-check" not in prompt


def test_evaluation_prompt_with_evidence():
    evidence = json.dumps({"insights": [{"title": "Gap A"}], "signals": [{"title": "Signal 1"}]})
    prompt = build_evaluation_prompt('{"title": "Test"}', evidence_json=evidence)
    assert "SUPPORTING EVIDENCE" in prompt
    assert "fact-check" in prompt
    assert "Gap A" in prompt
    assert "Signal 1" in prompt


# ── evaluate() param passthrough ──────────────────────────────────


def test_evaluate_passes_evidence_to_prompt():
    from max.evaluation.engine import evaluate

    unit = _make_unit("bu-001")
    evidence = '{"insights": [], "signals": []}'

    mock_dim = type("Dim", (), {"value": 5.0, "confidence": 0.7, "reasoning": "test"})()
    mock_result = type("EvalOut", (), {
        "pain_severity": mock_dim,
        "addressable_scale": mock_dim,
        "build_effort": mock_dim,
        "composability": mock_dim,
        "competitive_density": mock_dim,
        "timing_fit": mock_dim,
        "compounding_value": mock_dim,
        "strengths": ["good"],
        "weaknesses": ["bad"],
        "recommendation": "maybe",
    })()

    with patch("max.evaluation.engine.structured_call", return_value=mock_result) as mock_call:
        evaluate(unit, evidence=evidence)

    call_kwargs = mock_call.call_args
    prompt = call_kwargs.kwargs.get("prompt") or call_kwargs[1].get("prompt", call_kwargs[0][1])
    assert "SUPPORTING EVIDENCE" in prompt


def test_evaluate_without_evidence_no_block():
    from max.evaluation.engine import evaluate

    unit = _make_unit("bu-001")

    mock_dim = type("Dim", (), {"value": 5.0, "confidence": 0.7, "reasoning": "test"})()
    mock_result = type("EvalOut", (), {
        "pain_severity": mock_dim,
        "addressable_scale": mock_dim,
        "build_effort": mock_dim,
        "composability": mock_dim,
        "competitive_density": mock_dim,
        "timing_fit": mock_dim,
        "compounding_value": mock_dim,
        "strengths": ["good"],
        "weaknesses": ["bad"],
        "recommendation": "maybe",
    })()

    with patch("max.evaluation.engine.structured_call", return_value=mock_result) as mock_call:
        evaluate(unit)

    call_kwargs = mock_call.call_args
    prompt = call_kwargs.kwargs.get("prompt") or call_kwargs[1].get("prompt", call_kwargs[0][1])
    assert "SUPPORTING EVIDENCE" not in prompt


# ── Evidence chain resolution ─────────────────────────────────────


def test_resolve_chain_no_references(store):
    """Unit with no inspiring_insights or evidence_signals → None."""
    unit = _make_unit("bu-001")
    assert _resolve_evidence_chain(unit, store) is None


def test_resolve_chain_with_insight_and_signal(store):
    """Full chain: unit → insight → signal."""
    store.insert_signal(_make_signal("sig-001", "HN Post", "MCP servers need testing"))
    store.insert_insight(_make_insight("ins-001", "Testing gap", ["sig-001"]))

    unit = _make_unit("bu-001", inspiring_insights=["ins-001"])
    result = _resolve_evidence_chain(unit, store)
    assert result is not None

    data = json.loads(result)
    assert len(data["insights"]) == 1
    assert data["insights"][0]["id"] == "ins-001"
    assert len(data["signals"]) == 1
    assert data["signals"][0]["id"] == "sig-001"


def test_resolve_chain_with_direct_evidence_signals(store):
    """Unit has direct evidence_signals (not via insights)."""
    store.insert_signal(_make_signal("sig-002", "Direct signal", "Direct evidence"))

    unit = _make_unit("bu-001", evidence_signals=["sig-002"])
    result = _resolve_evidence_chain(unit, store)
    assert result is not None

    data = json.loads(result)
    assert len(data["signals"]) == 1
    assert data["signals"][0]["id"] == "sig-002"


def test_resolve_chain_deduplicates_signals(store):
    """Same signal referenced via insight AND directly → appears once."""
    store.insert_signal(_make_signal("sig-001", "Shared signal", "Referenced twice"))
    store.insert_insight(_make_insight("ins-001", "Gap", ["sig-001"]))

    unit = _make_unit("bu-001", inspiring_insights=["ins-001"], evidence_signals=["sig-001"])
    result = _resolve_evidence_chain(unit, store)
    data = json.loads(result)
    assert len(data["signals"]) == 1


def test_resolve_chain_missing_insight_graceful(store):
    """Non-existent insight ID → skipped gracefully."""
    unit = _make_unit("bu-001", inspiring_insights=["ins-nonexistent"])
    assert _resolve_evidence_chain(unit, store) is None


def test_resolve_chain_truncates_content(store):
    """Signal content longer than 500 chars gets truncated."""
    long_content = "x" * 1000
    store.insert_signal(_make_signal("sig-001", "Long signal", long_content))

    unit = _make_unit("bu-001", evidence_signals=["sig-001"])
    result = _resolve_evidence_chain(unit, store)
    data = json.loads(result)
    assert len(data["signals"][0]["content"]) == 500
