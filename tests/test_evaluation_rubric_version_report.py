from __future__ import annotations

from max.exports import generate_evaluation_rubric_version_report as exported
from max.exports.evaluation_rubric_version_report import generate_evaluation_rubric_version_report


def test_evaluation_rubric_version_report_supports_current_version() -> None:
    report = generate_evaluation_rubric_version_report([], current_version="v3")

    assert exported is generate_evaluation_rubric_version_report
    assert report["summary"]["status"] == "current"
    assert report["summary"]["current_version"] == "v3"
    assert report["rows"] == []


def test_evaluation_rubric_version_report_counts_stale_percentages() -> None:
    report = generate_evaluation_rubric_version_report(
        [
            {"profile": "core", "rubric_version": "v3"},
            {"profile": "core", "version": "v2"},
        ],
        current_version="v3",
    )

    row = report["rows"][0]
    assert row["version_counts"] == {"v2": 1, "v3": 1}
    assert row["stale_count"] == 1
    assert row["stale_percent"] == 50
    assert row["status"] == "stale"


def test_evaluation_rubric_version_report_classifies_mixed() -> None:
    report = generate_evaluation_rubric_version_report(
        [{"profile": "core", "version": "v3"}, {"profile": "core", "version": "v3"}, {"profile": "core", "version": "v2"}],
        current_version="v3",
        stale_threshold=0.5,
    )

    assert report["rows"][0]["status"] == "mixed"
