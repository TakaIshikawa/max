"""Generate deterministic third-party dependency sunset plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.third_party_dependency_sunset_plan.v1"
KIND = "max.spec.third_party_dependency_sunset_plan"


def generate_third_party_dependency_sunset_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    evidence_ids = _evidence_ids(ctx)
    dependency = compact(hints.get("dependency_name") or hints.get("dependency")) or "third-party dependency"
    replacement = compact(hints.get("replacement_path") or hints.get("replacement")) or "approved replacement path"
    integrations = _records(hints.get("affected_integrations") or hints.get("integrations"), "integration", [{"name": ctx["workflow_context"], "owner": "integration_owner", "description": f"Integration currently depends on {dependency}."}])
    steps = _records(hints.get("migration_steps") or hints.get("steps"), "step", [{"name": "migrate dependency usage", "owner": "engineering_owner", "description": f"Move affected integrations to {replacement}."}])
    controls = _records(hints.get("risk_controls") or hints.get("controls"), "control", [{"name": "parallel run validation", "owner": "engineering_owner", "description": "Run old and replacement paths until parity is confirmed."}])
    communications = _records(hints.get("customer_communications") or hints.get("communications"), "communication", [{"name": "customer dependency notice", "owner": "customer_success_owner", "description": "Notify impacted customers before sunset."}])
    checks = _records(hints.get("validation_checks"), "check", [{"name": "replacement parity check", "owner": "qa_owner", "description": "Validate replacement path meets existing integration contract."}])

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, dependency=dependency, replacement_path=replacement),
        "dependency_profile": {"name": dependency, "replacement_path": replacement, "owner": compact(hints.get("owner")) or "dependency_owner", "evidence_reference_ids": evidence_ids},
        "affected_integrations": [_item("INT", index, row, evidence_ids) for index, row in enumerate(integrations, start=1)],
        "replacement_path": {"path": replacement, "owner": compact(hints.get("replacement_owner")) or "engineering_owner", "evidence_reference_ids": evidence_ids},
        "migration_steps": [_item("MS", index, row, evidence_ids) for index, row in enumerate(steps, start=1)],
        "risk_controls": [_item("RC", index, row, evidence_ids) for index, row in enumerate(controls, start=1)],
        "communications": [_item("COM", index, row, evidence_ids) for index, row in enumerate(communications, start=1)],
        "validation_checks": [_item("VC", index, row, evidence_ids) for index, row in enumerate(checks, start=1)],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("third_party_dependency_sunset")
    return hints if isinstance(hints, dict) else {}


def _records(value: Any, default_name: str, fallback: list[dict[str, str]]) -> list[dict[str, str]]:
    raw = [value] if isinstance(value, dict) else value if isinstance(value, list) else string_list(value)
    rows = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            rows.append({"name": compact(item.get("name") or item.get("integration") or item.get("step") or item.get("control") or item.get("check")) or f"{default_name} {index}", "owner": compact(item.get("owner")), "description": compact(item.get("description") or item.get("message"))})
        else:
            rows.append({"name": compact(item) or f"{default_name} {index}", "owner": "", "description": ""})
    return sorted(rows or fallback, key=lambda row: row["name"].casefold())


def _item(prefix: str, index: int, row: dict[str, str], evidence_ids: list[str]) -> dict[str, Any]:
    return {"id": f"{prefix}{index}", "name": row["name"], "owner": row["owner"] or "engineering_owner", "description": row["description"] or row["name"], "evidence_reference_ids": evidence_ids}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
