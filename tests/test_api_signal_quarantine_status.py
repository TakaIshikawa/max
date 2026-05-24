from __future__ import annotations

import json

from max.api.signal_quarantine_status import signal_quarantine_status_to_json


def test_signal_quarantine_status_accepts_quarantine_and_derives_states() -> None:
    parsed = json.loads(
        signal_quarantine_status_to_json(
            {
                "quarantine": [
                    {"signal_id": "a", "source": "crm", "reason": "pii", "severity": "high", "age_hours": 1},
                    {"signal_id": "b", "source": "crm", "reason": "stale", "severity": "low", "age_hours": 200, "release_eligible": True},
                    {"signal_id": "c", "source": "web", "reason": "noise", "severity": "low", "age_hours": 1, "release_eligible": "yes"},
                    {"signal_id": "d", "source": "web", "reason": "noise", "age_hours": "bad"},
                ]
            }
        )
    )

    assert [row["status"] for row in parsed["signals"]] == ["expired", "escalated", "pending_review", "releasable"]
    assert parsed["summary"]["expired_count"] == 1
    assert parsed["summary"]["releasable_count"] == 1
    assert parsed["reason_totals"][1]["reason"] == "pii"
    assert parsed["source_totals"][0]["escalated_count"] == 2


def test_signal_quarantine_status_accepts_signals_alias_and_metadata() -> None:
    parsed = json.loads(signal_quarantine_status_to_json({"signals": [{"id": "s", "source": "x", "age": 72}]}, as_of="now"))

    assert parsed["signals"][0]["status"] == "escalated"
    assert parsed["metadata"]["as_of"] == "now"
