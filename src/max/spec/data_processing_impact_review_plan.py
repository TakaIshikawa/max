"""Generate deterministic data processing impact review plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.data_processing_impact_review_plan.v1"
KIND = "max.spec.data_processing_impact_review_plan"


def generate_data_processing_impact_review_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    evidence_ids = _evidence_ids(ctx)
    categories = _values(hints.get("data_categories"), ["account data", "workflow metadata"])
    purposes = _values(hints.get("processing_purposes") or hints.get("purposes"), [f"Support {ctx['workflow_context']}"])
    systems = _values(hints.get("affected_systems") or hints.get("systems"), [ctx["stack_label"] or "application service"])
    basis = _records(hints.get("lawful_basis") or hints.get("policy_basis") or hints.get("basis_review"), "basis", [{"name": "policy review", "owner": "privacy_owner", "description": "Confirm processing basis before approval."}])
    risks = _records(hints.get("residual_risks") or ctx["risks"], "risk", [{"name": "processing change risk", "owner": "privacy_owner", "description": "Assess residual data processing risk."}])
    mitigations = _records(hints.get("mitigations"), "mitigation", [{"name": "minimize retained data", "owner": "engineering_owner", "description": "Limit processing to approved categories and retention."}])
    checks = _records(hints.get("validation_checks"), "check", [{"name": "privacy approval check", "owner": "privacy_owner", "description": "Verify basis, categories, systems, and mitigations are approved."}])

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, category_count=len(categories), system_count=len(systems)),
        "data_categories": [_named("DC", index, category, compact(hints.get("review_owner")) or "privacy_owner", evidence_ids) for index, category in enumerate(categories, start=1)],
        "processing_purposes": [_named("PP", index, purpose, "product_owner", evidence_ids) for index, purpose in enumerate(purposes, start=1)],
        "affected_systems": [_named("SYS", index, system, "engineering_owner", evidence_ids) for index, system in enumerate(systems, start=1)],
        "basis_review": [_item("BR", index, row, evidence_ids) for index, row in enumerate(basis, start=1)],
        "residual_risks": [_item("RR", index, row, evidence_ids) for index, row in enumerate(risks, start=1)],
        "mitigations": [_item("MIT", index, row, evidence_ids) for index, row in enumerate(mitigations, start=1)],
        "validation_checks": [_item("VC", index, row, evidence_ids) for index, row in enumerate(checks, start=1)],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("data_processing_impact_review")
    return hints if isinstance(hints, dict) else {}


def _records(value: Any, default_name: str, fallback: list[dict[str, str]]) -> list[dict[str, str]]:
    raw = [value] if isinstance(value, dict) else value if isinstance(value, list) else string_list(value)
    rows = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            rows.append({"name": compact(item.get("name") or item.get("risk") or item.get("basis") or item.get("check")) or f"{default_name} {index}", "owner": compact(item.get("owner")), "description": compact(item.get("description") or item.get("mitigation") or item.get("basis"))})
        else:
            rows.append({"name": compact(item) or f"{default_name} {index}", "owner": "", "description": ""})
    return sorted(rows or fallback, key=lambda row: row["name"].casefold())


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(values), key=str.casefold) if values else fallback


def _named(prefix: str, index: int, name: str, owner: str, evidence_ids: list[str]) -> dict[str, Any]:
    return {"id": f"{prefix}{index}", "name": name, "owner": owner, "evidence_reference_ids": evidence_ids}


def _item(prefix: str, index: int, row: dict[str, str], evidence_ids: list[str]) -> dict[str, Any]:
    return {"id": f"{prefix}{index}", "name": row["name"], "owner": row["owner"] or "privacy_owner", "description": row["description"] or row["name"], "evidence_reference_ids": evidence_ids}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
