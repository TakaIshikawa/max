"""Generate deterministic maintenance window plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.maintenance_window_plan.v1"
MAINTENANCE_WINDOW_PLAN_SCHEMA_VERSION = SCHEMA_VERSION
KIND = "max.spec.maintenance_window_plan"


def generate_maintenance_window_plan(spec_like: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic planning data for a planned maintenance window."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _maintenance_hints(spec)
    evidence_ids = [item["id"] for item in ctx["evidence_references"]]
    strictness = "strict" if hints["customer_impacting"] or hints["downtime_expected"] else ctx["strictness"]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(
            ctx,
            maintenance_strictness=strictness,
            customer_impacting=hints["customer_impacting"],
            downtime_expected=hints["downtime_expected"],
            communication_cadence="high-touch" if strictness == "strict" else "standard",
        ),
        "window_strategy": _window_strategy(ctx, hints, strictness, evidence_ids),
        "impacted_users": _impacted_users(ctx, hints, evidence_ids),
        "communication_timeline": _communication_timeline(strictness, evidence_ids),
        "pre_checks": _pre_checks(ctx, hints, strictness, evidence_ids),
        "execution_steps": _execution_steps(ctx, hints, strictness, evidence_ids),
        "rollback_or_abort_criteria": _rollback_or_abort_criteria(strictness, evidence_ids),
        "post_checks": _post_checks(ctx, hints, strictness, evidence_ids),
        "owner_roles": _owner_roles(ctx),
        "evidence_references": ctx["evidence_references"],
    }


def _maintenance_hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    maintenance = metadata.get("maintenance") if isinstance(metadata.get("maintenance"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    text = " ".join(
        string_list(execution.get("risks"))
        + string_list(metadata.get("risks"))
        + string_list(maintenance.get("risks"))
        + [
            compact(metadata.get("change_type")),
            compact(maintenance.get("impact")),
            compact(maintenance.get("downtime")),
            compact(maintenance.get("window")),
        ]
    ).lower()
    customer_impacting = _truthy(
        maintenance.get("customer_impacting")
        if "customer_impacting" in maintenance
        else metadata.get("customer_impacting")
    ) or any(term in text for term in ("customer-impacting", "customer impacting", "customer impact", "breaking"))
    downtime_expected = _truthy(
        maintenance.get("downtime_expected")
        if "downtime_expected" in maintenance
        else metadata.get("downtime_expected")
    ) or any(term in text for term in ("downtime", "unavailable", "outage", "maintenance mode"))

    return {
        "requested_window": compact(maintenance.get("window") or metadata.get("maintenance_window")) or "lowest-usage staffed window",
        "duration": compact(maintenance.get("duration") or metadata.get("duration")) or "60 minutes",
        "timezone": compact(maintenance.get("timezone") or metadata.get("timezone")) or "local business timezone",
        "customer_impacting": customer_impacting,
        "downtime_expected": downtime_expected,
        "impacted_users": string_list(
            maintenance.get("impacted_users")
            or metadata.get("impacted_users")
            or project.get("target_users")
            or project.get("specific_user")
        ),
        "systems": string_list(maintenance.get("systems") or metadata.get("systems") or execution.get("mvp_scope")),
    }


def _window_strategy(
    ctx: dict[str, Any], hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> dict[str, Any]:
    return {
        "id": "WS1",
        "name": "Planned staffed maintenance window",
        "owner": "release_owner",
        "strictness": strictness,
        "window": hints["requested_window"],
        "duration": hints["duration"],
        "timezone": hints["timezone"],
        "strategy": f"Schedule {ctx['workflow_context']} maintenance during a staffed low-usage period with rollback owner present.",
        "customer_impact": "customer-visible downtime expected" if hints["downtime_expected"] else ("customer-visible degradation possible" if hints["customer_impacting"] else "no planned customer-visible downtime"),
        "evidence_reference_ids": evidence_ids,
    }


def _impacted_users(
    ctx: dict[str, Any], hints: dict[str, Any], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    users = hints["impacted_users"] or [ctx["target_user"]]
    return [
        {
            "id": f"IU{index}",
            "segment": user,
            "impact": "temporary downtime or degraded workflow" if hints["downtime_expected"] else "possible delayed workflow completion",
            "support_path": "staffed support channel with maintenance status and escalation owner",
            "evidence_reference_ids": evidence_ids,
        }
        for index, user in enumerate(users, start=1)
    ]


def _communication_timeline(strictness: str, evidence_ids: list[str]) -> list[dict[str, Any]]:
    milestones = (
        [
            ("CT1", "T-14 days", "announce maintenance scope, expected impact, and support path"),
            ("CT2", "T-3 days", "send reminder with exact window and customer action needed"),
            ("CT3", "T-1 hour", "post final reminder and live status channel"),
            ("CT4", "T+30 minutes", "confirm completion, residual impact, and support follow-up"),
        ]
        if strictness == "strict"
        else [
            ("CT1", "T-7 days", "announce planned maintenance window and support path"),
            ("CT2", "T-1 hour", "post start reminder to internal and customer-facing channels"),
            ("CT3", "T+30 minutes", "confirm completion and support path"),
        ]
    )
    return [
        {
            "id": item_id,
            "milestone": milestone,
            "owner": "communications_owner" if item_id != "CT3" else "support_owner",
            "message": message,
            "evidence_reference_ids": evidence_ids,
        }
        for item_id, milestone, message in milestones
    ]


def _pre_checks(
    ctx: dict[str, Any], hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    systems = ", ".join(hints["systems"] or ctx["mvp_scope"] or ["target systems"])
    checks = [
        _check("PC1", "Rollback package ready", "release_owner", "rollback artifact, owner, and decision channel are confirmed", evidence_ids),
        _check("PC2", "Backup and restore point verified", "data_owner", "backup, snapshot, or reversible migration checkpoint completed before start", evidence_ids),
        _check("PC3", "Dependency and telemetry health", "technical_owner", f"{systems} telemetry is healthy and alert routing is active", evidence_ids),
    ]
    if strictness == "strict":
        checks.append(
            _check("PC4", "Customer communications sent", "communications_owner", "all required customer-impact notices are sent and status page is ready", evidence_ids)
        )
    return checks


def _execution_steps(
    ctx: dict[str, Any], hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        _step("ES1", "Open maintenance window", "release_owner", f"Start staffed window for {ctx['workflow_context']} and announce status.", "planned start time", evidence_ids),
        _step("ES2", "Enable protection controls", "technical_owner", "pause conflicting jobs, enable maintenance mode if needed, and confirm write-drain state.", "before change execution", evidence_ids),
        _step("ES3", "Execute maintenance change", "technical_owner", f"Apply the approved change within {hints['duration']} and record timestamps.", "during window", evidence_ids),
        _step("ES4", "Validate or abort", "qa_owner", "run smoke checks and compare telemetry against abort criteria before reopening traffic.", "before customer traffic resumes" if strictness == "strict" else "before closeout", evidence_ids),
    ]


def _rollback_or_abort_criteria(strictness: str, evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [
        _criterion("AC1", "Pre-check failure", "release_owner", "required backup, rollback package, owner coverage, or communication checkpoint is missing", "delay or abort before customer impact", evidence_ids),
        _criterion("AC2", "Error budget breach", "incident_commander", "critical workflow errors exceed baseline or p95 latency remains above target for two checks", "rollback immediately" if strictness == "strict" else "pause and decide rollback", evidence_ids),
        _criterion("AC3", "Window overrun", "release_owner", "remaining work cannot complete with validation inside the approved window", "rollback or extend only with sponsor approval", evidence_ids),
    ]


def _post_checks(
    ctx: dict[str, Any], hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    cadence = "15 minutes for first hour, then hourly through next business day" if strictness == "strict" else "hourly through the staffed support window"
    return [
        _check("PO1", "Workflow smoke test", "qa_owner", f"confirm {ctx['workflow_context']} completes for impacted users", evidence_ids),
        _check("PO2", "Telemetry review", "technical_owner", f"monitor errors, latency, queue depth, and saturation {cadence}", evidence_ids),
        _check("PO3", "Customer/support closeout", "support_owner", "confirm no unresolved tickets or customer-facing status updates remain open", evidence_ids),
    ]


def _owner_roles(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"role": "release_owner", "suggested_owner": "release_owner", "responsibility": "Own window approval, go/no-go, timeline, and closeout evidence."},
        {"role": "technical_owner", "suggested_owner": "technical_owner", "responsibility": "Execute change, monitor systems, and prepare rollback controls."},
        {"role": "communications_owner", "suggested_owner": ctx["buyer"], "responsibility": "Own customer and stakeholder maintenance messaging."},
        {"role": "support_owner", "suggested_owner": "support_owner", "responsibility": "Staff support path, escalation intake, and post-window customer follow-up."},
    ]


def _check(item_id: str, name: str, owner: str, description: str, evidence_ids: list[str]) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "owner": owner,
        "description": description,
        "evidence_reference_ids": evidence_ids,
    }


def _step(
    item_id: str,
    name: str,
    owner: str,
    action: str,
    timing: str,
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "owner": owner,
        "action": action,
        "timing": timing,
        "evidence_reference_ids": evidence_ids,
    }


def _criterion(
    item_id: str,
    name: str,
    owner: str,
    condition: str,
    action: str,
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "owner": owner,
        "condition": condition,
        "action": action,
        "evidence_reference_ids": evidence_ids,
    }


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return compact(value).lower() in {"1", "true", "yes", "y", "customer-impacting", "downtime"}
