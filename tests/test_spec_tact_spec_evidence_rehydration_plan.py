from __future__ import annotations

import pytest

from max.spec.tact_spec_evidence_rehydration_plan import generate_tact_spec_evidence_rehydration_plan


def test_tact_spec_evidence_rehydration_prioritizes_missing_and_unblocks_publication() -> None:
    plan = generate_tact_spec_evidence_rehydration_plan(
        {
            "metadata": {
                "tact_spec_evidence_rehydration": {
                    "spec_id": "spec-123",
                    "missing_evidence_ids": ["ev-m2", "ev-m1"],
                    "stale_evidence_ids": ["ev-s1"],
                    "source_systems": ["warehouse", "signals"],
                    "owner": "spec_owner",
                    "publication_blocked": True,
                }
            }
        }
    )

    assert [item["priority"] for item in plan["evidence_lookup"]] == ["missing", "missing", "stale"]
    assert [item["evidence_id"] for item in plan["evidence_lookup"]] == ["ev-m1", "ev-m2", "ev-s1"]
    assert plan["publication_unblock"][0]["required"] is True


def test_tact_spec_evidence_rehydration_allows_stale_only_and_validates_evidence_ids() -> None:
    plan = generate_tact_spec_evidence_rehydration_plan(
        {"metadata": {"tact_spec_evidence_rehydration": {"spec_id": "spec-123", "stale_evidence_ids": ["ev-s1"], "source_systems": ["warehouse"], "owner": "spec_owner"}}}
    )

    assert plan["evidence_lookup"][0]["priority"] == "stale"
    with pytest.raises(ValueError, match="missing_evidence_ids or stale_evidence_ids"):
        generate_tact_spec_evidence_rehydration_plan({"metadata": {"tact_spec_evidence_rehydration": {"spec_id": "spec-123", "source_systems": ["warehouse"], "owner": "spec_owner"}}})
