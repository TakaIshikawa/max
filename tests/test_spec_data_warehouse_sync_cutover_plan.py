from __future__ import annotations

import json

from max.spec import generate_data_warehouse_sync_cutover_plan


def test_data_warehouse_sync_cutover_plan_prioritizes_risks() -> None:
    plan = generate_data_warehouse_sync_cutover_plan(
        _spec(
            "data_warehouse_sync_cutover",
            {
                "sync_scope": ["billing analytics sync"],
                "systems": [{"source": "postgres", "destination": "snowflake"}],
                "risks": [
                    {"schema": "events", "destination": "snowflake", "severity": "low"},
                    {"schema": "invoices", "destination": "bigquery", "severity": "high"},
                ],
                "compatibility": ["type mapping check"],
                "dual_run": ["checksum compare"],
                "lag": ["15 minute lag alert"],
                "impact": ["finance dashboards"],
                "cutover": ["switch destination"],
                "rollback": ["replay from checkpoint"],
            },
        )
    )

    assert plan["schema_version"] == "max.spec.data_warehouse_sync_cutover_plan.v1"
    assert [item["name"] for item in plan["schema_destination_risks"]] == ["invoices", "events"]
    assert set(plan) >= {"source_destination_systems", "compatibility_checks", "dual_run_validation", "lag_monitoring", "cutover_steps", "rollback_replay"}
    assert json.loads(json.dumps(plan)) == plan


def test_data_warehouse_sync_cutover_plan_defaults_sparse_input() -> None:
    plan = generate_data_warehouse_sync_cutover_plan({})

    assert plan["schema_destination_risks"][0]["owner"] == "analytics_owner"
    assert plan["dual_run_validation"][0]["name"] == "row counts, checksums, freshness, and sample query comparison"


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"signal_ids": ["dws-1"]}}
