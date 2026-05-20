"""Generate deterministic incident escalation readiness plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.incident_escalation_readiness_plan.v1"
KIND = "max.spec.incident_escalation_readiness_plan"


def generate_incident_escalation_readiness_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    evidence_ids = _evidence_ids(ctx)
    tiers = _records(
        hints.get("escalation_tiers") or hints.get("tiers"),
        "tier",
        [
            {"name": "technical triage", "owner": "incident_commander", "description": f"Stabilize {ctx['workflow_context']} incidents."},
            {"name": "executive escalation", "owner": ctx["buyer"], "description": "Escalate customer, data, or availability risk."},
        ],
    )
    triggers = _records(
        hints.get("trigger_conditions") or hints.get("triggers"),
        "trigger",
        [{"name": "customer-impacting incident", "owner": "incident_commander", "description": f"Any high-risk issue affecting {ctx['target_user']}."}],
    )
    channels = _values(hints.get("channels") or hints.get("communication_channels"), ["incident bridge", "status channel"])
    targets = _records(
        hints.get("response_targets") or hints.get("targets"),
        "target",
        [{"name": "acknowledgement", "owner": "incident_commander", "description": "Acknowledge escalation within 15 minutes." if ctx["strictness"] == "strict" else "Acknowledge escalation within 30 minutes."}],
    )
    checks = _records(
        hints.get("validation_checks"),
        "check",
        [{"name": "dry run escalation path", "owner": "incident_commander", "description": "Confirm owners, bridge, and update cadence before launch."}],
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, tier_count=len(tiers), trigger_count=len(triggers), channel_count=len(channels)),
        "escalation_tiers": [_item("TIER", index, row, evidence_ids) for index, row in enumerate(tiers, start=1)],
        "trigger_conditions": [_item("TRG", index, row, evidence_ids) for index, row in enumerate(triggers, start=1)],
        "communication_channels": [
            {"id": f"CH{index}", "channel": channel, "owner": compact(hints.get("channel_owner")) or "communications_owner", "evidence_reference_ids": evidence_ids}
            for index, channel in enumerate(channels, start=1)
        ],
        "response_targets": [_item("RT", index, row, evidence_ids) for index, row in enumerate(targets, start=1)],
        "validation_checks": [_item("VC", index, row, evidence_ids) for index, row in enumerate(checks, start=1)],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("incident_escalation_readiness")
    return hints if isinstance(hints, dict) else {}


def _records(value: Any, default_name: str, fallback: list[dict[str, str]]) -> list[dict[str, str]]:
    raw = [value] if isinstance(value, dict) else value if isinstance(value, list) else string_list(value)
    rows: list[dict[str, str]] = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            rows.append(
                {
                    "name": compact(item.get("name") or item.get("tier") or item.get("condition") or item.get("target") or item.get("check")) or f"{default_name} {index}",
                    "owner": compact(item.get("owner")),
                    "description": compact(item.get("description") or item.get("condition") or item.get("target")),
                    "timing": compact(item.get("timing") or item.get("target_time") or item.get("response_time")),
                }
            )
        else:
            name = compact(item) or f"{default_name} {index}"
            rows.append({"name": name, "owner": "", "description": "", "timing": ""})
    return sorted(rows or fallback, key=lambda row: row["name"].casefold())


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(values), key=str.casefold) if values else fallback


def _item(prefix: str, index: int, row: dict[str, str], evidence_ids: list[str]) -> dict[str, Any]:
    return {
        "id": f"{prefix}{index}",
        "name": row["name"],
        "owner": row["owner"] or "incident_commander",
        "description": row["description"] or row["name"],
        "timing": row.get("timing") or "planned",
        "evidence_reference_ids": evidence_ids,
    }


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
