from __future__ import annotations

from max.analysis.insight_staleness_audit import (
    build_insight_staleness_audit,
    render_insight_staleness_audit_markdown,
)


def test_insight_staleness_audit_flags_old_latest_evidence() -> None:
    audit = build_insight_staleness_audit(
        [
            {
                "insight_id": "old-pricing",
                "evidence_dates": ["2026-01-15", "2026-02-01"],
                "corroborating_source_count": 2,
                "confidence": 0.7,
            }
        ],
        as_of="2026-05-20",
        stale_after_days=60,
    )

    assert audit["schema_version"] == "max.insight_staleness_audit.v1"
    assert audit["kind"] == "max.insight_staleness_audit"
    row = audit["staleness_rows"][0]
    assert row["insight_id"] == "old-pricing"
    assert row["age_days"] == 108
    assert row["staleness_tier"] == "stale"
    assert row["refresh_action"] == "collect recent corroboration because latest evidence is 108 day(s) old"


def test_insight_staleness_audit_marks_strong_recent_corroboration_current() -> None:
    audit = build_insight_staleness_audit(
        [
            {
                "insight_id": "mixed-age",
                "evidence": [
                    {"source": "calls", "observed_at": "2026-01-01"},
                    {"source": "survey", "observed_at": "2026-05-12"},
                    {"source": "tickets", "observed_at": "2026-05-14"},
                ],
                "confidence": 0.62,
            }
        ],
        as_of="2026-05-20",
        stale_after_days=30,
        current_after_days=14,
        strong_corroboration_count=2,
    )

    row = audit["staleness_rows"][0]
    assert row["age_days"] == 6
    assert row["recent_corroboration_count"] == 2
    assert row["corroborating_source_count"] == 3
    assert row["staleness_tier"] == "current"


def test_insight_staleness_audit_includes_required_row_fields_and_sorting() -> None:
    audit = build_insight_staleness_audit(
        [
            {"insight_id": "current", "evidence_dates": ["2026-05-15"], "corroborating_source_count": 2},
            {"insight_id": "watch", "evidence_dates": ["2026-04-10"], "corroborating_source_count": 1},
            {"insight_id": "stale", "evidence_dates": ["2026-02-01"], "corroborating_source_count": 3},
        ],
        as_of="2026-05-20",
        stale_after_days=60,
    )

    assert [row["insight_id"] for row in audit["staleness_rows"]] == ["stale", "watch", "current"]
    row = audit["staleness_rows"][0]
    assert set(row) >= {
        "insight_id",
        "age_days",
        "corroborating_source_count",
        "confidence",
        "staleness_tier",
        "refresh_action",
    }


def test_insight_staleness_audit_markdown_is_deterministic() -> None:
    audit = build_insight_staleness_audit(
        [
            {"insight_id": "b", "evidence_dates": ["2026-05-01"], "corroborating_source_count": 2},
            {"insight_id": "a", "evidence_dates": ["2026-01-01"], "corroborating_source_count": 2},
        ],
        as_of="2026-05-20",
        stale_after_days=45,
    )

    first = render_insight_staleness_audit_markdown(audit)
    second = render_insight_staleness_audit_markdown(audit)

    assert first == second
    assert first.startswith("# Insight Staleness Audit")
    assert first.index("### a") < first.index("### b")
    assert "- Staleness tier:" in first
    assert "- Refresh action:" in first
