from __future__ import annotations

from max.exports.prompt_template_drift_report import build_prompt_template_drift_report


def test_prompt_template_drift_report_detects_section_drift() -> None:
    report = build_prompt_template_drift_report(
        [
            {
                "template_id": "t",
                "baseline_version": "1",
                "current_version": "2",
                "baseline_sections": {"Safety": {"body": "Never leak secrets", "required": True}, "Tone": "formal"},
                "current_sections": {"Safety": {"body": "Avoid secrets", "required": True}, "Examples": "few-shot"},
            }
        ]
    )

    assert report["summary"]["changed_count"] == 1
    assert report["summary"]["removed_count"] == 1
    assert report["summary"]["added_count"] == 1
    assert [row["drift_type"] for row in report["drift_rows"]] == ["changed", "removed", "added"]
    assert build_prompt_template_drift_report([{"template_id": "same", "baseline_sections": {"A": "x"}, "current_sections": {"A": "x"}}])["summary"]["drift_count"] == 0
