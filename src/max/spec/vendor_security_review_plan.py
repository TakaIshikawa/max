"""Generate deterministic vendor security review plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.vendor_security_review_plan.v1"
KIND = "max.spec.vendor_security_review_plan"
RISK_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def generate_vendor_security_review_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    vendor = _required(hints, "vendor_name", "vendor name")
    owner = _required(hints, "owner", "owner")
    risk_tier = _risk(_required(hints, "risk_tier", "risk tier"))
    evidence = _required_list(hints, "required_evidence", "evidence requirements")
    scope = compact(hints.get("integration_scope")) or "integration scope under review"
    exposure = compact(hints.get("data_exposure")) or "customer data exposure"
    due = compact(hints.get("due_date")) or "not recorded"
    refs = _evidence_ids(ctx)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, vendor=vendor, risk_tier=risk_tier, due_date=due),
        "review_scope": {"vendor": vendor, "integration_scope": scope, "data_exposure": exposure, "owner": owner, "risk_tier": risk_tier, "due_date": due},
        "evidence_collection": [_row("VSE", i, item, owner, f"Collect and validate {item} for {vendor}.", refs, status="required") for i, item in enumerate(evidence, 1)],
        "questionnaire_review": [_row("VSQ", 1, "Security questionnaire review", owner, f"Review questionnaire answers against {risk_tier} risk expectations.", refs)],
        "data_flow_assessment": [_row("VSF", 1, "Data-flow assessment", owner, f"Confirm {scope} data flows match declared exposure: {exposure}.", refs)],
        "remediation_tasks": _remediation_tasks(hints, owner, risk_tier, refs),
        "approval_criteria": [
            _row("VSA", 1, "Security go/no-go", owner, "Approve only after evidence, questionnaire, data-flow, and remediation checks are complete.", refs, decision="go/no-go"),
        ],
        "evidence_references": ctx["evidence_references"],
    }


def _remediation_tasks(hints: dict[str, Any], owner: str, risk_tier: str, refs: list[str]) -> list[dict[str, Any]]:
    tasks = _list(hints.get("remediation_tasks") or hints.get("remediation"), ["resolve security review findings"])
    severity = "high" if risk_tier in {"critical", "high"} else "medium"
    return [_row("VSR", i, task, owner, f"Remediate before vendor approval: {task}.", refs, severity=severity) for i, task in enumerate(tasks, 1)]


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    value = metadata.get("vendor_security_review")
    return value if isinstance(value, dict) else {}


def _required(hints: dict[str, Any], key: str, label: str) -> str:
    value = compact(hints.get(key))
    if not value:
        raise ValueError(f"vendor_security_review requires {label}")
    return value


def _required_list(hints: dict[str, Any], key: str, label: str) -> list[str]:
    values = _list(hints.get(key), [])
    if not values:
        raise ValueError(f"vendor_security_review requires {label}")
    return values


def _risk(value: str) -> str:
    tier = value.casefold()
    if tier not in RISK_RANK:
        raise ValueError("vendor_security_review requires risk tier to be low, medium, high, or critical")
    return tier


def _list(value: Any, fallback: list[str]) -> list[str]:
    items = string_list(value)
    if isinstance(value, list):
        items.extend(compact(item.get("name") or item.get("evidence") or item.get("description")) for item in value if isinstance(item, dict))
    return sorted(dict.fromkeys(item for item in items if item), key=str.casefold) or fallback


def _row(prefix: str, index: int, name: str, owner: str, description: str, refs: list[str], **extra: Any) -> dict[str, Any]:
    data = {"id": f"{prefix}{index}", "name": name, "owner": owner, "description": description, "evidence_reference_ids": refs}
    data.update({key: value for key, value in extra.items() if value not in ("", None)})
    return data


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
