from __future__ import annotations

from max.exports import generate_signal_annotation_coverage_report as exported
from max.exports.signal_annotation_coverage_report import generate_signal_annotation_coverage_report


def test_signal_annotation_coverage_report_groups_profiles_sources_and_roles() -> None:
    report = generate_signal_annotation_coverage_report(
        [
            {"profile": "growth", "source": "crm", "role": "owner"},
            {"profile": "growth", "source": "crm"},
            {"profile": "growth", "source": "docs", "annotations": [{"role": "owner"}, {"role": "reviewer"}]},
        ],
        minimum_coverage=0.75,
        required_roles=["owner", "reviewer"],
    )

    assert exported is generate_signal_annotation_coverage_report
    assert report["summary"]["total_signals"] == 3
    assert report["rows"] == [
        {"profile": "growth", "source": "crm", "total_signals": 2, "annotated_signals": 1, "unannotated_signals": 1, "coverage_rate": 0.5, "missing_roles": ["reviewer"], "status": "incomplete"},
        {"profile": "growth", "source": "docs", "total_signals": 1, "annotated_signals": 1, "unannotated_signals": 0, "coverage_rate": 1.0, "missing_roles": [], "status": "complete"},
    ]


def test_signal_annotation_coverage_report_empty_input() -> None:
    assert generate_signal_annotation_coverage_report([])["rows"] == []
