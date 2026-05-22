"""Generate deterministic production data backfill plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.production_data_backfill_plan.v1"
KIND = "max.spec.production_data_backfill_plan"


def generate_production_data_backfill_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "production_data_backfill")
    backfills = unique_records(
        named(hints.get("backfills") or hints.get("affected_tables") or hints.get("entities"), ("table", "entity")),
        [{"name": "production backfill item", "owner": "data_owner", "severity": "medium"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, backfill_count=len(backfills)),
        "backfill_scope": [
            item("PDB", index, record, "data_owner", evidence_ids, "Review production backfill scope", name_keys=("name", "table", "entity"), extra_keys=("table", "entity", "criteria"))
            for index, record in enumerate(backfills, start=1)
        ],
        "selection_criteria": section(hints, ("selection_criteria", "criteria"), "PDS", "data_owner", "Approve selection criteria", evidence_ids, ["immutable candidate record selection criteria"]),
        "dry_run_evidence": section(hints, ("dry_run", "dry_run_evidence"), "PDD", "qa_owner", "Capture dry-run evidence", evidence_ids, ["write-disabled dry run counts, diffs, and skips"]),
        "batching_throttling": section(hints, ("batching", "throttling", "batching_throttling"), "PDT", "engineering_owner", "Control batching and throttling", evidence_ids, ["bounded batches, pauses, and load guardrails"]),
        "idempotency_controls": section(hints, ("idempotency", "idempotency_controls"), "PDI", "engineering_owner", "Verify idempotency control", evidence_ids, ["deterministic keys, checkpoints, and retry guards"]),
        "observability": section(hints, ("observability", "monitoring"), "PDO", "on_call_owner", "Observe production backfill", evidence_ids, ["processed, skipped, failed, and reconciled metrics"]),
        "customer_impact": section(hints, ("customer_impact", "impact"), "PDC", "support_owner", "Assess customer impact", evidence_ids, ["customer-facing workflow and support watch"]),
        "approval_gates": section(hints, ("approvals", "approvers"), "PDA", "approval_owner", "Capture production backfill approval", evidence_ids, ["data, engineering, support, and release approval"]),
        "rollback_reconciliation": section(hints, ("rollback", "reconciliation", "rollback_reconciliation"), "PDR", "engineering_owner", "Rollback and reconcile backfill", evidence_ids, ["inverse patch, snapshot restore, and reconciliation report"]),
        "evidence_references": ctx["evidence_references"],
    }
