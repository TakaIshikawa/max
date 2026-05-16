from __future__ import annotations

import json

from max.exports.trial_to_paid_conversion_diagnostic import (
    export_trial_to_paid_conversion_diagnostic,
    render_trial_to_paid_conversion_diagnostic_json,
)


def test_trial_to_paid_conversion_diagnostic_groups_and_calculates_rate() -> None:
    rows = export_trial_to_paid_conversion_diagnostic(
        [
            {"cohort": "2026-01", "converted": True, "activation_signals": ["invite_sent"], "sales_touchpoints": 1},
            {"cohort": "2026-01", "converted": False, "blockers": ["setup blocked"]},
            {"cohort": "2026-02", "paid": "yes", "activation": ["workspace_created"]},
        ]
    )

    assert rows[0]["cohort"] == "2026-01"
    assert rows[0]["conversion_rate"] == 0.5
    assert rows[0]["blocker_classification"] == "activation"
    assert rows[0]["recommended_experiment"] == "Test guided activation checklist for stalled trials."


def test_trial_to_paid_conversion_diagnostic_empty_and_missing_data_are_stable() -> None:
    assert export_trial_to_paid_conversion_diagnostic([]) == []

    rows = export_trial_to_paid_conversion_diagnostic([{}])
    assert rows[0]["cohort"] == "Unknown"
    assert rows[0]["activation_signals"] == ["unknown"]
    assert rows[0]["blockers"] == ["none"]
    assert json.loads(render_trial_to_paid_conversion_diagnostic_json(rows))
