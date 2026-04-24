"""Tests for context budget waste analysis."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from max.analysis.context_budget import build_context_budget_waste_report
from max.llm.client import estimate_text_tokens
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def store():
    s = Store(db_path=":memory:")
    yield s
    s.close()


def _signal(signal_id: str, *, adapter: str, fetched_at: datetime) -> Signal:
    return Signal(
        id=signal_id,
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter,
        title=f"Signal {signal_id}",
        content=f"Context payload for {signal_id} from {adapter}.",
        url=f"https://example.com/{signal_id}",
        fetched_at=fetched_at,
        credibility=0.7,
    )


def test_context_budget_report_counts_reuse_staleness_and_savings(store):
    now = datetime.now(timezone.utc)
    stale_at = now - timedelta(days=90)
    fresh_at = now - timedelta(days=2)

    store.insert_signal(_signal("sig-used", adapter="github", fetched_at=fresh_at))
    store.insert_signal(_signal("sig-unused", adapter="github", fetched_at=fresh_at))
    store.insert_signal(_signal("sig-stale", adapter="reddit", fetched_at=stale_at))

    store.insert_insight(
        Insight(
            id="ins-used",
            category=InsightCategory.GAP,
            title="Used insight",
            summary="A reused signal supports an idea.",
            evidence=["sig-used"],
            confidence=0.8,
        )
    )
    store.insert_buildable_unit(
        BuildableUnit(
            id="bu-used",
            title="Used idea",
            one_liner="Uses evidence",
            category=BuildableCategory.APPLICATION,
            ideation_mode=IdeationMode.DIRECT,
            problem="Too much context",
            solution="Prune unused sources",
            value_proposition="Lower LLM spend",
            inspiring_insights=["ins-used"],
            evidence_signals=["sig-used"],
        )
    )

    report = build_context_budget_waste_report(store, days=30, min_reuse_count=1)

    assert report["total_signals"] == 3
    assert report["reused_signal_count"] == 1
    assert report["low_utility_signal_count"] == 2
    assert report["stale_signal_count"] == 1
    assert report["projected_token_savings"] > 0
    assert report["evidence_pack_estimated_tokens"] > 0

    by_adapter = {item["source_adapter"]: item for item in report["adapters"]}
    assert by_adapter["github"]["signal_count"] == 2
    assert by_adapter["github"]["reused_signal_count"] == 1
    assert by_adapter["github"]["candidate_signal_ids"] == ["sig-unused"]
    assert by_adapter["reddit"]["stale_signal_count"] == 1
    assert by_adapter["reddit"]["candidate_signal_ids"] == ["sig-stale"]

    stale_tokens = estimate_text_tokens(
        "\n".join(
            [
                "Signal sig-stale",
                "Context payload for sig-stale from reddit.",
                "https://example.com/sig-stale",
            ]
        )
    )
    assert by_adapter["reddit"]["projected_token_savings"] >= stale_tokens


def test_context_budget_report_filters_source_adapter(store):
    now = datetime.now(timezone.utc)
    store.insert_signal(_signal("sig-github", adapter="github", fetched_at=now))
    store.insert_signal(_signal("sig-reddit", adapter="reddit", fetched_at=now))

    report = build_context_budget_waste_report(
        store,
        source_adapter="github",
        min_reuse_count=1,
    )

    assert report["source_adapter_filter"] == "github"
    assert report["total_signals"] == 1
    assert [item["source_adapter"] for item in report["adapters"]] == ["github"]
