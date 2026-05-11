"""Generate deterministic feature flag rollout plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import CSV_COLUMNS as FEATURE_FLAG_ROLLOUT_PLAN_CSV_COLUMNS
from max.spec._planning_common import context, extend_section, markdown_header, render_csv, render_evidence, render_item, summary

SCHEMA_VERSION = "max-feature-flag-rollout-plan/v1"
KIND = "max.feature_flag_rollout_plan"
_SECTIONS = ("flags", "rollout_stages", "guardrail_metrics", "rollback_triggers", "owner_handoffs")


def generate_feature_flag_rollout_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    ctx = context(tact_spec)
    strict = ctx["strictness"] == "strict"
    ramp = ("1%", "5%", "25%", "50%") if strict else ("5%", "25%", "50%", "100%")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, stage_count=len(ramp)),
        "flags": [
            _item("FLG1", "primary_exposure", "flag", f"Controls access to {ctx['workflow_context']} for {ctx['target_user']}.", "launch_owner", "required", references=["project.workflow_context"]),
            _item("FLG2", "integration_path", "flag", f"Separately gates integration behavior for {ctx['technical_approach']}.", "technical_owner", "conditional", references=["solution.technical_approach"]),
        ],
        "rollout_stages": [
            _item(f"STG{idx}", f"ramp_{percent.replace('%', '')}", "stage", f"Expose {percent} of eligible cohort after guardrails pass.", "launch_owner", "required", timing=f"stage {idx}", references=["summary.risk_level"])
            for idx, percent in enumerate(ramp, start=1)
        ],
        "guardrail_metrics": [
            _item("GRD1", "slo_health", "guardrail", "Availability, latency, and error budget remain within launch thresholds.", "on_call_owner", "critical" if strict else "high", references=["summary.strictness"]),
            _item("GRD2", "acceptance_signal", "guardrail", "Launch-critical acceptance criteria and support intake stay clean.", "qa_owner", "high", references=["acceptance_criteria"]),
        ],
        "rollback_triggers": [
            _item("RBT1", "critical_alert", "rollback", "Any critical alert or unresolved customer-visible regression fires.", "on_call_owner", "critical", references=["guardrail_metrics"]),
            _item("RBT2", "risk_materialized", "rollback", "Known risk materializes without approved mitigation.", "launch_owner", "critical" if strict else "high", references=["execution.risks"]),
        ],
        "owner_handoffs": [
            _item("HOF1", "launch_to_on_call", "handoff", "Launch owner transfers stage status, guardrail state, and rollback authority.", "launch_owner", "required", references=["rollout_stages"]),
            _item("HOF2", "product_to_support", "handoff", "Product owner shares cohort, customer promise, and support response guidance.", "product_owner", "required", references=["project.buyer", "project.specific_user"]),
        ],
        "evidence_references": ctx["evidence_references"],
    }


def render_feature_flag_rollout_plan_markdown(plan: dict[str, Any]) -> str:
    lines = markdown_header(plan if isinstance(plan, dict) else {}, "Feature Flag Rollout Plan")
    for title, key in (("Flags", "flags"), ("Rollout Stages", "rollout_stages"), ("Guardrail Metrics", "guardrail_metrics"), ("Rollback Triggers", "rollback_triggers"), ("Owner Handoffs", "owner_handoffs"), ("Evidence References", "evidence_references")):
        extend_section(lines, title, (plan or {}).get(key) or [], render_evidence if key == "evidence_references" else render_item)
    return "\n".join(lines).rstrip() + "\n"


def render_feature_flag_rollout_plan_csv(plan: dict[str, Any]) -> str:
    return render_csv(plan if isinstance(plan, dict) else {}, _SECTIONS)


def _item(item_id: str, name: str, item_type: str, description: str, owner: str, severity: str, *, timing: str | None = None, references: list[str]) -> dict[str, Any]:
    item = {"id": item_id, "name": name, "type": item_type, "description": description, "owner": owner, "severity": severity, "references": references}
    if timing:
        item["timing"] = timing
    return item
