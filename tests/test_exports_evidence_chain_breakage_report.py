from __future__ import annotations

import json

from max.exports.evidence_chain_breakage_report import (
    build_evidence_chain_breakage_report,
    render_evidence_chain_breakage_report_json,
)


def test_evidence_chain_breakage_report_accepts_intact_chains() -> None:
    report = build_evidence_chain_breakage_report(
        {
            "signals": [{"id": "s1"}],
            "insights": [{"id": "i1", "signal_ids": ["s1"]}],
            "units": [{"id": "u1", "insight_ids": ["i1"]}],
            "specs": [{"id": "sp1", "unit_ids": ["u1"]}],
        }
    )

    assert report["summary"]["checked_link_count"] == 3
    assert report["summary"]["broken_link_count"] == 0
    assert report["summary"]["orphaned_record_count"] == 0
    assert report["broken_links"] == []


def test_evidence_chain_breakage_report_detects_broken_signal_references() -> None:
    report = build_evidence_chain_breakage_report({"insights": [{"id": "i1", "signal_ids": ["missing-signal"]}]})

    assert report["broken_links"] == [
        {
            "record_type": "insight",
            "record_id": "i1",
            "missing_reference_type": "signal",
            "missing_reference_id": "missing-signal",
        }
    ]
    assert report["summary"]["broken_link_count"] == 1


def test_evidence_chain_breakage_report_detects_orphaned_insights() -> None:
    report = build_evidence_chain_breakage_report(
        {
            "signals": [{"id": "s1"}],
            "insights": [{"id": "used", "signal_ids": ["s1"]}, {"id": "orphan", "signal_ids": ["s1"]}],
            "units": [{"id": "u1", "insight_ids": ["used"]}],
            "specs": [{"id": "sp1", "unit_ids": ["u1"]}],
        }
    )

    assert {"record_type": "insight", "record_id": "orphan"} in report["orphaned_records"]


def test_evidence_chain_breakage_report_detects_orphaned_units() -> None:
    report = build_evidence_chain_breakage_report(
        {
            "signals": [{"id": "s1"}],
            "insights": [{"id": "i1", "signal_ids": ["s1"]}],
            "units": [{"id": "u1", "insight_ids": ["i1"]}, {"id": "u2", "insight_ids": ["i1"]}],
            "specs": [{"id": "sp1", "unit_ids": ["u1"]}],
        }
    )

    assert {"record_type": "unit", "record_id": "u2"} in report["orphaned_records"]


def test_evidence_chain_breakage_report_sorts_deterministically() -> None:
    report = build_evidence_chain_breakage_report(
        {
            "units": [
                {"id": "b", "insight_ids": ["z"]},
                {"id": "a", "insight_ids": ["y"]},
            ],
            "specs": [{"id": "sp", "unit_ids": ["missing"]}],
        }
    )

    assert [(row["record_type"], row["record_id"], row["missing_reference_id"]) for row in report["broken_links"]] == [
        ("spec", "sp", "missing"),
        ("unit", "a", "y"),
        ("unit", "b", "z"),
    ]


def test_evidence_chain_breakage_report_empty_input_is_stable() -> None:
    report = build_evidence_chain_breakage_report({})

    assert report["summary"] == {
        "signal_count": 0,
        "insight_count": 0,
        "unit_count": 0,
        "spec_count": 0,
        "checked_link_count": 0,
        "broken_link_count": 0,
        "orphaned_record_count": 0,
        "missing_evidence_count": 0,
    }
    assert report["broken_links"] == []
    assert report["orphaned_records"] == []


def test_evidence_chain_breakage_report_preserves_metadata_and_counts_missing_evidence() -> None:
    report = build_evidence_chain_breakage_report(
        {"units": [{"id": "u1"}], "metadata": {"source": "fixture"}},
        metadata={"run": "nightly"},
    )

    assert report["metadata"] == {"run": "nightly"}
    assert report["missing_evidence_records"] == [
        {"record_type": "unit", "record_id": "u1", "missing_evidence": "insights_or_signals"}
    ]
    assert (
        json.loads(render_evidence_chain_breakage_report_json(report))["kind"]
        == "max.evidence_chain_breakage_report"
    )
