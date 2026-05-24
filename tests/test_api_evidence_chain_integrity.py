from __future__ import annotations

import json

from max.api.evidence_chain_integrity import evidence_chain_integrity_to_json


def test_evidence_chain_integrity_derives_complete_degraded_broken() -> None:
    parsed = json.loads(
        evidence_chain_integrity_to_json(
            {
                "chains": [
                    {"id": "ok", "entity_type": "idea", "confidence": 0.9},
                    {"id": "weak", "entity_type": "unit", "confidence": 0.5},
                    {"id": "bad", "entity_type": "insight", "missing_signal_ids": ["s1"], "orphaned_reference_count": "2"},
                ]
            }
        )
    )

    assert parsed["schema_version"] == "max.api.evidence_chain_integrity.v1"
    assert [row["entity_id"] for row in parsed["chains"]] == ["bad", "weak", "ok"]
    assert parsed["summary"]["complete_count"] == 1
    assert parsed["summary"]["degraded_count"] == 1
    assert parsed["summary"]["broken_count"] == 1
    assert parsed["summary"]["missing_reference_count"] == 3
    assert parsed["broken_chains"][0]["entity_id"] == "bad"


def test_evidence_chain_integrity_aliases_and_metadata() -> None:
    parsed = json.loads(evidence_chain_integrity_to_json({"evidence_chains": [{"entity_id": "e", "type": "signal", "missing_insights": "i1", "confidence": "bad"}]}, as_of="2026-05-21T00:00:00Z"))

    assert parsed["chains"][0]["missing_insight_ids"] == ["i1"]
    assert parsed["chains"][0]["status"] == "broken"
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"
