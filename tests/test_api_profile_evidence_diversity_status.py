from __future__ import annotations

import json

from max.api.profile_evidence_diversity_status import profile_evidence_diversity_status_to_json


def test_profile_evidence_diversity_status_scores_and_flags_thresholds() -> None:
    parsed = json.loads(
        profile_evidence_diversity_status_to_json(
            {
                "low_diversity_threshold": 0.6,
                "dominance_threshold": 0.65,
                "profiles": [
                    {"profile": "healthy", "source_counts": {"crm": 2, "tickets": 2, "calls": 1}, "category_counts": {"pain": 3, "budget": 2}, "corroboration_count": 2},
                    {"profile": "risky", "source_counts": {"crm": 9, "tickets": 1}, "category_counts": {"pain": 10}, "dominant_source_share": 0.9},
                ],
            }
        )
    )

    assert [row["profile"] for row in parsed["low_diversity_profiles"]] == ["risky"]
    assert "dominant_source" in parsed["low_diversity_profiles"][0]["risk_flags"]
    assert parsed["profile_diversity"][1]["profile"] == "healthy"


def test_profile_evidence_diversity_status_missing_evidence_is_safe_zero() -> None:
    parsed = json.loads(profile_evidence_diversity_status_to_json({"profiles": [{}]}))

    assert parsed["profile_diversity"][0]["diversity_score"] == 0.0
    assert parsed["profile_diversity"][0]["risk_flags"] == ["missing_evidence", "low_diversity"]


def test_profile_evidence_diversity_status_mix_totals_and_schema() -> None:
    parsed = json.loads(
        profile_evidence_diversity_status_to_json(
            {"profile_diversity": [{"profile_id": "p", "evidence": [{"source": "a", "category": "x"}, {"source": "a", "category": "y"}]}]},
            as_of="2026-05-21T00:00:00Z",
        )
    )

    assert parsed["source_mix"] == [{"count": 2, "source": "a"}]
    assert parsed["category_mix"] == [{"category": "x", "count": 1}, {"category": "y", "count": 1}]
    assert set(parsed) == {"schema_version", "kind", "summary", "profile_diversity", "low_diversity_profiles", "source_mix", "category_mix", "metadata"}
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"
