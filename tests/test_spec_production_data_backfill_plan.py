from __future__ import annotations

import json

from max.spec import generate_production_data_backfill_plan


def test_production_data_backfill_plan_sorts_items_and_sections() -> None:
    plan = generate_production_data_backfill_plan(
        _spec(
            "production_data_backfill",
            {
                "backfills": [
                    {"table": "invoice_items", "severity": "low", "criteria": "May invoices"},
                    {"table": "subscriptions", "severity": "high", "criteria": "missing status"},
                ],
                "selection_criteria": ["approved record IDs"],
                "dry_run": ["candidate diff"],
                "batching": ["100 records per batch"],
                "idempotency": ["upsert by stable key"],
                "observability": ["batch dashboard"],
                "customer_impact": ["support watch"],
                "approvals": ["data owner"],
                "reconciliation": ["totals report"],
            },
        )
    )

    assert plan["schema_version"] == "max.spec.production_data_backfill_plan.v1"
    assert [item["name"] for item in plan["backfill_scope"]] == ["subscriptions", "invoice_items"]
    assert set(plan) >= {"dry_run_evidence", "batching_throttling", "idempotency_controls", "observability", "approval_gates", "rollback_reconciliation"}
    assert json.loads(json.dumps(plan)) == plan


def test_production_data_backfill_plan_defaults_sparse_input() -> None:
    plan = generate_production_data_backfill_plan({})

    assert plan["backfill_scope"][0]["owner"] == "data_owner"
    assert plan["dry_run_evidence"][0]["name"] == "write-disabled dry run counts, diffs, and skips"


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"insight_ids": ["pdb-1"]}}
