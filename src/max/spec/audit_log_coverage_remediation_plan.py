"""Generate deterministic audit log coverage remediation plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.audit_log_coverage_remediation_plan.v1"
KIND = "max.spec.audit_log_coverage_remediation_plan"


def generate_audit_log_coverage_remediation_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    gaps = _gaps(hints.get("gaps") or hints.get("coverage_gaps"))
    refs = [item["id"] for item in ctx["evidence_references"]]
    blockers = [gap for gap in gaps if gap["critical"] or gap["retention_blocker"] or not gap["owner"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, gap_count=len(gaps), blocker_count=len(blockers)),
        "coverage_gaps_by_system": [_row("ALC", i, f"{gap['system']} - {gap['event_category']}", gap["owner"] or "logging_owner", f"Close audit-log gap for {gap['event_category']} in {gap['system']}.", refs, severity="high" if gap["critical"] else "medium", missing_fields=gap["missing_fields"], retention_period=gap["retention_period"]) for i, gap in enumerate(gaps, 1)],
        "critical_actions": [_row("ALB", i, f"{gap['system']} - {gap['event_category']}", gap["owner"] or "logging_owner", "Blocker: critical event missing, insufficient retention, or owner missing.", refs, status="blocked") for i, gap in enumerate(blockers, 1)],
        "owner_follow_up": [_row("ALO", i, gap["system"], gap["owner"] or "logging_owner", f"Assign owner and delivery date for {gap['event_category']}.", refs) for i, gap in enumerate(gaps, 1)],
        "validation_evidence": [_row("ALV", i, f"{gap['system']} - {gap['event_category']}", gap["owner"] or "audit_owner", f"Capture validation evidence: {gap['validation_evidence']}.", refs) for i, gap in enumerate(gaps, 1)],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    value = metadata.get("audit_log_coverage_remediation")
    return value if isinstance(value, dict) else {}


def _gaps(value: Any) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else []
    if not raw:
        raise ValueError("audit_log_coverage_remediation requires coverage gaps")
    gaps = []
    for index, item in enumerate(raw, 1):
        item = item if isinstance(item, dict) else {"event_category": item}
        required = compact(item.get("required_retention") or item.get("retention_required"))
        current = compact(item.get("retention_period") or item.get("current_retention"))
        retention_blocker = bool(required and current and required != current)
        critical = compact(item.get("critical")).casefold() in {"true", "yes", "critical", "1"} or compact(item.get("severity")).casefold() == "critical"
        gaps.append({"system": compact(item.get("system")) or f"system {index}", "event_category": compact(item.get("event_category") or item.get("category")) or "audit event", "required_controls": ", ".join(string_list(item.get("required_controls"))) or "audit logging", "current_coverage": compact(item.get("current_coverage")) or "missing", "missing_fields": ", ".join(string_list(item.get("missing_fields"))), "retention_period": current or "missing", "owner": compact(item.get("owner")), "validation_evidence": compact(item.get("validation_evidence")) or "sample log evidence", "critical": critical, "retention_blocker": retention_blocker})
    return sorted(gaps, key=lambda item: (item["system"].casefold(), item["event_category"].casefold()))


def _row(prefix: str, index: int, name: str, owner: str, description: str, refs: list[str], **extra: Any) -> dict[str, Any]:
    data = {"id": f"{prefix}{index}", "name": name, "owner": owner, "description": description, "evidence_reference_ids": refs}
    data.update({key: value for key, value in extra.items() if value not in ("", None)})
    return data
