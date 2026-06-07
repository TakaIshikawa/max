from __future__ import annotations

from max.exports import generate_source_adapter_circuit_breaker_churn_report as exported
from max.exports.source_adapter_circuit_breaker_churn_report import generate_source_adapter_circuit_breaker_churn_report


def test_source_adapter_circuit_breaker_churn_report_groups_and_flags_churn() -> None:
    report = generate_source_adapter_circuit_breaker_churn_report(
        [
            {"adapter": "github", "source": "issues", "state": "closed", "timestamp": "2026-06-01T00:10:00Z"},
            {"adapter": "github", "source": "issues", "state": "open", "timestamp": "2026-06-01T00:00:00Z"},
            {"adapter": "github", "source": "issues", "state": "open", "timestamp": "2026-06-01T00:20:00Z"},
            {"adapter": "github", "source": "issues", "state": "closed", "timestamp": "2026-06-01T00:30:00Z"},
            {"adapter": "rss", "source": "blog", "state": "open", "timestamp": "2026-06-01T00:00:00Z"},
        ],
        churn_threshold=4,
    )

    assert exported is generate_source_adapter_circuit_breaker_churn_report
    assert report["summary"] == {
        "adapter_source_count": 2,
        "opened_count": 3,
        "closed_count": 2,
        "reopen_count": 1,
        "churn_count": 1,
        "churn_threshold": 4,
    }
    assert report["rows"][0] == {
        "adapter": "github",
        "source": "issues",
        "opened_count": 2,
        "closed_count": 2,
        "reopen_count": 1,
        "churn_score": 5,
        "status": "churn",
    }
    assert report["rows"][1]["status"] == "stable"


def test_source_adapter_circuit_breaker_churn_report_empty_input_returns_valid_summary() -> None:
    report = generate_source_adapter_circuit_breaker_churn_report([])

    assert report["schema_version"] == "max.source_adapter_circuit_breaker_churn_report.v1"
    assert report["summary"]["adapter_source_count"] == 0
    assert report["rows"] == []
