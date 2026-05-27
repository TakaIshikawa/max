"""Generate deterministic model retirement plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.model_retirement_plan.v1"
KIND = "max.spec.model_retirement_plan"


def generate_model_retirement_plan(spec_like: Any) -> dict[str, Any]:
    """Return a stable plan for retiring a production model."""
    _spec, ctx, hints, evidence_ids = base(spec_like, "model_retirement")
    workflows = unique_records(
        named(hints.get("impacted_workflows") or hints.get("workflows"), ("workflow", "name")),
        [{"name": ctx["workflow_context"], "owner": "product_owner"}],
    )
    replacement_model = compact(hints.get("replacement_model") or hints.get("replacement") or hints.get("target_model"))
    blockers = _blockers(hints, replacement_model, evidence_ids)
    warnings = _warnings(hints, evidence_ids)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, impacted_workflow_count=len(workflows), replacement_model=replacement_model or None, blocker_count=len(blockers), warning_count=len(warnings)),
        "impacted_workflows": [
            item("MRW", index, record, "product_owner", evidence_ids, "Review impacted model workflow", name_keys=("name", "workflow"), extra_keys=("impact", "traffic"))
            for index, record in enumerate(workflows, start=1)
        ],
        "replacement_model": {
            "name": replacement_model or "missing",
            "owner": compact(hints.get("owner") or hints.get("model_owner")) or "",
            "evaluation_evidence": compact(hints.get("evaluation_evidence") or hints.get("eval_evidence")) or "",
        },
        "migration_checkpoints": section(hints, ("migration_checkpoints", "checkpoints"), "MRC", "release_manager", "Run model retirement migration checkpoint", evidence_ids, ["shadow validation", "canary traffic shift", "full cutover", "post-cutover quality review"]),
        "customer_communication": section(hints, ("customer_communication", "communications"), "MRN", "customer_success_owner", "Communicate model retirement", evidence_ids, ["announce retirement timeline, replacement behavior, customer impact, and support path"]),
        "rollback_window": section(hints, ("rollback_window", "rollback"), "MRB", "on_call_owner", "Define model retirement rollback window", evidence_ids, ["retain routing and artifacts for rollback through the approved observation window"]),
        "archive_requirements": section(hints, ("archive_requirements", "archive"), "MRA", "compliance_owner", "Archive retired model evidence", evidence_ids, ["model card, prompts, eval results, approval record, rollout log, and retirement decision"]),
        "validation_checks": section(hints, ("validation_checks", "validation"), "MRV", "quality_owner", "Validate model retirement", evidence_ids, ["replacement model evaluation evidence attached", "archive evidence complete", "customer communication approved"]),
        "blockers": blockers,
        "warnings": warnings,
        "evidence_references": ctx["evidence_references"],
    }


def _blockers(hints: dict[str, Any], replacement_model: str, evidence_ids: list[str]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if not replacement_model:
        blockers.append(row("MRK", 1, "missing replacement model", "ml_platform_owner", "Model retirement requires a named replacement model before migration.", evidence_ids, severity="critical"))
    if not compact(hints.get("owner") or hints.get("model_owner")):
        blockers.append(row("MRK", len(blockers) + 1, "missing retirement owner", "program_owner", "Model retirement requires an accountable owner.", evidence_ids, severity="high"))
    if not compact(hints.get("evaluation_evidence") or hints.get("eval_evidence")):
        blockers.append(row("MRK", len(blockers) + 1, "missing evaluation evidence", "quality_owner", "Replacement model evaluation evidence is required before retirement.", evidence_ids, severity="high"))
    return blockers


def _warnings(hints: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    freshness = compact(hints.get("evaluation_freshness") or hints.get("evaluation_status")).lower()
    if freshness in {"stale", "expired", "outdated"}:
        return [row("MRW", 1, "stale evaluation evidence", "quality_owner", "Replacement model evaluation evidence is stale and should be refreshed before cutover.", evidence_ids, severity="medium")]
    return []
