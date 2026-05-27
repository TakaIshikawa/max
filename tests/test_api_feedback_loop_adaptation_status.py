from __future__ import annotations

import json

from max.api.feedback_loop_adaptation_status import feedback_loop_adaptation_status_to_json


def test_feedback_loop_adaptation_status_counts_backed_up_rows() -> None:
    report = json.loads(
        feedback_loop_adaptation_status_to_json(
            {
                "adaptations": [
                    {"profile": "p", "outcome_label": "won", "feedback_count": 10, "applied_adjustments": 6, "pending_adjustments": 5, "last_applied_at": "2026-05-26T00:00:00Z", "max_pending_adjustments": 3},
                    {"profile": "p", "outcome_label": "lost", "feedback_count": 0, "applied_adjustments": 0, "pending_adjustments": 0, "max_pending_adjustments": 3},
                ]
            }
        )
    )

    assert report["rows"][0]["backed_up"] is True
    assert report["rows"][0]["applied_ratio"] == 0.6
    assert report["summary"]["total_feedback"] == 10
    assert report["summary"]["total_applied_adjustments"] == 6
    assert report["summary"]["total_pending_adjustments"] == 5
    assert report["summary"]["backed_up_count"] == 1
