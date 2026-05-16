from __future__ import annotations

import json

from max.exports.onboarding_activation_cohorts import (
    export_onboarding_activation_cohorts,
    render_onboarding_activation_cohorts_json,
)


def test_onboarding_activation_cohorts_groups_math_and_stalled_milestones() -> None:
    rows = export_onboarding_activation_cohorts(
        [
            {"cohort": "2026-01", "activated": True, "time_to_value_days": 10},
            {"cohort": "2026-01", "stalled_milestones": ["SSO", "SSO", "import"]},
            {"cohort": "2026-02", "milestones": {"invite": True, "first_value": True}, "time_to_value_days": 20},
        ]
    )

    assert rows[0]["cohort"] == "2026-01"
    assert rows[0]["activation_rate"] == 0.5
    assert rows[0]["average_time_to_value_days"] == 10.0
    assert rows[0]["stalled_milestones"][0] == {"milestone": "SSO", "count": 2}
    assert rows[0]["recommended_intervention"] == "Assign onboarding owner to unblock SSO."


def test_onboarding_activation_cohorts_empty_partial_and_json() -> None:
    assert export_onboarding_activation_cohorts([]) == []

    rows = export_onboarding_activation_cohorts([{}])
    assert rows[0]["cohort"] == "Unknown"
    assert rows[0]["activation_rate"] == 0.0
    assert rows[0]["average_time_to_value_days"] is None
    assert json.loads(render_onboarding_activation_cohorts_json(rows))
