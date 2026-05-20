"""Generate deterministic integration backout plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.integration_backout_plan.v1"
KIND = "max.spec.integration_backout_plan"
CRITICALITY_RANK = {"critical": 0, "high": 1, "standard": 2, "medium": 2, "low": 3}


def generate_integration_backout_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    integrations = _integrations(hints.get("integrations") or spec.get("integrations"))
    evidence_ids = _evidence_ids(ctx)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, integration_count=len(integrations), critical_integration_count=sum(1 for item in integrations if item["criticality"] in {"critical", "high"})),
        "integration_inventory": [_inventory(index, item, evidence_ids) for index, item in enumerate(integrations, start=1)],
        "backout_triggers": _triggers(hints, ctx, evidence_ids),
        "backout_steps": _steps(hints, integrations, evidence_ids),
        "reconciliation_checks": _reconciliation(integrations, evidence_ids),
        "communication_owners": _communications(integrations, evidence_ids),
        "validation_checks": _validation(integrations, evidence_ids),
        "evidence_references": ctx["evidence_references"],
    }


def _inventory(index: int, item: dict[str, str], evidence_ids: list[str]) -> dict[str, Any]:
    return {"id": f"INT{index}", **item, "evidence_reference_ids": evidence_ids}


def _integrations(value: Any) -> list[dict[str, str]]:
    raw = [value] if isinstance(value, dict) else value if isinstance(value, list) else string_list(value)
    rows = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            name = compact(item.get("name") or item.get("integration") or item.get("service")) or f"integration {index}"
            rows.append({"name": name, "owner": compact(item.get("owner")) or "integration_owner", "criticality": _criticality(item.get("criticality") or item.get("priority")), "data_sync_direction": compact(item.get("data_sync_direction") or item.get("sync_direction")) or "bidirectional", "manual_fallback": compact(item.get("manual_fallback") or item.get("fallback")) or "manual processing path required"})
        else:
            name = compact(item) or f"integration {index}"
            rows.append({"name": name, "owner": "integration_owner", "criticality": "standard", "data_sync_direction": "bidirectional", "manual_fallback": "manual processing path required"})
    if not rows:
        rows.append({"name": "primary integration", "owner": "integration_owner", "criticality": "standard", "data_sync_direction": "bidirectional", "manual_fallback": "manual processing path required"})
    return sorted(rows, key=lambda row: (CRITICALITY_RANK[row["criticality"]], row["name"].casefold()))


def _triggers(hints: dict[str, Any], ctx: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    values = string_list(hints.get("backout_triggers") or hints.get("triggers")) or ctx["risks"] or ["integration error rate exceeds threshold"]
    return [{"id": f"BT{index}", "trigger": value, "owner": "release_manager", "evidence_reference_ids": evidence_ids} for index, value in enumerate(sorted(values, key=str.casefold), start=1)]


def _steps(hints: dict[str, Any], integrations: list[dict[str, str]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    custom = string_list(hints.get("backout_steps") or hints.get("steps"))
    values = custom or [f"Disable {item['name']} traffic and activate {item['manual_fallback']}." for item in integrations]
    return [{"id": f"BS{index}", "step": value, "owner": "integration_owner", "evidence_reference_ids": evidence_ids} for index, value in enumerate(values, start=1)]


def _reconciliation(integrations: list[dict[str, str]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [{"id": f"RC{index}", "integration": item["name"], "check": f"Reconcile {item['data_sync_direction']} data movement after backout.", "owner": item["owner"], "evidence_reference_ids": evidence_ids} for index, item in enumerate(integrations, start=1)]


def _communications(integrations: list[dict[str, str]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    owners = sorted({item["owner"] for item in integrations} | {"release_manager"})
    return [{"id": f"CO{index}", "owner": owner, "responsibility": "Coordinate integration backout status and stakeholder updates.", "evidence_reference_ids": evidence_ids} for index, owner in enumerate(owners, start=1)]


def _validation(integrations: list[dict[str, str]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [{"id": f"VC{index}", "integration": item["name"], "check": f"Confirm {item['name']} is stable or fully backed out with no queued data loss.", "owner": item["owner"], "evidence_reference_ids": evidence_ids} for index, item in enumerate(integrations, start=1)]


def _criticality(value: Any) -> str:
    text = compact(value).casefold()
    return text if text in CRITICALITY_RANK else "standard"


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("integration_backout")
    return hints if isinstance(hints, dict) else {}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
