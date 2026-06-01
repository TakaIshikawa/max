from __future__ import annotations

import json

from max.api import signal_payload_redaction_status_to_json


def test_signal_payload_redaction_status_reports_clean_warning_critical_and_empty() -> None:
    empty = json.loads(signal_payload_redaction_status_to_json({"signals": []}))
    assert empty["overall_status"] == "healthy"
    assert empty["redaction_coverage"] == 1.0
    report = json.loads(signal_payload_redaction_status_to_json({"current_policy_version": "p2", "signals": [{"signal_id": "clean", "redacted": True, "policy_version": "p2"}, {"signal_id": "drift", "redacted": True, "policy_version": "p1"}, {"signal_id": "bad", "unredacted_sensitive_fields": ["email"], "failed_redaction_count": 1}]}))
    assert report["overall_status"] == "critical"
    assert report["policy_drift_count"] == 1
    assert report["failed_redaction_count"] == 1
    assert [row["signal_id"] for row in report["quarantine_recommendations"]] == ["bad"]
