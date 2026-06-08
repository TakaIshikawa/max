from __future__ import annotations

from max.exports import generate_synthesis_throughput_report as exported
from max.exports.synthesis_throughput_report import generate_synthesis_throughput_report


def test_synthesis_throughput_report_aggregates_successful_batches() -> None:
    report = generate_synthesis_throughput_report(
        [
            {"profile": "core", "model": "gpt", "signal_count": 10, "insight_count": 3, "status": "ok"},
            {"profile": "core", "model": "gpt", "signal_count": 5, "insight_count": 2, "status": "ok"},
        ]
    )

    assert exported is generate_synthesis_throughput_report
    assert report["rows"][0]["batch_count"] == 2
    assert report["rows"][0]["avg_insights_per_batch"] == 2.5
    assert report["rows"][0]["conversion_rate"] == 0.3333
    assert report["rows"][0]["status"] == "ok"


def test_synthesis_throughput_report_flags_low_yield_and_failing_groups() -> None:
    report = generate_synthesis_throughput_report(
        [
            {"profile": "growth", "model": "small", "signal_count": 20, "insight_count": 0, "status": "ok"},
            {"profile": "core", "model": "bad", "signal_count": 7, "insight_count": 0, "status": "failed"},
        ]
    )

    assert [row["status"] for row in report["rows"]] == ["failing", "low_yield"]
    assert report["summary"]["status"] == "failing"
    assert report["summary"]["failed_batch_count"] == 1


def test_synthesis_throughput_report_handles_zero_signal_conversion() -> None:
    report = generate_synthesis_throughput_report([{"profile": "empty", "model": "gpt", "signal_count": 0, "insight_count": 1}])

    assert report["rows"][0]["conversion_rate"] == 0.0


def test_synthesis_throughput_report_handles_empty_input() -> None:
    report = generate_synthesis_throughput_report([])

    assert report["summary"]["group_count"] == 0
    assert report["summary"]["status"] == "ok"
    assert report["rows"] == []
