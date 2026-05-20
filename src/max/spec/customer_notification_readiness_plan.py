"""Generate deterministic customer notification readiness plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.customer_notification_readiness_plan.v1"
KIND = "max.spec.customer_notification_readiness_plan"


def generate_customer_notification_readiness_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    evidence_ids = _evidence_ids(ctx)
    audiences = _values(hints.get("audience_segments") or hints.get("audiences"), [ctx["target_user"]])
    triggers = _records(hints.get("notification_triggers") or hints.get("triggers"), "trigger", [{"name": "material customer impact", "owner": "communications_owner", "description": f"Notify when {ctx['workflow_context']} materially changes."}])
    channels = _values(hints.get("channels"), ["email", "status page" if ctx["strictness"] == "strict" else "in-app message"])
    gates = _records(hints.get("approval_gates") or hints.get("approvals"), "gate", [{"name": "message approval", "owner": compact(hints.get("message_owner")) or "communications_owner", "description": "Approve audience, channel, timing, and final copy."}])
    timing = _records(hints.get("send_timing") or hints.get("timing_plan"), "timing", [{"name": "pre-send readiness", "owner": "communications_owner", "description": "Send after approval gate and support briefing are complete."}])
    localization = _values(hints.get("localization_needs") or hints.get("locales"), ["default locale"])
    checks = _records(hints.get("validation_checks"), "check", [{"name": "notification dry run", "owner": "communications_owner", "description": "Validate audience list, template rendering, links, and approvals."}])

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, audience_count=len(audiences), channel_count=len(channels)),
        "audience_segments": [_named("AUD", index, audience, "customer_success_owner", evidence_ids) for index, audience in enumerate(audiences, start=1)],
        "notification_triggers": [_item("TRG", index, row, evidence_ids) for index, row in enumerate(triggers, start=1)],
        "channels": [_named("CH", index, channel, "communications_owner", evidence_ids) for index, channel in enumerate(channels, start=1)],
        "approval_gates": [_item("GATE", index, row, evidence_ids) for index, row in enumerate(gates, start=1)],
        "timing_plan": [_item("TIME", index, row, evidence_ids) for index, row in enumerate(timing, start=1)],
        "localization_needs": [_named("LOC", index, locale, "localization_owner", evidence_ids) for index, locale in enumerate(localization, start=1)],
        "validation_checks": [_item("VC", index, row, evidence_ids) for index, row in enumerate(checks, start=1)],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("customer_notification_readiness")
    return hints if isinstance(hints, dict) else {}


def _records(value: Any, default_name: str, fallback: list[dict[str, str]]) -> list[dict[str, str]]:
    raw = [value] if isinstance(value, dict) else value if isinstance(value, list) else string_list(value)
    rows = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            rows.append({"name": compact(item.get("name") or item.get("trigger") or item.get("gate") or item.get("timing") or item.get("check")) or f"{default_name} {index}", "owner": compact(item.get("owner")), "description": compact(item.get("description") or item.get("message"))})
        else:
            rows.append({"name": compact(item) or f"{default_name} {index}", "owner": "", "description": ""})
    return sorted(rows or fallback, key=lambda row: row["name"].casefold())


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(values), key=str.casefold) if values else fallback


def _named(prefix: str, index: int, name: str, owner: str, evidence_ids: list[str]) -> dict[str, Any]:
    return {"id": f"{prefix}{index}", "name": name, "owner": owner, "evidence_reference_ids": evidence_ids}


def _item(prefix: str, index: int, row: dict[str, str], evidence_ids: list[str]) -> dict[str, Any]:
    return {"id": f"{prefix}{index}", "name": row["name"], "owner": row["owner"] or "communications_owner", "description": row["description"] or row["name"], "evidence_reference_ids": evidence_ids}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
