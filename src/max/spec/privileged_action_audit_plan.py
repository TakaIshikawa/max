"""Generate deterministic privileged action audit plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import named, section
from max.spec._planning_common import compact, string_list
from max.spec._review_plan_common import base, row, source_summary, unique_records

SCHEMA_VERSION = "max.spec.privileged_action_audit_plan.v1"
KIND = "max.spec.privileged_action_audit_plan"
REQUIRED_LOG_FIELDS = ["actor", "actor_role", "action", "target", "timestamp", "source_ip", "ticket_id", "outcome"]


def generate_privileged_action_audit_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "privileged_action_audit")
    actions = unique_records(named(hints.get("privileged_actions") or hints.get("actions"), ("action", "name")), [{"action": "privileged production action"}])
    action_rows = [_action_row(record, index, evidence_ids) for index, record in enumerate(actions, start=1)]
    blockers = [blocker for action in action_rows for blocker in _blockers(action, evidence_ids)]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, privileged_action_count=len(action_rows), blocker_count=len(blockers)),
        "privileged_actions": action_rows,
        "audit_log_fields": REQUIRED_LOG_FIELDS,
        "anomaly_checks": section(hints, ("anomaly_checks", "checks"), "PGA", "security_owner", "Run privileged action anomaly check", evidence_ids, ["off-hours access, unusual target, failed action spike, and missing ticket"]),
        "review_cadence": section(hints, ("review_cadence", "reviews"), "PGR", "security_owner", "Review privileged actions", evidence_ids, ["daily high-risk review and weekly aggregate review"]),
        "escalation_path": section(hints, ("escalation_path", "escalations"), "PGE", "security_owner", "Escalate privileged action anomaly", evidence_ids, ["security incident commander, system owner, legal/privacy if data exposure is suspected"]),
        "blockers": blockers,
        "evidence_references": ctx["evidence_references"],
    }


def _action_row(record: dict[str, Any], index: int, evidence_ids: list[str]) -> dict[str, Any]:
    fields = sorted(set(string_list(record.get("log_fields"))) | set(REQUIRED_LOG_FIELDS), key=lambda item: (REQUIRED_LOG_FIELDS.index(item) if item in REQUIRED_LOG_FIELDS else len(REQUIRED_LOG_FIELDS), item))
    return row("PGI", index, compact(record.get("action") or record.get("name")) or "privileged production action", compact(record.get("owner")) or "security_owner", "Verify privileged action audit coverage.", evidence_ids, actor_role=compact(record.get("actor_role") or record.get("role")) or "missing", log_destination=compact(record.get("log_destination") or record.get("destination")) or "missing", retention_requirement=compact(record.get("retention_requirement") or record.get("retention")) or "missing", required_log_fields=fields)


def _blockers(action: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    required = (("actor_role", "missing actor role"), ("log_destination", "missing log destination"), ("retention_requirement", "missing retention requirement"))
    return [row("PGB", index, f"{label} for {action['name']}", "security_owner", f"Resolve {label} before audit plan approval.", evidence_ids, severity="high", action=action["name"]) for index, (key, label) in enumerate(required, start=1) if action[key] in {"", "missing", "unknown"}]
