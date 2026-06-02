from __future__ import annotations

import json

from max.api import insight_evidence_chain_to_json


def test_insight_evidence_chain_normalizes_aliases_and_summary() -> None:
    parsed = json.loads(
        insight_evidence_chain_to_json(
            {
                "id": "ins-1",
                "confidence": 0.82,
                "evidence": [
                    {"id": "s2", "source": "rss", "url": "https://example.com/2", "observed_at": "2026-05-02T00:00:00Z"},
                    {"signal_id": "s1", "source_adapter": "github", "url": "https://example.com/1", "published_at": "2026-05-01T00:00:00Z"},
                    {"signal_id": "missing", "source": "github"},
                ],
                "buildable_units": [{"id": "u1", "title": "Unit"}],
            },
            as_of="2026-06-01T00:00:00Z",
        )
    )

    assert parsed["schema_version"] == "max.api.insight_evidence_chain.v1"
    assert parsed["kind"] == "max.api.insight_evidence_chain"
    assert parsed["summary"] == {
        "confidence_score": 0.82,
        "missing_signal_count": 1,
        "signal_count": 3,
        "source_count": 2,
        "unit_count": 1,
    }
    assert [row["signal_id"] for row in parsed["evidence_chain"]] == ["missing", "s1", "s2"]
    assert parsed["source_breakdown"] == [{"signal_count": 2, "source": "github"}, {"signal_count": 1, "source": "rss"}]
    assert parsed["missing_links"][0]["signal_id"] == "missing"


def test_insight_evidence_chain_supports_insight_and_units_aliases() -> None:
    parsed = json.loads(
        insight_evidence_chain_to_json(
            {
                "insight": {"insight_id": "i2", "confidence_score": "0.5"},
                "signals": [{"signal_id": "s1", "source": "hn", "url": "https://example.com"}],
                "units": [{"unit_id": "unit-a", "name": "A"}],
            }
        )
    )

    assert parsed["insight"]["insight_id"] == "i2"
    assert parsed["summary"]["confidence_score"] == 0.5
    assert parsed["buildable_units"][0]["unit_id"] == "unit-a"
