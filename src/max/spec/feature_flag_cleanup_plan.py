"""Generate deterministic feature flag cleanup plans for TactSpec previews."""

from __future__ import annotations

from typing import Any, Mapping

from max.spec._launch_governance import CSV_COLUMNS, base_context, item, render_csv, render_markdown, summary

FEATURE_FLAG_CLEANUP_PLAN_SCHEMA_VERSION = "max-feature-flag-cleanup-plan/v1"
KIND = "max.feature_flag_cleanup_plan"
FEATURE_FLAG_CLEANUP_PLAN_CSV_COLUMNS = CSV_COLUMNS
SECTIONS = ("stale_flag_inventory", "owners", "current_exposure", "removal_checklist", "data_config_cleanup", "monitoring", "rollback", "evidence")


def generate_feature_flag_cleanup_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    context = base_context(tact_spec)
    cleanup = _mapping(context["spec"].get("flag_cleanup") or context["spec"].get("feature_flag") or context["spec"].get("flag"))
    flag_name = _text(cleanup.get("flag_name") or cleanup.get("name")) or "primary_workflow_enabled"
    state = (_text(cleanup.get("rollout_state") or cleanup.get("state")) or "unknown").lower()
    active_state = state in {"active", "partial", "partially_rolled_out", "rolling_out", "enabled"}
    owner = _text(cleanup.get("owner")) or "release_owner"
    exposure = _text(cleanup.get("current_exposure")) or ("active or partial rollout" if active_state else "no known active exposure")

    return {
        "schema_version": FEATURE_FLAG_CLEANUP_PLAN_SCHEMA_VERSION,
        "kind": KIND,
        "source": context["source"],
        "summary": summary(context, flag_name=flag_name, extra_approval_required=active_state),
        "stale_flag_inventory": [
            item("FFI1", "flag_record", f"Retire stale flag {flag_name} after confirming it no longer gates active behavior.", owner, severity="high" if active_state else "medium", action="Require extra approval before cleanup." if active_state else "Proceed after owner confirmation.", evidence=["flag_cleanup.flag_name"])
        ],
        "owners": [
            item("OWN1", "cleanup_owner", f"{owner} owns code, config, and stakeholder sign-off for {flag_name}.", owner, evidence=["flag_cleanup.owner"])
        ],
        "current_exposure": [
            item("EXP1", "rollout_state", f"Current exposure is {exposure}.", "release_owner", severity="high" if active_state else "low", action="Escalate active or partially rolled-out flags before removal." if active_state else "Record final exposure snapshot.", evidence=["flag_cleanup.rollout_state"])
        ],
        "removal_checklist": [
            item("REM1", "code_references", f"Remove reads, writes, tests, and dead branches for {flag_name}.", "engineering_owner", action="Search all services before merge.", evidence=["solution.technical_approach"]),
            item("REM2", "release_sequence", "Ship cleanup behind the normal release process with owner review.", "release_owner", timing="cleanup release", evidence=["execution.validation_plan"]),
        ],
        "data_config_cleanup": [
            item("CFG1", "configuration_delete", "Delete flag records, targeting rules, stale cohorts, and dashboards that only support the retired flag.", "engineering_owner", action="Preserve audit trail before deletion.", evidence=["flag_cleanup.config"])
        ],
        "monitoring": [
            item("MON1", "post_cleanup_watch", f"Watch errors and workflow conversion for {context['workflow']} after cleanup.", "on_call_owner", timing="24 hours", evidence=["project.workflow_context"])
        ],
        "rollback": [
            item("RB1", "restore_flag_path", "Keep a revert plan that restores the previous flag evaluation path or disables the cleanup release.", "release_owner", severity="high", evidence=["execution.risks"])
        ],
        "evidence": [
            item("EV1", "cleanup_evidence", "Attach owner approval, exposure snapshot, code search output, config deletion log, and post-release monitoring results.", "release_manager", action="Required for closure.", evidence=["evidence.references"])
        ],
        "evidence_references": context["evidence_references"],
    }


def render_feature_flag_cleanup_plan_markdown(plan: dict[str, Any]) -> str:
    return render_markdown(plan, "Feature Flag Cleanup Plan", SECTIONS)


def render_feature_flag_cleanup_plan_csv(plan: dict[str, Any]) -> str:
    return render_csv(plan, SECTIONS)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
