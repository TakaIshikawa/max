from __future__ import annotations

import json

from max.api import insight_confidence_decay_status_to_json


def test_insight_confidence_decay_status_flags_refresh_candidates() -> None:
    data = json.loads(insight_confidence_decay_status_to_json({"minimum_confidence": 0.4, "warning_decay": 0.2, "critical_decay": 0.5, "insights": [{"insight_id": "i2", "profile": "Growth", "confidence": 0.3, "original_confidence": 0.9, "age_days": 20, "evidence_refresh_count": 0}, {"insight_id": "i1", "profile": "Core", "confidence": 0.7, "original_confidence": 0.95, "age_days": 5}]}))

    assert data["status"] == "critical"
    assert data["summary"]["total"] == 2
    assert data["summary"]["refresh_candidate_count"] == 2
    assert data["insights"][0]["insight_id"] == "i2"
    assert data["insights"][0]["confidence_delta"] == -0.6
    assert data["insights"][1]["status"] == "warning"
