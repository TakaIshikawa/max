from __future__ import annotations

import json

from max.exports.customer_value_realization import (
    export_customer_value_realization,
    render_customer_value_realization_json,
)


def test_customer_value_realization_classifies_status_and_preserves_evidence() -> None:
    rows = export_customer_value_realization(
        [
            {"account_name": "Beta", "target_outcome": "Reduce handle time", "achieved_outcomes": ["12% reduction"], "usage_signals": ["active"], "evidence_ids": ["case-1"]},
            {"account_name": "Acme", "success_criteria": "Automate intake", "usage_signals": ["low usage"]},
        ]
    )

    assert [row["account_name"] for row in rows] == ["Acme", "Beta"]
    assert rows[0]["realization_status"] == "at_risk"
    assert rows[0]["gap_summary"] == "No achieved outcome recorded for Automate intake."
    assert rows[1]["realization_status"] == "realized"
    assert rows[1]["current_evidence"] == ["case-1"]


def test_customer_value_realization_defaults_missing_targets_and_json() -> None:
    rows = export_customer_value_realization([{}])

    assert rows[0]["account_name"] == "Unknown"
    assert rows[0]["target_outcome"] == "Unknown"
    assert rows[0]["realization_status"] == "unknown"
    assert rows[0]["recommended_next_step"] == "Document target outcome and baseline value evidence."
    assert json.loads(render_customer_value_realization_json(rows))
