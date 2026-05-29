"""Generate deterministic spec approval escalation plans."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from max.spec._compact_plan_common import item, section
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.spec_approval_escalation_plan.v1"
KIND = "max.spec.spec_approval_escalation_plan"


def generate_spec_approval_escalation_plan(spec_like: Any, *, now: str = "2026-05-29T00:00:00+00:00") -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "spec_approval_escalation")
    now_dt = _dt(now)
    specs = unique_records(hints.get("blocked_specs") or hints.get("approvals") or hints.get("specs"), [{"name": "pending spec approval", "owner": "approval_owner"}])
    blocked = [_blocked_item(i, r, evidence_ids, now_dt) for i, r in enumerate(specs, 1)]
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "source": ctx["source"], "title": "Spec Approval Escalation Plan", "summary": source_summary(ctx, blocked_spec_count=len(blocked), overdue_count=sum(1 for r in blocked if r["overdue_hours"] > 0)), "blocked_specs": blocked, "approval_stages": section(hints, ("approval_stages", "stages"), "SAES", "approval_owner", "Review approval stage", evidence_ids, ["review, security, product, and release approval stages"]), "escalation_path": section(hints, ("escalation_path", "escalations"), "SAEP", "program_owner", "Escalate blocked approval", evidence_ids, ["reviewer, backup reviewer, approval lead, and decision owner"]), "decision_sla": section(hints, ("decision_sla", "sla"), "SAED", "program_owner", "Set approval decision SLA", evidence_ids, ["24 hour response and 48 hour decision for overdue specs"]), "risk_assessment": section(hints, ("risk_assessment", "risks"), "SAER", "program_owner", "Assess blocked approval risk", evidence_ids, ["release delay, compliance exposure, and customer commitment risk"]), "communication_steps": section(hints, ("communication_steps", "communications"), "SAEC", "program_owner", "Communicate approval escalation", evidence_ids, ["notify assignee, requester, release owner, and escalation channel"]), "fallback_decisions": section(hints, ("fallback_decisions", "fallback"), "SAEF", "program_owner", "Define fallback approval decision", evidence_ids, ["defer scope, appoint alternate approver, or hold release"]), "evidence_references": ctx["evidence_references"]}


def _blocked_item(index: int, record: dict[str, Any], evidence_ids: list[str], now: datetime) -> dict[str, Any]:
    data = item("SAEB", index, record, "approval_owner", evidence_ids, "Escalate blocked spec approval", extra_keys=("assignee", "stage", "status", "due_at"))
    due = _dt(record.get("due_at") or record.get("deadline"))
    data["assignee"] = data.get("assignee") or "unassigned"
    data["overdue_hours"] = max(int((now - due).total_seconds() // 3600), 0) if due else 0
    data["severity"] = "high" if data["overdue_hours"] else "medium"
    return data


def _dt(value: Any) -> datetime | None:
    text = str(value or "").replace("Z", "+00:00").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime(2026, 5, 29, tzinfo=timezone.utc)
