from __future__ import annotations

import json

from max.exports.roadmap_commitment_tracker import (
    export_roadmap_commitment_tracker,
    render_roadmap_commitment_tracker_json,
)


def test_roadmap_commitment_tracker_classifies_slippage_and_orders_exposure() -> None:
    rows = export_roadmap_commitment_tracker(
        [
            {"account": "Beta", "capability": "Audit logs", "target_date": "2026-03-01", "revenue_exposure": 50000},
            {"account": "Acme", "promised_capability": "SAML", "target_date": "2025-12-01", "arr": "200000"},
            {"segment": "SMB", "capability": "Mobile", "target_date": "2025-12-01", "arr": 10000},
        ],
        as_of="2026-01-01",
    )

    assert [row["account_or_segment"] for row in rows] == ["Acme", "SMB", "Beta"]
    assert rows[0]["status"] == "overdue"
    assert rows[0]["slippage_days"] == 31
    assert rows[2]["status"] == "on_track"


def test_roadmap_commitment_tracker_handles_missing_dates_and_json() -> None:
    rows = export_roadmap_commitment_tracker([{}])

    assert rows[0]["target_date"] == ""
    assert rows[0]["status"] == "unknown"
    assert rows[0]["communication_action"] == "Validate target date and owner before next roadmap review."
    assert json.loads(render_roadmap_commitment_tracker_json(rows))
