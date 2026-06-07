from __future__ import annotations

from max.exports import generate_spec_evidence_citation_quality_report


def test_spec_evidence_citation_quality_flags_missing_stale_and_unsupported() -> None:
    report = generate_spec_evidence_citation_quality_report(
        [
            {"spec_id": "s-ok", "citations": [{"created_at": "2026-06-01"}]},
            {"spec_id": "s-stale", "citations": [{"created_at": "2026-01-01"}]},
            {"spec_id": "s-blocked", "citation_count": 0, "unsupported_criteria_count": 1},
        ],
        stale_after_days=30,
        minimum_citation_count=1,
        as_of="2026-06-07",
    )

    assert [(row["spec_id"], row["status"]) for row in report["rows"]] == [("s-blocked", "blocked"), ("s-stale", "warning"), ("s-ok", "ok")]
    assert report["rows"][0]["missing_citation_count"] == 1
    assert report["rows"][1]["stale_citation_count"] == 1


def test_spec_evidence_citation_quality_empty() -> None:
    assert generate_spec_evidence_citation_quality_report([])["rows"] == []
