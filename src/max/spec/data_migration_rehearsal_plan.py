"""Generate deterministic data migration rehearsal plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import CSV_COLUMNS as DATA_MIGRATION_REHEARSAL_PLAN_CSV_COLUMNS
from max.spec._planning_common import context, extend_section, markdown_header, render_csv, render_evidence, render_item, summary

SCHEMA_VERSION = "max-data-migration-rehearsal-plan/v1"
KIND = "max.data_migration_rehearsal_plan"
_SECTIONS = ("rehearsal_stages", "fixture_requirements", "validation_queries", "reconciliation_checks", "cutover_gates", "rollback_rehearsals")


def generate_data_migration_rehearsal_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    ctx = context(tact_spec)
    deep = ctx["strictness"] == "strict" or any("migration" in risk.lower() or "data" in risk.lower() for risk in ctx["risks"])
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, rehearsal_depth="deep" if deep else "standard"),
        "rehearsal_stages": [
            _item("DRY1", "baseline_snapshot", "stage", "Capture source counts, checksums, and rollback marker before dry run.", "data_owner", "required", "dry run start", references=["execution.validation_plan"]),
            _item("DRY2", "full_replay", "stage", "Replay migration against production-shaped fixtures and record duration.", "technical_owner", "required" if deep else "recommended", "dry run", references=["solution.technical_approach"]),
        ],
        "fixture_requirements": [
            _item("FIX1", "representative_records", "fixture", f"Include records for {ctx['workflow_context']} and edge cases from known risks.", "qa_owner", "required", "before dry run", references=["project.workflow_context", "execution.risks"]),
            _item("FIX2", "failure_cases", "fixture", "Include malformed, duplicated, and permission-limited records.", "data_owner", "required" if deep else "recommended", "before dry run", references=["summary.risk_level"]),
        ],
        "validation_queries": [
            _item("VAL1", "row_count_match", "validation_query", "Source and target entity counts match accepted tolerances.", "data_owner", "critical", "after dry run", references=["fixture_requirements"]),
            _item("VAL2", "workflow_acceptance", "validation_query", "Migrated records satisfy launch-critical acceptance criteria.", "qa_owner", "critical" if deep else "high", "after dry run", references=["acceptance_criteria"]),
        ],
        "reconciliation_checks": [
            _item("REC1", "checksum_reconciliation", "reconciliation", "Checksums or sampled field comparisons reconcile before cutover.", "data_owner", "required", "after validation", references=["validation_queries"]),
            _item("REC2", "support_exception_review", "reconciliation", "Unmatched records have owner, disposition, and customer impact notes.", "support_owner", "required" if deep else "recommended", "after validation", references=["project.specific_user"]),
        ],
        "cutover_gates": [
            _item("GAT1", "zero_critical_mismatch", "cutover_gate", "No critical mismatch, data-loss risk, or unresolved rollback blocker remains.", "release_manager", "required", "go/no-go", references=["reconciliation_checks"]),
            _item("GAT2", "duration_budget", "cutover_gate", "Dry-run duration fits the approved cutover window.", "technical_owner", "required" if deep else "recommended", "go/no-go", references=["rehearsal_stages"]),
        ],
        "rollback_rehearsals": [
            _item("RBK1", "restore_snapshot", "rollback", "Restore source snapshot and verify user workflow returns to pre-migration state.", "technical_owner", "required", "dry run close", references=["DRY1"]),
            _item("RBK2", "customer_comms", "rollback", "Prepare customer and support notice for rollback-triggered delay.", "product_owner", "required" if deep else "recommended", "dry run close", references=["project.buyer"]),
        ],
        "evidence_references": ctx["evidence_references"],
    }


def render_data_migration_rehearsal_plan_markdown(plan: dict[str, Any]) -> str:
    lines = markdown_header(plan if isinstance(plan, dict) else {}, "Data Migration Rehearsal Plan")
    for title, key in (("Rehearsal Stages", "rehearsal_stages"), ("Fixture Requirements", "fixture_requirements"), ("Validation Queries", "validation_queries"), ("Reconciliation Checks", "reconciliation_checks"), ("Cutover Gates", "cutover_gates"), ("Rollback Rehearsals", "rollback_rehearsals"), ("Evidence References", "evidence_references")):
        extend_section(lines, title, (plan or {}).get(key) or [], render_evidence if key == "evidence_references" else render_item)
    return "\n".join(lines).rstrip() + "\n"


def render_data_migration_rehearsal_plan_csv(plan: dict[str, Any]) -> str:
    return render_csv(plan if isinstance(plan, dict) else {}, _SECTIONS)


def _item(item_id: str, name: str, item_type: str, description: str, owner: str, severity: str, timing: str, *, references: list[str]) -> dict[str, Any]:
    return {"id": item_id, "name": name, "type": item_type, "description": description, "owner": owner, "severity": severity, "timing": timing, "references": references}
