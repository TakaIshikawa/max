from __future__ import annotations

import json

from max.api import spec_evidence_freshness_status_to_json


AS_OF = "2026-06-01T00:00:00Z"


def test_spec_evidence_freshness_status_fresh_specs() -> None:
    report = json.loads(spec_evidence_freshness_status_to_json({"max_age_hours": 48, "specs": [{"id": "s1", "evidence": [{"id": "e1", "timestamp": "2026-05-31T12:00:00Z"}]}]}, as_of=AS_OF))
    assert report["summary"]["status"] == "healthy"
    assert report["specs"][0]["refresh_required"] is False


def test_spec_evidence_freshness_status_partially_stale() -> None:
    report = json.loads(spec_evidence_freshness_status_to_json({"max_age_hours": 24, "specs": [{"id": "s1", "evidence": [{"id": "fresh", "timestamp": "2026-05-31T12:00:00Z"}, {"id": "old", "timestamp": "2026-05-29T00:00:00Z"}]}]}, as_of=AS_OF))
    assert report["summary"]["status"] == "warning"
    assert report["specs"][0]["stale_evidence_count"] == 1


def test_spec_evidence_freshness_status_entirely_stale_specs() -> None:
    report = json.loads(spec_evidence_freshness_status_to_json({"max_age_hours": 24, "specs": [{"id": "s1", "evidence": [{"timestamp": "2026-05-01T00:00:00Z"}]}, {"id": "s2", "evidence": [{"timestamp": "2026-05-02T00:00:00Z"}]}]}, as_of=AS_OF))
    assert report["summary"]["status"] == "critical"
    assert report["summary"]["refresh_required_count"] == 2


def test_spec_evidence_freshness_status_missing_evidence_timestamp() -> None:
    report = json.loads(spec_evidence_freshness_status_to_json({"specs": [{"id": "s1", "evidence": [{"id": "e1"}]}]}, as_of=AS_OF))
    assert report["specs"][0]["evidence"][0]["status"] == "missing"
    assert report["specs"][0]["refresh_required"] is True
