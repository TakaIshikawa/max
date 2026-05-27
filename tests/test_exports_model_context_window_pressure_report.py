from __future__ import annotations

from max.exports.model_context_window_pressure_report import build_model_context_window_pressure_report


def test_model_context_window_pressure_report_filters_and_flags_rows() -> None:
    report = build_model_context_window_pressure_report(
        [
            {"run_id": "ok", "model": "m", "prompt_tokens": 10, "completion_tokens": 10, "context_window": 100},
            {"run_id": "near", "model": "m", "total_tokens": 85, "context_window": 100},
            {"run_id": "over", "model": "m", "total_tokens": 120, "context_window": 100},
        ]
    )

    assert [row["run_id"] for row in report["pressure_rows"]] == ["over", "near"]
    assert report["pressure_rows"][0]["overflow"] is True
    assert report["pressure_rows"][1]["near_limit"] is True
    assert report["summary"]["overflow_count"] == 1
    assert build_model_context_window_pressure_report([])["pressure_rows"] == []
