"""Generate deterministic data migration rehearsal plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._launch_governance import CSV_COLUMNS, base_context, item, render_csv, render_markdown, summary

DATA_MIGRATION_REHEARSAL_PLAN_SCHEMA_VERSION = "max-data-migration-rehearsal-plan/v1"
KIND = "max.data_migration_rehearsal_plan"
DATA_MIGRATION_REHEARSAL_PLAN_CSV_COLUMNS = CSV_COLUMNS
SECTIONS = ("rehearsal_stages", "fixture_requirements", "validation_queries", "reconciliation_checks", "cutover_gates", "rollback_rehearsals")


def generate_data_migration_rehearsal_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    context = base_context(tact_spec)
    strict = context["strictness"] == "strict"
    rehearsal_stages = [
        item("DRS1", "schema_dry_run", f"Run migration against representative fixtures for {context['workflow']}.", "data_owner", timing="T-5 days" if strict else "T-3 days", evidence=["project.workflow_context"]),
        item("DRS2", "full_volume_rehearsal", "Replay expected launch volume and record duration, errors, and restart behavior.", "engineering_owner", timing="T-2 days" if strict else "T-1 day", evidence=["solution.technical_approach"]),
    ]
    fixture_requirements = [
        item("FR1", "golden_dataset", f"Include happy-path records used by {context['target_user']}.", "qa_owner", evidence=["project.target_users"]),
        item("FR2", "edge_case_dataset", "Include nulls, duplicates, permission boundaries, and known risk examples.", "data_owner", evidence=["execution.risks"]),
    ]
    validation_queries = [
        item("VQ1", "row_count_validation", "Compare source and target counts by status, owner, and workflow stage.", "data_owner", action="Expected delta is documented and approved.", evidence=["fixture_requirements"]),
        item("VQ2", "referential_integrity", "Confirm migrated records preserve required relationships and audit identifiers.", "engineering_owner", action="Block cutover on orphaned critical records.", evidence=["solution.technical_approach"]),
    ]
    reconciliation_checks = [
        item("RC1", "business_reconciliation", f"{context['buyer']} reviews sampled business outcomes after rehearsal.", "product_owner", stakeholder=context["buyer"], evidence=["project.buyer"]),
        item("RC2", "support_reconciliation", f"Support confirms migrated records support {context['support_context']}.", "support_owner", stakeholder="support team", evidence=["support_context"]),
    ]
    cutover_gates = [
        item("CG1", "clean_rehearsal_gate", "Latest rehearsal completed with no unresolved critical defects.", "release_manager", action="Required" if strict else "Recommended", evidence=["rehearsal_stages"]),
        item("CG2", "rollback_ready_gate", "Rollback rehearsal has a measured duration and named owner.", "release_manager", action="Required before production cutover.", evidence=["rollback_rehearsals"]),
    ]
    rollback_rehearsals = [
        item("RR1", "restore_snapshot", "Restore source snapshot and verify customer-facing workflow returns to pre-cutover state.", "engineering_owner", timing="during final rehearsal", evidence=["execution.validation_plan"]),
        item("RR2", "communications_reversal", "Prepare customer/support message for aborted or reverted cutover.", "support_owner", timing="before production cutover", evidence=["support_context"]),
    ]
    return {"schema_version": DATA_MIGRATION_REHEARSAL_PLAN_SCHEMA_VERSION, "kind": KIND, "source": context["source"], "summary": summary(context), "rehearsal_stages": rehearsal_stages, "fixture_requirements": fixture_requirements, "validation_queries": validation_queries, "reconciliation_checks": reconciliation_checks, "cutover_gates": cutover_gates, "rollback_rehearsals": rollback_rehearsals, "evidence_references": context["evidence_references"]}


def render_data_migration_rehearsal_plan_markdown(plan: dict[str, Any]) -> str:
    return render_markdown(plan, "Data Migration Rehearsal Plan", SECTIONS)


def render_data_migration_rehearsal_plan_csv(plan: dict[str, Any]) -> str:
    return render_csv(plan, SECTIONS)
