from __future__ import annotations

import json

from max.api import signal_retention_policy_status_to_json


def test_signal_retention_empty_compliant_and_violating_rows() -> None:
    assert json.loads(signal_retention_policy_status_to_json({}))["summary"]["status"] == "healthy"
    parsed = json.loads(signal_retention_policy_status_to_json({"policies": [
        {"source": "a", "profile": "p", "retained_count": 10, "expired_count": 0, "max_age_days": 10, "policy_age_days": 30},
        {"source": "b", "profile": "p", "retained_count": 10, "expired_count": 1, "max_age_days": 40, "policy_age_days": 30},
        {"source": "c", "profile": "p", "retained_count": 10, "expired_count": 20, "max_age_days": 100, "policy_age_days": 30},
    ]}))
    assert parsed["summary"]["status"] == "critical"
    assert [row["source"] for row in parsed["affected_policies"]] == ["c", "b"]
