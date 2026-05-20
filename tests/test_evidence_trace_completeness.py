from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis.evidence_trace_completeness import (
    KIND,
    SCHEMA_VERSION,
    build_evidence_trace_completeness_audit,
    render_evidence_trace_completeness_audit,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


def test_evidence_trace_completeness_audit_reports_missing_and_unresolved_links(store: Store) -> None:
    _seed_trace(store)

    report = build_evidence_trace_completeness_audit(store, concentration_threshold=0.6)
    repeated = build_evidence_trace_completeness_audit(store, concentration_threshold=0.6)

    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert set(report) == {
        "schema_version",
        "kind",
        "filters",
        "summary",
        "incomplete_ideas",
        "incomplete_insights",
        "source_concentration",
        "next_actions",
    }
    assert report["summary"]["idea_count"] == 4
    assert report["summary"]["complete_idea_count"] == 1
    assert report["summary"]["idea_completeness_pct"] == 25.0
    assert report["summary"]["complete_insight_count"] == 1
    assert report["summary"]["unresolved_signal_link_count"] == 2
    assert [row["id"] for row in report["incomplete_ideas"]] == ["idea-missing", "idea-unresolved", "idea-no-insight"]
    assert report["incomplete_ideas"][1]["unresolved_signal_ids"] == ["sig-missing"]
    assert [row["id"] for row in report["incomplete_insights"]] == ["ins-bad", "ins-empty"]
    assert report["source_concentration"][0]["source_adapter"] == "github"
    assert report["source_concentration"][0]["risk_level"] == "high"


def test_evidence_trace_completeness_audit_renders_and_validates(store: Store) -> None:
    _seed_trace(store)
    report = build_evidence_trace_completeness_audit(store, concentration_threshold=0.6)

    assert json.loads(render_evidence_trace_completeness_audit(report, fmt="json")) == report
    markdown = render_evidence_trace_completeness_audit(report, fmt="markdown")
    assert markdown.startswith("# Evidence Trace Completeness Audit")
    rows = list(csv.DictReader(StringIO(render_evidence_trace_completeness_audit(report, fmt="csv"))))
    assert rows[0]["section"] == "idea"
    assert any(row["section"] == "source_concentration" for row in rows)

    with pytest.raises(ValueError, match="limit must be at least 1"):
        build_evidence_trace_completeness_audit(store, limit=0)
    with pytest.raises(ValueError, match="concentration_threshold must be greater than 0 and at most 1"):
        build_evidence_trace_completeness_audit(store, concentration_threshold=0)
    with pytest.raises(ValueError, match="Unsupported evidence trace completeness audit format: yaml"):
        render_evidence_trace_completeness_audit(report, fmt="yaml")


def _seed_trace(store: Store) -> None:
    store.insert_signal(_signal("sig-good", "github"))
    store.insert_signal(_signal("sig-other", "reddit"))
    store.insert_insight(_insight("ins-good", ["sig-good"]))
    store.insert_insight(_insight("ins-bad", ["sig-missing"]))
    store.insert_insight(_insight("ins-empty", []))
    store.insert_buildable_unit(_unit("idea-complete", ["ins-good"], ["sig-good"]))
    store.insert_buildable_unit(_unit("idea-unresolved", ["ins-bad"], ["sig-missing"]))
    store.insert_buildable_unit(_unit("idea-missing", [], []))
    store.insert_buildable_unit(_unit("idea-no-insight", [], ["sig-good"]))


def _signal(signal_id: str, adapter: str) -> Signal:
    return Signal(
        id=signal_id,
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter,
        title=signal_id,
        content="content",
        url=f"https://example.com/{signal_id}",
    )


def _insight(insight_id: str, evidence: list[str]) -> Insight:
    return Insight(
        id=insight_id,
        category=InsightCategory.GAP,
        title=insight_id,
        summary="summary",
        evidence=evidence,
    )


def _unit(idea_id: str, insights: list[str], signals: list[str]) -> BuildableUnit:
    return BuildableUnit(
        id=idea_id,
        title=idea_id,
        one_liner="one",
        category=BuildableCategory.CLI_TOOL,
        problem="problem",
        solution="solution",
        value_proposition="value",
        inspiring_insights=insights,
        evidence_signals=signals,
        status="evaluated",
    )
