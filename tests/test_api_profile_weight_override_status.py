from __future__ import annotations

import json

from max.api.profile_weight_override_status import profile_weight_override_status_to_json


def test_profile_weight_override_status_computes_drift_and_expiry() -> None:
    report = json.loads(
        profile_weight_override_status_to_json(
            {
                "overrides": [
                    {"profile": "p", "dimension": "quality", "base_weight": 0.5, "override_weight": 0.75, "source": "ops", "expires_at": "2026-05-01T00:00:00Z", "approved_by": ""},
                    {"profile": "p", "dimension": "safety", "base_weight": 0, "override_weight": 0.2, "source": "ops", "expires_at": "2026-06-01T00:00:00Z", "approved_by": "lead"},
                ]
            },
            as_of="2026-05-27T00:00:00Z",
        )
    )

    assert report["rows"][0]["expired"] is True
    assert report["rows"][0]["unapproved"] is True
    assert report["rows"][0]["absolute_drift"] == 0.25
    assert report["rows"][0]["relative_drift"] == 0.5
    assert report["summary"]["active_override_count"] == 1
    assert report["summary"]["expired_override_count"] == 1
    assert report["summary"]["unapproved_override_count"] == 1
