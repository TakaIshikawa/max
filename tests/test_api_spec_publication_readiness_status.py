from __future__ import annotations

import json

from max.api import spec_publication_readiness_status_to_json


def test_spec_publication_readiness_status_classifies_and_sorts_blocked_specs() -> None:
    rendered = json.loads(spec_publication_readiness_status_to_json({"specs": [{"spec_id": "ready", "has_evidence": True}, {"spec_id": "blocked", "has_evidence": False, "stale_evaluation": True, "created_at": "2026-01-01"}, {"spec_id": "dest", "has_evidence": True, "destination_eligible": False, "created_at": "2026-02-01"}]}))

    assert rendered["schema_version"] == "max.api.spec_publication_readiness_status.v1"
    assert rendered["kind"] == "max.api.spec_publication_readiness_status"
    assert rendered["ready_count"] == 1
    assert rendered["blocked_count"] == 2
    assert rendered["blockers_by_reason"]["missing_evidence"] == 1
    assert rendered["blocked_specs"][0]["spec_id"] == "blocked"
