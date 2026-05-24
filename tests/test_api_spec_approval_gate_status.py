from __future__ import annotations

import json

from max.api.spec_approval_gate_status import spec_approval_gate_status_to_json


def test_spec_approval_gate_status_blocks_and_owner_queues() -> None:
    parsed = json.loads(
        spec_approval_gate_status_to_json(
            {
                "gates": [
                    {"gate": "legal", "owner": "ana", "state": "rejected", "reason": "DPA missing", "action": "Attach DPA"},
                    {"gate": "security", "owner": "ben", "state": "approved"},
                ]
            }
        )
    )

    assert parsed["summary"]["overall_status"] == "blocked"
    assert parsed["blocking_gates"][0]["gate"] == "legal"
    assert parsed["next_actions"][0]["action"] == "Attach DPA"
    assert parsed["owner_queues"][0]["owner"] == "ana"


def test_spec_approval_gate_status_detects_stale_approvals() -> None:
    parsed = json.loads(
        spec_approval_gate_status_to_json(
            {"approvals": [{"name": "finance", "approver": "cfo", "status": "pass", "approved_at": "2026-05-01T00:00:00Z"}], "stale_after_days": 7},
            as_of="2026-05-21T00:00:00Z",
        )
    )

    assert parsed["summary"]["overall_status"] == "warning"
    assert parsed["stale_approvals"][0]["gate"] == "finance"
    assert parsed["next_actions"][0]["action"] == "Refresh stale approval"


def test_spec_approval_gate_status_all_clear() -> None:
    parsed = json.loads(spec_approval_gate_status_to_json({"gates": [{"gate": "legal", "approved": True}]}))

    assert parsed["summary"]["overall_status"] == "ready"
    assert parsed["blocking_gates"] == []
