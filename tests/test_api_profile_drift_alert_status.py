from __future__ import annotations

import json

from max.api.profile_drift_alert_status import profile_drift_alert_status_to_json


def test_profile_drift_alert_status_classifies_acknowledged_and_active_alerts() -> None:
    parsed = json.loads(
        profile_drift_alert_status_to_json(
            {
                "alerts": [
                    {"profile": "p", "field": "tone", "drift_score": 1.0, "threshold": 0.8, "owner": "ops"},
                    {"profile": "p", "field": "length", "drift_score": 0.7, "threshold": 0.8, "owner": "ops"},
                    {"profile": "q", "field": "tags", "drift_score": 0.1, "threshold": 0.8, "owner": "data"},
                    {"profile": "q", "field": "style", "drift_score": 2, "threshold": 1, "owner": "data", "acknowledged": "true"},
                ]
            }
        )
    )

    assert [row["status"] for row in parsed["alerts"]] == ["alerting", "watch", "normal", "acknowledged"]
    assert [row["field"] for row in parsed["active_alerts"]] == ["tone", "length"]
    assert parsed["summary"]["acknowledged_count"] == 1
    assert parsed["owner_totals"][1]["owner"] == "ops"
    assert parsed["owner_totals"][1]["active_count"] == 2


def test_profile_drift_alert_status_clamps_aliases_and_metadata() -> None:
    parsed = json.loads(profile_drift_alert_status_to_json({"profile_drift": [{"profile": "p", "field": "f", "score": "-1", "threshold": "bad"}]}, as_of="now"))

    assert parsed["alerts"][0]["drift_score"] == 0.0
    assert parsed["alerts"][0]["threshold"] == 0.0
    assert parsed["alerts"][0]["status"] == "normal"
    assert parsed["metadata"]["as_of"] == "now"
