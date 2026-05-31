from __future__ import annotations

import json

from max.exports.signal_source_reliability_report import generate_signal_source_reliability_report


def test_signal_source_reliability_groups_and_counts_tail_failures() -> None:
    report = generate_signal_source_reliability_report(
        [
            {"source": "api", "profile": "p", "run_id": "1", "run_at": "2026-05-31T00:00:00+00:00", "status": "success"},
            {"source": "api", "profile": "p", "run_id": "2", "run_at": "2026-05-31T01:00:00+00:00", "status": "failed", "error_type": "timeout"},
            {"source": "api", "profile": "p", "run_id": "3", "run_at": "2026-05-31T02:00:00+00:00", "status": "failed"},
        ],
        warning_failure_rate=0.2,
        critical_failure_rate=0.6,
    )

    row = report["rows"][0]
    assert row["attempts"] == 3
    assert row["successes"] == 1
    assert row["timeouts"] == 1
    assert row["success_rate"] == 0.3333
    assert row["consecutive_failures"] == 2
    assert row["severity"] == "critical"
    json.dumps(report)
