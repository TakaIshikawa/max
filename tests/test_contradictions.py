"""Tests for contradiction analysis."""

from __future__ import annotations

from max.analysis.contradictions import (
    build_idea_contradiction_report,
    build_insight_contradiction_report,
    normalize_claim_text,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


def _signal(signal_id: str, *, adapter: str, sentiment: str, claim: str) -> Signal:
    return Signal(
        id=signal_id,
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter,
        title=claim,
        content=f"{sentiment} evidence for {claim}",
        url=f"https://example.com/{signal_id}",
        credibility=0.8,
        metadata={
            "normalized_claim": claim,
            "sentiment": sentiment,
            "signal_role": "problem",
        },
    )


def _unit() -> BuildableUnit:
    return BuildableUnit(
        id="bu-conflict",
        title="Conflict Idea",
        one_liner="An idea with conflicting evidence",
        category=BuildableCategory.APPLICATION,
        problem="Evidence conflicts",
        solution="Review it",
        value_proposition="Clearer evidence",
        inspiring_insights=["ins-conflict"],
        evidence_signals=["sig-positive", "sig-negative"],
    )


def test_normalize_claim_text_removes_case_punctuation_and_urls() -> None:
    assert normalize_claim_text("API latency improves! https://example.com/x") == "api latency improves"


def test_insight_contradictions_group_by_normalized_claim() -> None:
    with Store(":memory:") as store:
        store.insert_signal(
            _signal(
                "sig-positive",
                adapter="forum-a",
                sentiment="positive",
                claim="API latency improves",
            )
        )
        store.insert_signal(
            _signal(
                "sig-negative",
                adapter="forum-b",
                sentiment="negative",
                claim="API latency improves",
            )
        )
        insight = Insight(
            id="ins-conflict",
            category=InsightCategory.GAP,
            title="Latency conflict",
            summary="Signals disagree",
            evidence=["sig-positive", "sig-negative"],
        )
        store.insert_insight(insight)

        report = build_insight_contradiction_report(insight, store)

    assert report["entity_type"] == "insight"
    assert report["contradiction_count"] == 1
    contradiction = report["contradictions"][0]
    assert contradiction["severity"] == "medium"
    assert contradiction["involved_signal_ids"] == ["sig-negative", "sig-positive"]
    assert contradiction["sentiments"]["positive"] == ["sig-positive"]
    assert contradiction["sentiments"]["negative"] == ["sig-negative"]
    assert "Review medium-severity conflict" in contradiction["suggested_review_note"]


def test_idea_contradictions_use_evidence_chain_and_dedupe_direct_signals() -> None:
    with Store(":memory:") as store:
        store.insert_signal(
            _signal(
                "sig-positive",
                adapter="forum-a",
                sentiment="support",
                claim="Buyers need audit logs",
            )
        )
        store.insert_signal(
            _signal(
                "sig-negative",
                adapter="forum-b",
                sentiment="refutes",
                claim="Buyers need audit logs",
            )
        )
        insight = Insight(
            id="ins-conflict",
            category=InsightCategory.GAP,
            title="Audit conflict",
            summary="Signals disagree",
            evidence=["sig-positive", "sig-negative"],
        )
        store.insert_insight(insight)
        unit = store.insert_buildable_unit(_unit())

        report = build_idea_contradiction_report(unit, store)

    assert report["entity_type"] == "idea"
    assert report["signal_count"] == 2
    assert report["contradiction_count"] == 1
    assert report["contradictions"][0]["normalized_claim"] == "buyers need audit logs"
