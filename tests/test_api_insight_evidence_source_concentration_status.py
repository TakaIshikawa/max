from __future__ import annotations

import json

from max.api import insight_evidence_source_concentration_status_to_json


def test_insight_evidence_source_concentration_status_classifies_and_sorts() -> None:
    report = json.loads(insight_evidence_source_concentration_status_to_json({"insights": [{"insight_id": "ok", "source_counts": {"a": 2, "b": 2}}, {"insight_id": "warn", "source_counts": {"a": 7, "b": 3}}, {"id": "crit", "evidence_sources": [{"source": "a", "count": 9}, {"source": "b", "count": 1}], "profile": "ops"}]}, warning_share=0.7, critical_share=0.9))

    assert report["schema_version"] == "max.api.insight_evidence_source_concentration_status.v1"
    assert [row["insight_id"] for row in report["insight_rows"]] == ["crit", "warn", "ok"]
    assert [row["status"] for row in report["insight_rows"]] == ["critical", "warning", "ok"]
    assert report["summary"]["concentrated_insights"] == 2
    assert report["summary"]["most_concentrated_insight_id"] == "crit"


def test_insight_evidence_source_concentration_status_handles_empty_and_malformed_counts() -> None:
    report = json.loads(insight_evidence_source_concentration_status_to_json({"rows": [{"id": "bad", "source_counts": {"a": "nope", "b": -4}}, {"id": "missing"}]}))

    assert report["summary"]["total_insights"] == 2
    assert report["insight_rows"][0]["top_source_share"] == 0.0
    assert {row["status"] for row in report["insight_rows"]} == {"ok"}
