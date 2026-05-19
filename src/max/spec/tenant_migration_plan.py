"""Generate deterministic tenant migration plans for TactSpec previews."""

from __future__ import annotations

from typing import Any, Mapping

from max.spec._launch_governance import CSV_COLUMNS, base_context, item, render_csv, render_markdown, summary

TENANT_MIGRATION_PLAN_SCHEMA_VERSION = "max-tenant-migration-plan/v1"
KIND = "max.tenant_migration_plan"
TENANT_MIGRATION_PLAN_CSV_COLUMNS = CSV_COLUMNS
SECTIONS = ("tenant_eligibility", "environments", "migration_window", "data_copy_steps", "validation_checks", "communications", "rollback", "evidence")


def generate_tenant_migration_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    context = base_context(tact_spec)
    migration = _mapping(context["spec"].get("tenant_migration") or context["spec"].get("migration"))
    tenant = _text(migration.get("tenant_id") or migration.get("tenant")) or context["source"].get("idea_id") or "target tenant"
    source_env = _text(migration.get("source_environment")) or "current production environment"
    target_env = _text(migration.get("target_environment")) or "target production environment"
    window = _text(migration.get("migration_window")) or ("staffed maintenance window" if context["strictness"] == "strict" else "scheduled migration window")
    downtime = _bool(migration.get("customer_facing_downtime"))

    return {
        "schema_version": TENANT_MIGRATION_PLAN_SCHEMA_VERSION,
        "kind": KIND,
        "source": context["source"],
        "summary": summary(context, tenant=tenant, explicit_approval_required=downtime),
        "tenant_eligibility": [
            item("ELG1", "eligibility_review", f"Confirm {tenant} is eligible for migration and has no unresolved billing, legal, or support blocks.", "customer_success_owner", action="Block migration until eligibility is approved.", evidence=["tenant_migration.tenant_id"])
        ],
        "environments": [
            item("ENV1", "source_environment", f"Source environment: {source_env}.", "engineering_owner", evidence=["tenant_migration.source_environment"]),
            item("ENV2", "target_environment", f"Target environment: {target_env}.", "engineering_owner", evidence=["tenant_migration.target_environment"]),
        ],
        "migration_window": [
            item("WIN1", "freeze_window", f"Run migration during {window}.", "release_manager", severity="high" if downtime else "medium", action="Requires explicit approval for customer-facing downtime." if downtime else "Announce freeze before writes are paused.", evidence=["tenant_migration.migration_window"])
        ],
        "data_copy_steps": [
            item("CPY1", "snapshot_source", "Take source snapshot and export tenant-scoped records with checksums.", "data_owner", timing="before freeze", evidence=["solution.technical_approach"]),
            item("CPY2", "copy_to_target", "Copy tenant data to target environment with resumable jobs and preserved audit identifiers.", "engineering_owner", timing="during freeze", evidence=["execution.validation_plan"]),
        ],
        "validation_checks": [
            item("VAL1", "record_reconciliation", "Compare source and target counts, checksums, permissions, and key workflows.", "qa_owner", action="Do not release tenant until validation passes.", evidence=["execution.validation_plan"])
        ],
        "communications": [
            item("COM1", "customer_notice", f"Notify tenant stakeholders, support, and account owner about {window}.", "customer_success_owner", stakeholder=tenant, evidence=["project.support_context"])
        ],
        "rollback": [
            item("RB1", "return_to_source", "Keep source tenant frozen but intact until target validation and customer acceptance complete.", "engineering_owner", severity="high", action="Route traffic back to source on validation failure.", evidence=["execution.risks"])
        ],
        "evidence": [
            item("EV1", "migration_evidence", "Attach eligibility approval, snapshots, copy logs, validation report, customer communications, and rollback readiness.", "release_manager", action="Required for closure.", evidence=["evidence.references"])
        ],
        "evidence_references": context["evidence_references"],
    }


def render_tenant_migration_plan_markdown(plan: dict[str, Any]) -> str:
    return render_markdown(plan, "Tenant Migration Plan", SECTIONS)


def render_tenant_migration_plan_csv(plan: dict[str, Any]) -> str:
    return render_csv(plan, SECTIONS)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}
