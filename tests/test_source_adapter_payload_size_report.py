from __future__ import annotations

from max.exports import generate_source_adapter_payload_size_report as exported
from max.exports.source_adapter_payload_size_report import generate_source_adapter_payload_size_report


def test_source_adapter_payload_size_report_groups_payload_sizes() -> None:
    report = generate_source_adapter_payload_size_report(
        [
            {"adapter": "rss", "profile": "core", "payload_bytes": 100},
            {"adapter": "rss", "profile": "core", "payload": "abc"},
        ],
        warning_bytes=50,
        max_bytes=200,
    )

    assert exported is generate_source_adapter_payload_size_report
    assert report["rows"][0]["payload_count"] == 2
    assert report["rows"][0]["total_bytes"] == 103
    assert report["rows"][0]["avg_bytes"] == 51.5
    assert report["rows"][0]["status"] == "warning"


def test_source_adapter_payload_size_report_flags_oversized_and_sorts_by_status() -> None:
    report = generate_source_adapter_payload_size_report(
        [
            {"adapter": "small", "profile": "core", "payload_bytes": 10},
            {"adapter": "large", "profile": "core", "payload_bytes": 2000},
        ],
        warning_bytes=100,
        max_bytes=1000,
    )

    assert [row["adapter"] for row in report["rows"]] == ["large", "small"]
    assert report["summary"]["status"] == "oversized"


def test_source_adapter_payload_size_report_handles_empty_input() -> None:
    report = generate_source_adapter_payload_size_report([])

    assert report["summary"]["group_count"] == 0
    assert report["summary"]["status"] == "ok"
    assert report["rows"] == []
