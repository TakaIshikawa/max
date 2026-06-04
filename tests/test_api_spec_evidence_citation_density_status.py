from __future__ import annotations

import json

from max.api import spec_evidence_citation_density_status_to_json


def test_spec_evidence_citation_density_status_classifies_and_sorts() -> None:
    report = json.loads(spec_evidence_citation_density_status_to_json({"specs": [{"spec_id": "ok", "block_count": 4, "citation_count": 4}, {"spec_id": "warn", "blocks": ["a", "b", "c", "d"], "citations": ["c1"]}, {"id": "crit", "block_count": 5, "citation_count": 0}]}, warning_citations_per_block=0.5, critical_citations_per_block=0.25))

    assert report["kind"] == "max.api.spec_evidence_citation_density_status"
    assert [row["spec_id"] for row in report["spec_rows"]] == ["crit", "warn", "ok"]
    assert [row["status"] for row in report["spec_rows"]] == ["critical", "warning", "ok"]
    assert report["summary"]["lowest_density_spec_id"] == "crit"
