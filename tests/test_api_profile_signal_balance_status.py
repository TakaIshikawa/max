from __future__ import annotations

import json

from max.api.profile_signal_balance_status import profile_signal_balance_status_to_json


def test_profile_signal_balance_status_reports_missing_and_dominant_roles() -> None:
    report = json.loads(
        profile_signal_balance_status_to_json(
            {
                "signals": [
                    {"profile_id": "balanced", "role": "problem"},
                    {"profile_id": "balanced", "role": "solution"},
                    {"profile_id": "balanced", "role": "market"},
                    {"profile_id": "thin", "role": "problem"},
                    {"profile_id": "thin", "role": "other"},
                ]
            }
        )
    )

    assert report["rows"][0]["profile_id"] == "thin"
    assert report["rows"][0]["missing_roles"] == ["market", "solution"]
    assert report["rows"][0]["role_counts"]["unknown"] == 1
    assert report["rows"][1]["dominant_role_ratio"] == 0.3333
    assert report["summary"]["unbalanced_count"] == 1
