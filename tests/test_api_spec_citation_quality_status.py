from __future__ import annotations

import json

from max.api import spec_citation_quality_status_to_json


def test_spec_citation_quality_status_reports_issue_counts_and_critical() -> None:
    data = json.loads(spec_citation_quality_status_to_json({"warning_issue_threshold": 2, "critical_issue_threshold": 4, "specs": [{"spec_id": "s-1", "missing_citation_count": 1, "stale_citation_count": 1}, {"spec_id": "s-2", "unsupported_criteria_count": 2}]}))

    assert data["status"] == "critical"
    assert data["spec_count"] == 2
    assert data["missing_citation_count"] == 1
    assert data["stale_citation_count"] == 1
    assert data["unsupported_criteria_count"] == 2
    assert data["worst_spec_id"] == "s-2"


def test_spec_citation_quality_status_supports_warning_and_empty() -> None:
    warning = json.loads(spec_citation_quality_status_to_json({"warning_issue_threshold": 1, "critical_issue_threshold": 3, "items": [{"id": "s-1", "stale_count": 1}]}))
    empty = json.loads(spec_citation_quality_status_to_json({}))

    assert warning["status"] == "warning"
    assert warning["worst_spec_id"] == "s-1"
    assert empty["status"] == "ok"
    assert empty["worst_spec_id"] is None
