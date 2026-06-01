"""Generate deterministic subprocessor change notification plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.subprocessor_change_notification_plan.v1"
KIND = "max.spec.subprocessor_change_notification_plan"


def generate_subprocessor_change_notification_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    changes = _changes(hints.get("subprocessors") or hints.get("changes"))
    refs = [item["id"] for item in ctx["evidence_references"]]
    escalations = [change for change in changes if change["short_notice"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, change_count=len(changes), escalation_count=len(escalations)),
        "change_inventory": [_row("SCN", i, change["name"], "privacy_owner", f"{change['change_type']} subprocessor for {change['products']}.", refs, regions=change["regions"], data_categories=change["data_categories"], notice_window=change["notice_window"]) for i, change in enumerate(changes, 1)],
        "customer_notice_requirements": [_row("SCC", i, change["name"], "customer_owner", f"Notify affected customers for {change['products']} in {change['regions']}.", refs) for i, change in enumerate(changes, 1)],
        "escalation_actions": [_row("SCE", i, change["name"], "legal_owner", f"Escalate short or expired notice window: {change['notice_window']}.", refs, status="escalated") for i, change in enumerate(escalations, 1)],
        "legal_review": [_row("SCL", 1, "Legal review", "legal_owner", "Review contractual notice, objection rights, and regional requirements.", refs)],
        "objection_handling": [_row("SCO", 1, "Customer objection handling", "customer_owner", "Triage objections, document responses, and block rollout where required.", refs)],
        "rollout_gates": [_row("SCR", 1, "Rollout gate", "privacy_owner", "Proceed only after notice, legal review, objections, and escalations are resolved.", refs)],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    value = metadata.get("subprocessor_change_notification")
    return value if isinstance(value, dict) else {}


def _changes(value: Any) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else []
    if not raw:
        raise ValueError("subprocessor_change_notification requires subprocessors")
    changes = []
    for index, item in enumerate(raw, 1):
        item = item if isinstance(item, dict) else {"name": item}
        name = compact(item.get("name") or item.get("subprocessor")) or f"subprocessor {index}"
        notice = compact(item.get("notice_window")) or "missing"
        notice_text = notice.casefold()
        short = "expired" in notice_text or "short" in notice_text or notice_text in {"0 days", "0 day", "7 days", "7 day", "missing"}
        changes.append({"name": name, "change_type": compact(item.get("change_type") or item.get("type")) or "changed", "products": ", ".join(string_list(item.get("products") or item.get("affected_products"))) or "affected products", "regions": ", ".join(string_list(item.get("regions"))) or "all regions", "data_categories": ", ".join(string_list(item.get("data_categories"))) or "customer data", "notice_window": notice, "short_notice": short})
    return sorted(changes, key=lambda item: (not item["short_notice"], item["name"].casefold()))


def _row(prefix: str, index: int, name: str, owner: str, description: str, refs: list[str], **extra: Any) -> dict[str, Any]:
    data = {"id": f"{prefix}{index}", "name": name, "owner": owner, "description": description, "evidence_reference_ids": refs}
    data.update({key: value for key, value in extra.items() if value not in ("", None)})
    return data
