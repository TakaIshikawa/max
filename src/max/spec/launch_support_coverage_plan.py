"""Generate deterministic launch support coverage plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, records, row, source_summary, values


SCHEMA_VERSION = "max.spec.launch_support_coverage_plan.v1"
KIND = "max.spec.launch_support_coverage_plan"


def generate_launch_support_coverage_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, hints, evidence_ids = base(spec_like, "launch_support_coverage")
    windows_raw = records(hints.get("support_windows") or hints.get("windows") or spec.get("support_windows"), ["launch day business hours"])
    roles_raw = records(hints.get("staffed_roles") or hints.get("roles") or spec.get("staffed_roles"), ["incident commander", "support lead"])
    uncovered_critical = any((compact(item.get("coverage")).lower() in {"uncovered", "missing"} or compact(item.get("severity")).lower() in {"critical", "high"} and compact(item.get("covered")).lower() == "false") for item in windows_raw)
    missing_escalation = not (hints.get("escalation_paths") or hints.get("escalations") or spec.get("escalation_paths"))
    recommendation = "hold" if uncovered_critical else "conditional" if missing_escalation else "ready"

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, recommendation=recommendation, support_window_count=len(windows_raw), staffed_role_count=len(roles_raw)),
        "support_windows": [row("LSW", index, item["name"], compact(item.get("owner")) or "support_manager", compact(item.get("description")) or f"Cover support window {item['name']}.", evidence_ids, severity=compact(item.get("severity")) or "medium", coverage=compact(item.get("coverage")) or "covered") for index, item in enumerate(windows_raw, start=1)],
        "staffed_roles": [row("LSR", index, item["name"], compact(item.get("owner")) or compact(item.get("person")) or "staffing_owner", f"Staff launch role {item['name']}.", evidence_ids, shift=compact(item.get("shift")) or "launch window") for index, item in enumerate(roles_raw, start=1)],
        "coverage_gaps": [row("LSG", index, item["name"], "support_manager", f"Close coverage gap for {item['name']}.", evidence_ids, severity=compact(item.get("severity")) or "high") for index, item in enumerate(records(hints.get("coverage_gaps"), [] if not uncovered_critical else ["critical support window uncovered"]), start=1)],
        "escalation_paths": [row("LSE", index, item["name"], compact(item.get("owner")) or "missing_escalation_owner", f"Escalate launch support issue through {item['name']}.", evidence_ids) for index, item in enumerate(records(hints.get("escalation_paths") or hints.get("escalations"), ["missing escalation path"] if missing_escalation else []), start=1)],
        "handoff_checkpoints": [row("LSH", index, name, "support_manager", f"Complete handoff checkpoint {name}.", evidence_ids) for index, name in enumerate(values(hints.get("handoff_checkpoints"), ["pre-launch briefing", "post-launch support handoff"]), start=1)],
        "recommendation": recommendation,
        "evidence_references": ctx["evidence_references"],
    }
