from __future__ import annotations

import json

from max.api.insight_evidence_coverage import insight_evidence_coverage_to_json


def test_insight_evidence_coverage_aggregates_buckets() -> None:
    parsed = json.loads(
        insight_evidence_coverage_to_json(
            {
                "insights": [
                    {
                        "id": "strong",
                        "evidence": [
                            {"source": "CRM", "category": "sales", "profile": "ent", "observed_at": "2026-05-20T00:00:00Z"},
                            {"source": "Calls", "category": "sales", "profile": "ent", "observed_at": "2026-05-10T00:00:00Z"},
                        ],
                    }
                ]
            },
            as_of="2026-05-21T00:00:00Z",
        )
    )

    assert parsed["summary"]["weak_evidence_count"] == 0
    assert parsed["coverage"]["sources"][0]["count"] == 1
    assert {row["bucket"] for row in parsed["coverage"]["recency_buckets"]} == {"aging", "fresh"}


def test_insight_evidence_coverage_aliases_and_stale_cutoff() -> None:
    parsed = json.loads(
        insight_evidence_coverage_to_json(
            {
                "items": [
                    {
                        "insight_id": "old",
                        "category": "ops",
                        "evidence_items": [{"source_name": "docs", "timestamp": "2026-04-01T00:00:00Z"}],
                    }
                ],
                "stale_cutoff_days": 10,
            },
            as_of="2026-05-21T00:00:00Z",
        )
    )

    assert parsed["weak_evidence_insights"][0]["insight_id"] == "old"
    assert parsed["single_source_warnings"][0]["sources"] == ["docs"]
    assert parsed["stale_evidence_warnings"][0]["stale_evidence"] is True
    assert {row["action"] for row in parsed["suggested_evidence_collection_actions"]} >= {"Collect evidence from an additional source", "Refresh stale evidence before publication"}


def test_insight_evidence_coverage_empty_input() -> None:
    parsed = json.loads(insight_evidence_coverage_to_json({}))

    assert parsed["summary"]["insight_count"] == 0
    assert parsed["weak_evidence_insights"] == []
