"""Generate deterministic data backfill plans for TactSpec previews."""

from __future__ import annotations

from typing import Any, Mapping

from max.spec._launch_governance import CSV_COLUMNS, base_context, item, render_csv, render_markdown, summary

DATA_BACKFILL_PLAN_SCHEMA_VERSION = "max-data-backfill-plan/v1"
KIND = "max.data_backfill_plan"
DATA_BACKFILL_PLAN_CSV_COLUMNS = CSV_COLUMNS
SECTIONS = (
    "scope",
    "affected_records",
    "source_of_truth",
    "dry_run_checklist",
    "batching_strategy",
    "idempotency_controls",
    "monitoring",
    "rollback",
    "evidence_artifacts",
)


def generate_data_backfill_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn dataset or job metadata into a deterministic production backfill plan."""
    context = base_context(tact_spec)
    backfill = _mapping(context["spec"].get("backfill") or context["spec"].get("dataset") or context["spec"].get("job"))
    dataset = _text(backfill.get("dataset") or backfill.get("name")) or context["workflow"]
    record_filter = _text(backfill.get("scope") or backfill.get("record_filter"))
    affected_count = _number(backfill.get("affected_records") or backfill.get("record_count"))
    unsafe_empty_scope = not record_filter and (affected_count is None or affected_count <= 0)
    source = _text(backfill.get("source_of_truth")) or "approved production source of truth"
    batch_size = _batch_size(backfill.get("batch_size")) or ("500 records" if context["strictness"] == "strict" else "1000 records")
    dry_run_sample = _text(backfill.get("dry_run_sample")) or ("full scoped dataset" if context["strictness"] == "strict" else "representative sample")

    scope = [
        item(
            "SCP1",
            "backfill_scope",
            f"Backfill {dataset} for {record_filter or 'no approved record filter'}.",
            "data_owner",
            severity="critical" if unsafe_empty_scope else "medium",
            action="Blocked until a non-empty scope or explicit record count is approved." if unsafe_empty_scope else "Approve scope before production writes.",
            evidence=["backfill.scope", "backfill.affected_records"],
        )
    ]
    affected_records = [
        item(
            "REC1",
            "record_inventory",
            f"Expected affected records: {_count_label(affected_count)}.",
            "data_owner",
            action="Export immutable candidate record IDs before dry run.",
            evidence=["backfill.affected_records"],
        )
    ]
    source_of_truth = [
        item("SOT1", "authoritative_source", f"Use {source} as the canonical input for {dataset}.", "engineering_owner", action="Block production if source freshness cannot be proven.", evidence=["backfill.source_of_truth"])
    ]
    dry_run_checklist = [
        item("DRY1", "dry_run_candidate_export", f"Run a write-disabled dry run against {dry_run_sample}.", "qa_owner", timing="before approval", action="Capture candidate counts, sample diffs, and skipped records.", evidence=["execution.validation_plan"]),
        item("DRY2", "dry_run_reconciliation", "Compare dry-run output to source totals and expected transformed values.", "data_owner", timing="before production", action="Resolve mismatches before enabling writes.", evidence=["backfill.source_of_truth"]),
    ]
    batching_strategy = [
        item("BAT1", "bounded_batches", f"Process {batch_size} per batch with checkpointed progress for {dataset}.", "engineering_owner", action="Pause between batches when guardrails breach.", evidence=["backfill.batch_size"]),
        item("BAT2", "traffic_window", "Run batches during the approved low-traffic maintenance or staffed support window.", "release_manager", timing="production window", evidence=["project.support_context"]),
    ]
    idempotency_controls = [
        item("IDM1", "idempotent_writes", "Use deterministic record keys, upsert guards, and per-record completion markers.", "engineering_owner", action="Re-running the job must not duplicate or overwrite newer customer data.", evidence=["solution.technical_approach"]),
        item("IDM2", "checkpoint_resume", "Persist batch checkpoints and failed record IDs for restart without widening scope.", "engineering_owner", evidence=["backfill.scope"]),
    ]
    monitoring = [
        item("MON1", "batch_dashboard", "Track processed, skipped, failed, retried, and rollback-required records by batch.", "on_call_owner", timing="during every batch", action="Page owner on critical error spikes.", evidence=["execution.risks"]),
        item("MON2", "customer_impact_watch", f"Watch support and workflow signals for {context['target_user']}.", "support_owner", timing="production window", evidence=["support_context"]),
    ]
    rollback = [
        item("RB1", "restore_snapshot", "Prepare pre-backfill snapshot or inverse patch for all mutated records.", "engineering_owner", severity="high", action="Rollback must be rehearsed before production write enablement.", evidence=["execution.validation_plan"]),
        item("RB2", "stop_criteria", "Stop the job on unexpected scope expansion, data integrity failures, or customer-facing errors.", "incident_commander", severity="critical", action="Freeze remaining batches and start rollback review.", evidence=["execution.risks"]),
    ]
    evidence_artifacts = [
        item("EV1", "completion_report", "Attach candidate export, dry-run output, batch logs, reconciliation results, and rollback readiness proof.", "release_manager", action="Required for completion sign-off.", evidence=["evidence.references"]),
        item("EV2", "approval_record", "Record scope approval, source-of-truth owner approval, and post-backfill validation sign-off.", "data_owner", action="Required before marking the backfill complete.", evidence=["backfill.approvals"]),
    ]

    return {
        "schema_version": DATA_BACKFILL_PLAN_SCHEMA_VERSION,
        "kind": KIND,
        "source": context["source"],
        "summary": summary(context, dataset=dataset, unsafe_empty_scope=unsafe_empty_scope),
        "scope": scope,
        "affected_records": affected_records,
        "source_of_truth": source_of_truth,
        "dry_run_checklist": dry_run_checklist,
        "batching_strategy": batching_strategy,
        "idempotency_controls": idempotency_controls,
        "monitoring": monitoring,
        "rollback": rollback,
        "evidence_artifacts": evidence_artifacts,
        "evidence_references": context["evidence_references"],
    }


def render_data_backfill_plan_markdown(plan: dict[str, Any]) -> str:
    return render_markdown(plan, "Data Backfill Plan", SECTIONS)


def render_data_backfill_plan_csv(plan: dict[str, Any]) -> str:
    return render_csv(plan, SECTIONS)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _count_label(value: int | None) -> str:
    return str(value) if value is not None else "unknown"


def _batch_size(value: Any) -> str:
    number = _number(value)
    if number is not None:
        return f"{number} records"
    return _text(value)
