from __future__ import annotations

from max.exports import generate_spec_acceptance_criteria_completeness_report as exported
from max.exports.spec_acceptance_criteria_completeness_report import generate_spec_acceptance_criteria_completeness_report


def test_spec_acceptance_criteria_completeness_report_detects_missing_duplicates_and_vague() -> None:
    report = generate_spec_acceptance_criteria_completeness_report(
        [
            {"spec_id": "spec-a", "acceptance_criteria": []},
            {"spec_id": "spec-b", "acceptance_criteria": ["must save the record", "must save the record", "works"]},
            {"spec_id": "spec-c", "acceptance_criteria": ["Given a valid request then the response must include a persisted id"]},
        ],
        specificity_min_words=4,
    )

    assert exported is generate_spec_acceptance_criteria_completeness_report
    assert report["summary"]["incomplete_count"] == 2
    assert report["rows"][0]["spec_id"] == "spec-a"
    assert report["rows"][1]["duplicate_count"] == 1
    assert report["rows"][2]["status"] == "complete"

