from __future__ import annotations

import json

from max.api import publisher_destination_consent_gate_status_to_json


def test_consent_gate_blocks_required_missing_consent_only() -> None:
    report = json.loads(publisher_destination_consent_gate_status_to_json({"destinations": [{"destination": "jira", "profile": "core", "requires_consent": True, "consent_recorded": False, "pending_specs": 3}, {"destination": "slack", "profile": "core", "requires_consent": False, "pending_specs": 5}]}))

    assert report["status"] == "blocked"
    assert report["destinations"][0]["blocked_specs"] == 3
    assert {row["destination"]: row["status"] for row in report["destinations"]}["slack"] == "ok"
