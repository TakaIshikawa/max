"""Generate deterministic production-readiness exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.production_readiness_exception_plan.v1"
KIND = "max.spec.production_readiness_exception_plan"


def generate_production_readiness_exception_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    unmet = _values(hints.get("unmet_controls"), ["observability sign-off", "rollback rehearsal evidence"])
    controls = _values(hints.get("compensating_controls"), ["daily owner review", "manual rollback checkpoint"])
    launch_blocking = _truthy(hints.get("launch_blocking"))
    high_risk = launch_blocking or compact(hints.get("risk_level")).lower() in {"high", "critical"} or ctx["strictness"] == "strict"
    expiry = compact(hints.get("expiry")) or ("7 days after launch" if high_risk else "30 days after approval")
    approvers = _values(hints.get("approvers"), ["engineering_lead", "product_owner", "risk_owner"] if high_risk else ["engineering_lead", "product_owner"])
    evidence_ids = _evidence_ids(ctx)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, launch_blocking=launch_blocking, exception_risk="high" if high_risk else "standard", expiry=expiry),
        "exception_summary": [
            _item("ES1", "exception_scope", "risk_owner", f"Document production-readiness exception for {ctx['title']}.", "high" if high_risk else "medium", evidence_ids=evidence_ids),
            _item("ES2", "launch_decision", "product_owner", "Launch is blocked until exception approval is complete." if launch_blocking else "Launch may proceed only inside the approved exception constraints.", "critical" if launch_blocking else "medium", evidence_ids=evidence_ids),
        ],
        "unmet_controls": [_item(f"UC{index}", control, "control_owner", f"Track unmet readiness control: {control}.", "high" if high_risk else "medium", evidence_ids=evidence_ids) for index, control in enumerate(unmet, start=1)],
        "compensating_controls": [_item(f"CC{index}", control, "risk_owner", f"Operate compensating control: {control}.", "high" if high_risk else "medium", evidence_ids=evidence_ids) for index, control in enumerate(controls, start=1)],
        "approval_workflow": [_item(f"AW{index}", approver, approver, f"Require approval from {approver} before exception activation.", "high" if high_risk else "medium", timing="before launch", evidence_ids=evidence_ids) for index, approver in enumerate(approvers, start=1)],
        "expiry_and_review": [
            _item("ER1", "exception_expiry", "risk_owner", f"Expire exception by {expiry} unless renewed with fresh evidence.", "high" if high_risk else "medium", timing=expiry, evidence_ids=evidence_ids),
            _item("ER2", "review_cadence", "risk_owner", "Review daily until closure." if high_risk else "Review weekly until closure.", "high" if high_risk else "medium", evidence_ids=evidence_ids),
        ],
        "remediation_plan": [_item("RP1", "close_readiness_gaps", "engineering_owner", "Close every unmet control and attach validation evidence before exception closure.", "high" if high_risk else "medium", evidence_ids=evidence_ids)],
        "launch_constraints": [_item("LC1", "constrained_launch", "release_manager", "Limit launch blast radius and pause expansion while the exception is open." if high_risk else "Do not expand scope beyond approved exception boundaries.", "high" if high_risk else "medium", evidence_ids=evidence_ids)],
        "owner_roles": _owner_roles(ctx),
        "evidence_references": ctx["evidence_references"],
    }


def _owner_roles(ctx: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "risk_owner", "suggested_owner": "risk_owner", "responsibility": "Own exception record, review cadence, and closure decision."},
        {"role": "engineering_owner", "suggested_owner": "engineering_owner", "responsibility": "Remediate unmet controls and provide validation evidence."},
        {"role": "product_owner", "suggested_owner": ctx["buyer"], "responsibility": "Approve launch constraints and customer impact tradeoffs."},
        {"role": "release_manager", "suggested_owner": "release_manager", "responsibility": "Enforce launch gates while the exception is active."},
    ]


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("production_readiness_exception")
    return hints if isinstance(hints, dict) else {}


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(values), key=str.casefold) if values else fallback


def _truthy(value: Any) -> bool:
    return value is True or compact(value).lower() in {"1", "true", "yes", "y", "blocked", "launch-blocking"}


def _item(item_id: str, name: str, owner: str, description: str, severity: str, *, timing: str = "planned", evidence_ids: list[str] | None = None) -> dict[str, Any]:
    return {"id": item_id, "name": name, "owner": owner, "severity": severity, "timing": timing, "description": description, "evidence_reference_ids": evidence_ids or []}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
