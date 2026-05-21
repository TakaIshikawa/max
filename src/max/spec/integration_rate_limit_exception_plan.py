"""Generate deterministic integration rate limit exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.integration_rate_limit_exception_plan.v1"
KIND = "max.spec.integration_rate_limit_exception_plan"


def generate_integration_rate_limit_exception_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "integration_rate_limit_exception")
    exceptions = unique_records(hints.get("integrations") or hints.get("exceptions"), [{"name": "temporary rate limit exception", "owner": "platform_owner", "severity": "medium", "duration": "30 days"}])
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, exception_count=len(exceptions)),
        "rate_limit_exceptions": [_item("IRL", index, item, "platform_owner", evidence_ids) for index, item in enumerate(exceptions, start=1)],
        "consumer_impact": _section(hints, ("consumers", "consumer_impact"), "IRC", "customer_success_owner", "Confirm consumer impact", evidence_ids, ["affected consumer inventory"]),
        "mitigation_controls": _section(hints, ("mitigation_controls", "controls"), "IRM", "platform_owner", "Operate mitigation control", evidence_ids, ["burst and abuse monitoring"]),
        "approval_gates": _section(hints, ("approval_gates", "approvals"), "IRA", "approval_owner", "Capture exception approval", evidence_ids, ["platform approval"]),
        "monitoring": _section(hints, ("monitoring", "monitors"), "IRO", "sre_owner", "Monitor exception usage", evidence_ids, ["rate-limit saturation dashboard"]),
        "rollback_criteria": _section(hints, ("rollback_criteria", "rollback"), "IRR", "platform_owner", "Define rollback criteria", evidence_ids, ["restore standard limit"]),
        "evidence_references": ctx["evidence_references"],
    }


def _section(hints: dict[str, Any], keys: tuple[str, ...], prefix: str, owner: str, label: str, evidence_ids: list[str], fallback: list[Any]) -> list[dict[str, Any]]:
    value = next((hints[key] for key in keys if key in hints), None)
    return [_item(prefix, index, item, owner, evidence_ids, label) for index, item in enumerate(unique_records(value, fallback), start=1)]


def _item(prefix: str, index: int, item: dict[str, Any], owner: str, evidence_ids: list[str], label: str = "Review integration rate limit exception") -> dict[str, Any]:
    name = compact(item.get("name") or item.get("integration"))
    return row(prefix, index, name, compact(item.get("owner")) or owner, compact(item.get("description")) or f"{label}: {name}.", evidence_ids, severity=compact(item.get("severity")) or "medium", status=compact(item.get("status") or item.get("due_status")) or "open", current_limit=compact(item.get("current_limit")), requested_limit=compact(item.get("requested_limit")), duration=compact(item.get("duration")) or "30 days")
