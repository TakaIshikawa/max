from __future__ import annotations

import json

from max.api import evidence_reference_url_health_status_to_json


def test_evidence_reference_url_health_classification_and_rollups() -> None:
    parsed = json.loads(evidence_reference_url_health_status_to_json({"references": [
        {"reference_id": "ok", "source": "docs", "status_code": 200, "checked_at": "2026-06-01T00:00:00Z"},
        {"reference_id": "redir", "source": "docs", "status_code": 301, "redirect_target": "https://new"},
        {"reference_id": "dead", "source": "blog", "status_code": 404},
        {"reference_id": "stale", "source": "docs", "status_code": 200, "checked_at": "2026-05-01T00:00:00Z"},
        {"reference_id": "unknown", "source": "blog"},
    ]}, as_of="2026-06-01T00:00:00Z"))
    assert parsed["schema_version"] == "max.api.evidence_reference_url_health_status.v1"
    assert parsed["summary"]["status"] == "critical"
    assert parsed["status_code_families"]["2xx"] == 2
    assert parsed["status_code_families"]["3xx"] == 1
    assert parsed["status_code_families"]["4xx"] == 1
    assert [row["reference_id"] for row in parsed["affected_references"][:2]] == ["dead", "redir"]
