from __future__ import annotations

import json

from max.api import tact_spec_export_readiness_status_to_json


def test_tact_spec_export_readiness_status_separates_ready_and_blocked_candidates() -> None:
    data = json.loads(tact_spec_export_readiness_status_to_json({"candidates": [{"id": "ready", "status": "approved", "evaluation": True, "evidence": True, "acceptance_criteria": True}, {"id": "blocked", "status": "approved", "evaluation": True, "evidence": False, "acceptance_criteria": True}]}))

    assert data["summary"]["ready_count"] == 1
    assert data["summary"]["blocked_count"] == 1
    assert data["blocked_candidates"][0]["blockers"] == ["evidence"]


def test_tact_spec_export_readiness_status_ignores_unapproved_candidates() -> None:
    data = json.loads(tact_spec_export_readiness_status_to_json({"items": [{"id": "draft", "status": "draft"}, {"id": "ok", "status": "approved", "has_evaluation": True, "has_evidence": True, "has_acceptance_criteria": True}]}))

    assert [row["idea_id"] for row in data["rows"]] == ["ok"]
    assert data["summary"]["status"] == "ready"
