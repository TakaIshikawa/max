"""Generate deterministic runbook ownership plans for TactSpec previews."""

from __future__ import annotations

from typing import Any, Mapping

from max.spec._launch_governance import CSV_COLUMNS, base_context, item, render_csv, render_markdown, summary

RUNBOOK_OWNERSHIP_PLAN_SCHEMA_VERSION = "max-runbook-ownership-plan/v1"
KIND = "max.runbook_ownership_plan"
RUNBOOK_OWNERSHIP_PLAN_CSV_COLUMNS = CSV_COLUMNS
SECTIONS = ("runbook_inventory", "owners", "escalation_paths", "stale_sections", "review_cadence", "validation_drills", "handoff_evidence", "publication_state")


def generate_runbook_ownership_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    context = base_context(tact_spec)
    runbook = _mapping(context["spec"].get("runbook") or context["spec"].get("runbook_ownership"))
    name = _text(runbook.get("name")) or f"{context['workflow']} runbook"
    owner = _text(runbook.get("owner"))
    stale = _bool(runbook.get("stale_review")) or not _text(runbook.get("last_reviewed"))
    readiness_risk = not owner or stale

    return {
        "schema_version": RUNBOOK_OWNERSHIP_PLAN_SCHEMA_VERSION,
        "kind": KIND,
        "source": context["source"],
        "summary": summary(context, runbook=name, readiness_risk=readiness_risk),
        "runbook_inventory": [
            item("RBK1", "runbook_record", f"Maintain ownership plan for {name}.", owner or "service_owner", evidence=["runbook.name"])
        ],
        "owners": [
            item("OWN1", "primary_owner", f"Primary owner: {owner or 'missing owner'}.", owner or "service_owner", severity="critical" if not owner else "medium", action="Assign a named owner before publication." if not owner else "Confirm backup owner.", evidence=["runbook.owner"])
        ],
        "escalation_paths": [
            item("ESC1", "coverage_path", "Document primary, backup, on-call, and leadership escalation coverage.", "service_owner", evidence=["project.support_context"])
        ],
        "stale_sections": [
            item("STL1", "stale_review", "Review stale troubleshooting, dashboards, permissions, and customer communication sections.", "service_owner", severity="high" if stale else "low", action="Refresh stale sections before handoff." if stale else "Record current review date.", evidence=["runbook.last_reviewed"])
        ],
        "review_cadence": [
            item("CAD1", "scheduled_review", "Set recurring runbook review cadence and ownership reminder.", "service_owner", timing=_text(runbook.get("review_cadence")) or "quarterly", evidence=["runbook.review_cadence"])
        ],
        "validation_drills": [
            item("DRL1", "runbook_drill", "Run a validation drill for alert triage, escalation, mitigation, and customer update steps.", "on_call_owner", evidence=["execution.validation_plan"])
        ],
        "handoff_evidence": [
            item("EV1", "handoff_packet", "Attach owner acknowledgement, drill notes, escalation roster, stale-section fixes, and support handoff.", "release_manager", action="Required for readiness.", evidence=["evidence.references"])
        ],
        "publication_state": [
            item("PUB1", "publish_status", f"Publication status: {_text(runbook.get('publication_status')) or 'draft pending owner review'}.", "service_owner", action="Publish only after owner and stale review risks are closed.", evidence=["runbook.publication_status"])
        ],
        "evidence_references": context["evidence_references"],
    }


def render_runbook_ownership_plan_markdown(plan: dict[str, Any]) -> str:
    return render_markdown(plan, "Runbook Ownership Plan", SECTIONS)


def render_runbook_ownership_plan_csv(plan: dict[str, Any]) -> str:
    return render_csv(plan, SECTIONS)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}
