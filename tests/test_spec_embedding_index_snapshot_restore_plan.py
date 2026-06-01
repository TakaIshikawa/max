from __future__ import annotations

import json

from max.spec.embedding_index_snapshot_restore_plan import generate_embedding_index_snapshot_restore_plan


def test_embedding_index_snapshot_restore_plan_selects_latest_compatible_snapshot() -> None:
    plan = generate_embedding_index_snapshot_restore_plan(
        [{"index": "docs", "dimension": 1536, "embedding_model": "text-embedding-3-small"}],
        [
            {"snapshot_id": "snap-old", "index": "docs", "dimension": 1536, "embedding_model": "text-embedding-3-small", "created_at": "2026-05-01T00:00:00Z"},
            {"snapshot_id": "snap-new", "index": "docs", "dimension": 1536, "embedding_model": "text-embedding-3-small", "created_at": "2026-06-01T00:00:00Z"},
        ],
    )

    assert plan["snapshot_selection"][0]["snapshot_id"] == "snap-new"
    assert plan["summary"]["status"] == "ready"
    assert json.loads(json.dumps(plan)) == plan


def test_embedding_index_snapshot_restore_plan_blocks_dimension_mismatch() -> None:
    plan = generate_embedding_index_snapshot_restore_plan(
        [{"index": "docs", "dimension": 1536, "embedding_model": "small"}],
        [{"snapshot_id": "snap-large", "index": "docs", "dimension": 3072, "embedding_model": "small"}],
    )

    assert plan["summary"]["status"] == "blocked"
    assert plan["blockers"][0]["affected_index"] == "docs"
    assert "No compatible snapshot" in plan["blockers"][0]["description"]


def test_embedding_index_snapshot_restore_plan_includes_verification_queries() -> None:
    plan = generate_embedding_index_snapshot_restore_plan(
        [{"index": "docs", "dimension": 1536}],
        [{"snapshot_id": "snap", "index": "docs", "dimension": 1536}],
        verification_queries=[{"query": "refund policy", "expected_result": "policy document"}, "pricing page"],
    )

    assert [item["name"] for item in plan["verification_queries"]] == ["refund policy", "pricing page"]
    assert plan["verification_queries"][0]["expected_result"] == "policy document"
    assert set(plan) >= {"snapshot_selection", "compatibility_checks", "restore_steps", "verification_queries", "rollback"}


def test_embedding_index_snapshot_restore_plan_blocks_missing_snapshot() -> None:
    plan = generate_embedding_index_snapshot_restore_plan([{"index": "docs"}], [])

    assert plan["summary"]["status"] == "blocked"
    assert plan["snapshot_selection"][0]["status"] == "blocked"
    assert plan["blockers"][0]["description"] == "No snapshot is available for docs."
