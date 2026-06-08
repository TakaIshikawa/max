from __future__ import annotations

from max.exports import generate_adapter_health_rollup_report as exported
from max.exports.adapter_health_rollup_report import generate_adapter_health_rollup_report


def test_adapter_health_rollup_report_groups_counts_and_thresholds() -> None:
    report = generate_adapter_health_rollup_report(
        [
            {"adapter": "github", "source": "issues", "status": "success", "seen_at": "2026-06-01T00:00:00Z"},
            {"adapter": "github", "source": "issues", "status": "timeout", "seen_at": "2026-06-02T00:00:00Z"},
            {"adapter": "slack", "source": "messages", "success_count": 9, "failure_count": 1, "latest_seen_at": "2026-06-03T00:00:00Z"},
            {"adapter": "zendesk", "source": "tickets", "success_count": 99, "failure_count": 1, "latest_seen_at": "2026-06-04T00:00:00Z"},
        ],
        warning_success_rate=0.95,
        critical_success_rate=0.75,
    )

    assert exported is generate_adapter_health_rollup_report
    assert report["summary"]["critical_count"] == 1
    assert report["summary"]["warning_count"] == 1
    assert report["summary"]["healthy_count"] == 1
    assert [row["adapter"] for row in report["rows"]] == ["github", "slack", "zendesk"]
    assert report["rows"][0]["timeout_count"] == 1
    assert report["rows"][0]["success_rate"] == 0.5
    assert report["rows"][0]["latest_seen_at"] == "2026-06-02T00:00:00Z"
    assert report["rows"][1]["status"] == "warning"
    assert report["rows"][2]["status"] == "healthy"


def test_adapter_health_rollup_report_empty_input() -> None:
    assert generate_adapter_health_rollup_report([])["rows"] == []
