"""Generate deterministic go-live decision records for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.go_live_decision_record.v1"
KIND = "max.spec.go_live_decision_record"


def generate_go_live_decision_record(spec_like: Any) -> dict[str, Any]:
    """Return a deterministic go-live decision record."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec, "go_live_decision")
    gates = _gates(hints.get("launch_criteria") or spec.get("launch_criteria"))
    risks = _risks(hints.get("risks") or spec.get("risks") or ctx["risks"])
    approvals = _approvals(hints.get("approvals") or spec.get("approvals"))
    rollback_ready = _truthy(hints.get("rollback_ready") if "rollback_ready" in hints else spec.get("rollback_ready"))
    exceptions = _values(hints.get("open_exceptions") or spec.get("open_exceptions"), [])
    recommendation = _recommendation(gates, risks, approvals, rollback_ready, exceptions)
    evidence_ids = _evidence_ids(ctx)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, recommendation=recommendation, unmet_gate_count=sum(1 for gate in gates if not gate["met"]), open_exception_count=len(exceptions)),
        "recommendation": recommendation,
        "rationale": _rationale(recommendation, gates, risks, approvals, rollback_ready, exceptions),
        "decision_inputs": _decision_inputs(gates, risks, rollback_ready, exceptions, evidence_ids),
        "approvers": approvals,
        "conditions": _conditions(gates, risks, approvals, rollback_ready, exceptions, evidence_ids),
        "follow_ups": _follow_ups(exceptions, risks, evidence_ids),
        "evidence_references": ctx["evidence_references"],
    }


def _recommendation(
    gates: list[dict[str, Any]], risks: list[dict[str, str]], approvals: list[dict[str, Any]], rollback_ready: bool, exceptions: list[str]
) -> str:
    has_blocking_risk = any(risk["blocking"] for risk in risks)
    has_unmet_gate = any(not gate["met"] for gate in gates)
    missing_approval = any(not approval["approved"] for approval in approvals)
    if has_blocking_risk or (has_unmet_gate and not exceptions):
        return "hold"
    if has_unmet_gate or missing_approval or not rollback_ready or exceptions:
        return "conditional"
    return "approve"


def _rationale(
    recommendation: str,
    gates: list[dict[str, Any]],
    risks: list[dict[str, str]],
    approvals: list[dict[str, Any]],
    rollback_ready: bool,
    exceptions: list[str],
) -> list[str]:
    reasons = [f"Recommendation is {recommendation}."]
    if all(gate["met"] for gate in gates):
        reasons.append("All launch criteria are met.")
    else:
        reasons.append("One or more launch criteria remain unmet.")
    if any(risk["blocking"] for risk in risks):
        reasons.append("Blocking risks are unresolved.")
    if not all(approval["approved"] for approval in approvals):
        reasons.append("Required approvals are still pending.")
    if not rollback_ready:
        reasons.append("Rollback posture is not yet ready.")
    if exceptions:
        reasons.append("Open exceptions must be accepted or closed.")
    return reasons


def _decision_inputs(
    gates: list[dict[str, Any]], risks: list[dict[str, str]], rollback_ready: bool, exceptions: list[str], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        {"id": "DI1", "type": "launch_criteria", "items": gates, "evidence_reference_ids": evidence_ids},
        {"id": "DI2", "type": "risks", "items": risks, "evidence_reference_ids": evidence_ids},
        {"id": "DI3", "type": "rollback_posture", "ready": rollback_ready, "evidence_reference_ids": evidence_ids},
        {"id": "DI4", "type": "open_exceptions", "items": exceptions, "evidence_reference_ids": evidence_ids},
    ]


def _conditions(
    gates: list[dict[str, Any]],
    risks: list[dict[str, str]],
    approvals: list[dict[str, Any]],
    rollback_ready: bool,
    exceptions: list[str],
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    conditions: list[dict[str, Any]] = []
    for gate in gates:
        if not gate["met"]:
            conditions.append({"id": f"COND{len(conditions) + 1}", "type": "unmet_gate", "owner": gate["owner"], "condition": f"Meet launch criterion: {gate['name']}", "evidence_reference_ids": evidence_ids})
    for risk in risks:
        if risk["blocking"]:
            conditions.append({"id": f"COND{len(conditions) + 1}", "type": "blocking_risk", "owner": "risk_owner", "condition": f"Resolve blocking risk: {risk['name']}", "evidence_reference_ids": evidence_ids})
    for approval in approvals:
        if not approval["approved"]:
            conditions.append({"id": f"COND{len(conditions) + 1}", "type": "pending_approval", "owner": approval["owner"], "condition": f"Collect approval from {approval['role']}", "evidence_reference_ids": evidence_ids})
    if not rollback_ready:
        conditions.append({"id": f"COND{len(conditions) + 1}", "type": "rollback_readiness", "owner": "release_manager", "condition": "Confirm rollback plan, owner, trigger, and rehearsal evidence.", "evidence_reference_ids": evidence_ids})
    for exception in exceptions:
        conditions.append({"id": f"COND{len(conditions) + 1}", "type": "open_exception", "owner": "release_manager", "condition": f"Accept or close exception: {exception}", "evidence_reference_ids": evidence_ids})
    return conditions


def _follow_ups(exceptions: list[str], risks: list[dict[str, str]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    values = exceptions + [risk["name"] for risk in risks if not risk["blocking"]]
    return [
        {"id": f"FU{index}", "owner": "release_manager", "action": f"Track deferred follow-up: {value}", "evidence_reference_ids": evidence_ids}
        for index, value in enumerate(values, start=1)
    ]


def _gates(value: Any) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else []
    gates: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            gates.append({"id": f"LC{index}", "name": compact(item.get("name") or item.get("criterion")) or f"criterion {index}", "met": _truthy(item.get("met") if "met" in item else item.get("status") == "met"), "owner": compact(item.get("owner")) or "release_manager"})
        else:
            gates.append({"id": f"LC{index}", "name": compact(item) or f"criterion {index}", "met": True, "owner": "release_manager"})
    return gates or [{"id": "LC1", "name": "launch readiness reviewed", "met": True, "owner": "release_manager"}]


def _risks(value: Any) -> list[dict[str, str]]:
    raw = value if isinstance(value, list) else string_list(value)
    risks: list[dict[str, str]] = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            name = compact(item.get("name") or item.get("risk") or item.get("description")) or f"risk {index}"
            blocking = _truthy(item.get("blocking") or item.get("launch_blocking"))
        else:
            name = compact(item) or f"risk {index}"
            blocking = any(term in name.casefold() for term in ("blocking", "outage", "data loss", "security"))
        risks.append({"id": f"RISK{index}", "name": name, "blocking": blocking})
    return risks


def _approvals(value: Any) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else []
    approvals: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            approvals.append({"id": f"APP{index}", "role": compact(item.get("role")) or f"approver {index}", "owner": compact(item.get("owner")) or "approval_owner", "approved": _truthy(item.get("approved") if "approved" in item else item.get("status") == "approved")})
    return approvals or [{"id": "APP1", "role": "release approver", "owner": "release_manager", "approved": True}]


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(values), key=str.casefold) if values else fallback


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return compact(value).casefold() in {"1", "true", "yes", "y", "approved", "met", "ready"}


def _hints(spec: dict[str, Any], key: str) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get(key)
    return hints if isinstance(hints, dict) else {}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
