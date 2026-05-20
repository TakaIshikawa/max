from __future__ import annotations

from max.analysis.evidence_conflict_resolution import (
    build_evidence_conflict_resolution_analysis,
    normalize_topic,
    render_evidence_conflict_resolution_markdown,
)


def test_evidence_conflict_resolution_groups_normalized_topics() -> None:
    report = build_evidence_conflict_resolution_analysis(
        [
            {
                "topic": "SOC2 audit readiness",
                "claim": "Controls are ready",
                "source": "grc_review",
                "polarity": "positive",
                "reliability": 0.8,
                "observed_at": "2026-05-01",
            },
            {
                "topic": "SOC 2 Audit Readiness!",
                "claim": "Evidence is incomplete",
                "source": "external_auditor",
                "polarity": "negative",
                "reliability": 0.9,
                "observed_at": "2026-05-10",
            },
            {
                "topic": "SOC-2 audit readiness",
                "claim": "Pending sampling",
                "source": "control_owner",
                "polarity": "neutral",
                "reliability": 0.6,
                "observed_at": "2026-04-15",
            },
        ]
    )

    assert report["schema_version"] == "max.evidence_conflict_resolution.v1"
    assert report["kind"] == "max.evidence_conflict_resolution"
    assert report["summary"] == {
        "claim_count": 3,
        "topic_count": 1,
        "conflict_count": 1,
        "non_conflict_count": 0,
    }
    row = report["resolution_rows"][0]
    assert row["normalized_topic"] == "soc 2 audit readiness"
    assert row["conflict_status"] == "conflict"
    assert row["positive_count"] == 1
    assert row["negative_count"] == 1
    assert row["neutral_count"] == 1
    assert row["strongest_supporting_source"] == "grc_review"
    assert row["strongest_opposing_source"] == "external_auditor"
    assert row["recommended_action"] == "prefer opposing claim; verify supporting source freshness before closing"


def test_evidence_conflict_resolution_keeps_non_conflicting_topics() -> None:
    report = build_evidence_conflict_resolution_analysis(
        [
            {"topic": "backup restore", "source": "sre", "polarity": "positive", "reliability": 0.7},
            {"topic": "backup restore", "source": "qa", "polarity": "support", "reliability": 0.6},
            {"topic": "data residency", "source": "legal", "polarity": "neutral", "reliability": 0.8},
        ]
    )

    assert report["summary"]["topic_count"] == 2
    assert report["summary"]["conflict_count"] == 0
    rows = {row["normalized_topic"]: row for row in report["resolution_rows"]}
    assert rows["backup restore"]["conflict_status"] == "no_conflict"
    assert rows["backup restore"]["strongest_opposing_source"] is None
    assert rows["data residency"]["recommended_action"] == "collect directional evidence before making a decision"


def test_evidence_conflict_resolution_uses_reliability_then_recency_for_tie_breaks() -> None:
    report = build_evidence_conflict_resolution_analysis(
        [
            {
                "topic": "pricing signal",
                "source": "older_panel",
                "polarity": "positive",
                "reliability": 0.7,
                "observed_at": "2026-01-01",
            },
            {
                "topic": "pricing signal",
                "source": "newer_panel",
                "polarity": "positive",
                "reliability": 0.7,
                "observed_at": "2026-05-01",
            },
            {
                "topic": "pricing signal",
                "source": "sales_calls",
                "polarity": "negative",
                "reliability": 0.69,
                "observed_at": "2026-05-15",
            },
        ]
    )

    row = report["resolution_rows"][0]
    assert row["strongest_supporting_source"] == "newer_panel"
    assert [claim["source"] for claim in row["claims"]][:2] == ["newer_panel", "older_panel"]


def test_evidence_conflict_resolution_markdown_is_deterministic() -> None:
    report = build_evidence_conflict_resolution_analysis(
        [
            {"topic": "z topic", "source": "source_b", "polarity": "positive", "reliability": 0.5},
            {"topic": "a topic", "source": "source_a", "polarity": "negative", "reliability": 0.8},
            {"topic": "a topic", "source": "source_c", "polarity": "positive", "reliability": 0.78},
        ]
    )

    first = render_evidence_conflict_resolution_markdown(report)
    second = render_evidence_conflict_resolution_markdown(report)

    assert first == second
    assert first.startswith("# Evidence Conflict Resolution Analysis")
    assert first.index("### a topic") < first.index("### z topic")
    assert "## Resolution Queue" in first
    assert "## Topic Details" in first
    assert "- Strongest supporting source: source_c" in first
    assert "- Strongest opposing source: source_a" in first


def test_normalize_topic_compacts_noise() -> None:
    assert normalize_topic("  SOC-2: Audit   Readiness!! ") == "soc 2 audit readiness"
