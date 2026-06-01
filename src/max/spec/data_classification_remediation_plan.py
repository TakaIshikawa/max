"""Generate deterministic data classification remediation plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.data_classification_remediation_plan.v1"
KIND = "max.spec.data_classification_remediation_plan"
RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def generate_data_classification_remediation_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    items = _items(hints.get("items") or hints.get("misclassifications"))
    refs = [item["id"] for item in ctx["evidence_references"]]
    ownerless = [item for item in items if not item["owner"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, item_count=len(items), ownerless_count=len(ownerless)),
        "remediation_priorities": [_row("DCR", i, item["name"], item["owner"] or "data_governance_owner", f"Change classification from {item['current']} to {item['target']}.", refs, severity=item["severity"], affected_systems=item["systems"]) for i, item in enumerate(items, 1)],
        "access_control_updates": [_row("DCA", i, item["name"], item["owner"] or "iam_owner", f"Update access controls for target classification {item['target']}.", refs) for i, item in enumerate(items, 1)],
        "retention_follow_up": [_row("DCT", i, item["name"], item["owner"] or "records_owner", f"Review retention impact: {item['retention']}.", refs) for i, item in enumerate(items, 1) if item["retention"]],
        "audit_evidence_follow_up": [_row("DCE", i, item["name"], item["owner"] or "audit_owner", "Capture evidence of reclassification, access update, and reviewer signoff.", refs) for i, item in enumerate(items, 1)],
        "escalations": [_row("DCX", i, item["name"], "data_governance_owner", "Assign an owner before remediation can close.", refs, status="owner_missing") for i, item in enumerate(ownerless, 1)],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    value = metadata.get("data_classification_remediation")
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else []
    if not raw:
        raise ValueError("data_classification_remediation requires misclassified items")
    items = []
    for index, item in enumerate(raw, 1):
        item = item if isinstance(item, dict) else {"name": item}
        systems = sorted(dict.fromkeys(string_list(item.get("affected_systems") or item.get("systems"))), key=str.casefold)
        severity = compact(item.get("severity")).casefold() or "medium"
        items.append({"name": compact(item.get("name") or item.get("dataset") or item.get("field")) or f"item {index}", "severity": severity if severity in RANK else "medium", "current": compact(item.get("current_classification")) or "unknown", "target": compact(item.get("target_classification")) or "restricted", "owner": compact(item.get("owner")), "systems": systems, "retention": compact(item.get("retention_implications") or item.get("retention"))})
    return sorted(items, key=lambda item: (RANK[item["severity"]], -len(item["systems"]), item["name"].casefold()))


def _row(prefix: str, index: int, name: str, owner: str, description: str, refs: list[str], **extra: Any) -> dict[str, Any]:
    data = {"id": f"{prefix}{index}", "name": name, "owner": owner, "description": description, "evidence_reference_ids": refs}
    data.update({key: value for key, value in extra.items() if value not in ("", None, [])})
    return data
