from __future__ import annotations

import json

from max.api import publication_approval_delegation_status_to_json


def test_publication_approval_delegation_status_covers_healthy_warning_critical_and_empty() -> None:
    empty = json.loads(publication_approval_delegation_status_to_json({"publications": []}))
    assert empty["overall_status"] == "healthy"
    report = json.loads(publication_approval_delegation_status_to_json({"as_of": "2026-06-01T00:00:00Z", "publications": [{"publication_id": "ok", "destination": "web", "delegate": "a", "delegate_expires_at": "2026-06-10T00:00:00Z"}, {"publication_id": "warn", "destination": "mail"}, {"publication_id": "crit", "destination": "web", "delegate": "b", "delegate_expires_at": "2026-05-01T00:00:00Z", "blocked_publication_count": 2}]}))
    assert report["overall_status"] == "critical"
    assert report["missing_delegate_count"] == 1
    assert report["blocked_publication_count"] == 2
    assert report["escalation_required_destinations"] == ["mail", "web"]
