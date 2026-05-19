from __future__ import annotations

import csv
from io import StringIO

from max.spec.data_backfill_plan import (
    DATA_BACKFILL_PLAN_CSV_COLUMNS,
    DATA_BACKFILL_PLAN_SCHEMA_VERSION,
    generate_data_backfill_plan,
    render_data_backfill_plan_csv,
    render_data_backfill_plan_markdown,
)


def test_data_backfill_plan_covers_production_controls() -> None:
    plan = generate_data_backfill_plan(_tact_spec())
    rows = list(csv.DictReader(StringIO(render_data_backfill_plan_csv(plan))))

    assert plan["schema_version"] == DATA_BACKFILL_PLAN_SCHEMA_VERSION
    assert plan["kind"] == "max.data_backfill_plan"
    assert {
        "scope",
        "affected_records",
        "source_of_truth",
        "dry_run_checklist",
        "batching_strategy",
        "idempotency_controls",
        "monitoring",
        "rollback",
        "evidence_artifacts",
    } <= set(plan)
    assert plan["summary"]["dataset"] == "accounts.region_code"
    assert plan["summary"]["unsafe_empty_scope"] is False
    assert plan["batching_strategy"][0]["description"].startswith("Process 250 records")
    assert "## Dry Run Checklist" in render_data_backfill_plan_markdown(plan)
    assert render_data_backfill_plan_csv(plan).splitlines()[0] == ",".join(DATA_BACKFILL_PLAN_CSV_COLUMNS)
    assert rows[0]["section"] == "scope"


def test_data_backfill_plan_uses_defaults_for_sparse_input() -> None:
    plan = generate_data_backfill_plan({"source": {"idea_id": "bf-sparse"}, "project": {"workflow_context": "account enrichment"}})

    assert plan["summary"]["dataset"] == "account enrichment"
    assert plan["source_of_truth"][0]["description"] == "Use approved production source of truth as the canonical input for account enrichment."
    assert plan["batching_strategy"][0]["description"].startswith("Process 1000 records")


def test_data_backfill_plan_flags_unsafe_empty_scope() -> None:
    plan = generate_data_backfill_plan({"project": {"title": "Empty Backfill"}, "backfill": {"dataset": "orders", "affected_records": 0}})

    assert plan["summary"]["unsafe_empty_scope"] is True
    assert plan["scope"][0]["severity"] == "critical"
    assert "Blocked until a non-empty scope" in plan["scope"][0]["action"]


def _tact_spec() -> dict:
    return {
        "source": {"idea_id": "bf-accounts"},
        "project": {"title": "Account Region Backfill", "specific_user": "billing analyst", "workflow_context": "account enrichment"},
        "solution": {"technical_approach": "Update account rows from the warehouse extract."},
        "execution": {"validation_plan": "Compare account counts and sampled transformed values."},
        "backfill": {
            "dataset": "accounts.region_code",
            "scope": "active enterprise accounts missing region_code",
            "affected_records": 1250,
            "source_of_truth": "warehouse.customer_accounts_v2",
            "batch_size": 250,
        },
    }
