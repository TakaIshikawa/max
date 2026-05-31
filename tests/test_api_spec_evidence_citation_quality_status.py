from __future__ import annotations

import json

from max.api import spec_evidence_citation_quality_status_to_json


def test_spec_evidence_citation_quality_status_scores_and_classifies_specs() -> None:
    data = json.loads(spec_evidence_citation_quality_status_to_json({"specs": [{"id": "ok", "citation_count": 4}, {"id": "bad", "citation_count": 2, "broken_citation_count": 1, "unsupported_claim_count": 1}]}))

    assert [row["spec_id"] for row in data["rows"]] == ["bad", "ok"]
    assert data["rows"][0]["status"] == "fail"
    assert data["rows"][0]["recommended_action"] == "repair_citations"


def test_spec_evidence_citation_quality_status_defaults_missing_ids() -> None:
    data = json.loads(spec_evidence_citation_quality_status_to_json({"items": [{"citation_count": 1, "stale_citation_count": 1}]}))

    assert data["rows"][0]["spec_id"] == "spec-1"
    assert data["summary"]["stale_citation_count"] == 1
