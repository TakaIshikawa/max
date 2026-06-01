from __future__ import annotations

import json

from max.exports.ideation_input_concentration_report import generate_ideation_input_concentration_report


def test_ideation_input_concentration_report_computes_dominant_ratios() -> None:
    report = generate_ideation_input_concentration_report(
        [
            {
                "unit_id": "unit-1",
                "evidence_chain": [
                    {"source": "crm", "category": "retention", "profile": "enterprise"},
                    {"source": "crm", "category": "retention", "profile": "smb"},
                    {"source": "support", "category": "activation", "profile": "enterprise"},
                ],
            }
        ]
    )

    row = report["units"][0]
    assert row["dominant_source"] == "crm"
    assert row["dominant_source_ratio"] == 0.6667
    assert row["dominant_category"] == "retention"
    assert row["dominant_profile"] == "enterprise"
    json.dumps(report)


def test_ideation_input_concentration_report_flags_threshold_exceedance() -> None:
    report = generate_ideation_input_concentration_report(
        [
            {"unit_id": "unit-1", "evidence": [{"source": "crm"}, {"source": "crm"}, {"source": "docs"}]},
            {"unit_id": "unit-2", "evidence": [{"source": "sales"}, {"source": "support"}]},
        ],
        concentration_threshold=0.6,
    )

    assert report["summary"]["flagged_unit_count"] == 1
    assert [row["unit_id"] for row in report["flagged_units"]] == ["unit-1"]
    assert report["flagged_units"][0]["dominant_inputs"] == [{"type": "source", "value": "crm", "ratio": 0.6667}]


def test_ideation_input_concentration_report_sorts_by_ratio_descending_then_unit_id() -> None:
    report = generate_ideation_input_concentration_report(
        [
            {"unit_id": "b", "signals": [{"source": "crm"}, {"source": "docs"}]},
            {"unit_id": "c", "signals": [{"source": "crm"}, {"source": "crm"}]},
            {"unit_id": "a", "signals": [{"source": "sales"}, {"source": "support"}]},
        ],
        concentration_threshold=0.5,
    )

    assert [row["unit_id"] for row in report["units"]] == ["c", "a", "b"]
    assert [row["concentration_ratio"] for row in report["units"]] == [1.0, 0.5, 0.5]
