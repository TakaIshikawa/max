"""Generate deterministic release risk acceptance plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.release_risk_acceptance_plan.v1"
KIND = "max.spec.release_risk_acceptance_plan"
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def generate_release_risk_acceptance_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    risks = _risks(hints.get("accepted_risks") or hints.get("risks") or ctx["risks"], hints)
    evidence_ids = _evidence_ids(ctx)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, accepted_risk_count=len(risks), highest_severity=risks[0]["severity"]),
        "accepted_risks": [_risk_record(index, risk, evidence_ids) for index, risk in enumerate(risks, start=1)],
        "mitigation_actions": _mitigations(hints, risks, evidence_ids),
        "decision_criteria": _criteria(hints, evidence_ids),
        "approver_signoffs": _approvers(hints, evidence_ids),
        "review_cadence": {
            "cadence": compact(hints.get("review_cadence") or hints.get("cadence")) or "weekly until release plus 30 days",
            "expiry": compact(hints.get("expiry") or hints.get("expires_at")) or "next release retrospective",
            "owner": compact(hints.get("review_owner")) or "release_manager",
        },
        "evidence_references": ctx["evidence_references"],
    }


def _risk_record(index: int, risk: dict[str, str], evidence_ids: list[str]) -> dict[str, Any]:
    return {
        "id": f"RAR{index}",
        "risk": risk["risk"],
        "severity": risk["severity"],
        "owner": risk["owner"],
        "acceptance_rationale": risk["rationale"] or f"{risk['risk']} accepted with documented mitigation and review cadence.",
        "evidence_reference_ids": evidence_ids,
    }


def _mitigations(hints: dict[str, Any], risks: list[dict[str, str]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    records = _records(hints.get("mitigations") or hints.get("mitigation_actions"), "mitigation")
    if not records:
        records = [{"name": f"Mitigate {risk['risk']}", "owner": risk["owner"], "description": f"Track mitigation for {risk['risk']} before release acceptance."} for risk in risks]
    return [
        {"id": f"MA{index}", "action": row["name"], "owner": row["owner"] or "risk_owner", "description": row["description"] or row["name"], "evidence_reference_ids": evidence_ids}
        for index, row in enumerate(sorted(records, key=lambda row: row["name"].casefold()), start=1)
    ]


def _criteria(hints: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    records = _records(hints.get("decision_criteria"), "criterion") or [
        {"name": "Residual risk is explicitly accepted by named approvers.", "owner": "release_manager", "description": "Residual risk is explicitly accepted by named approvers."},
        {"name": "Mitigations have owners and review dates.", "owner": "risk_owner", "description": "Mitigations have owners and review dates."},
    ]
    return [{"id": f"DC{index}", "criterion": row["name"], "owner": row["owner"] or "release_manager", "evidence_reference_ids": evidence_ids} for index, row in enumerate(records, start=1)]


def _approvers(hints: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    raw = hints.get("approvers") or hints.get("approver_signoffs") or ["release_manager", "product_owner", "engineering_owner"]
    approvers = _records(raw, "approver")
    return [
        {"id": f"AS{index}", "role": row["name"], "owner": row["owner"] or row["name"], "status": "pending", "evidence_reference_ids": evidence_ids}
        for index, row in enumerate(sorted(approvers, key=lambda row: row["name"].casefold()), start=1)
    ]


def _risks(value: Any, hints: dict[str, Any]) -> list[dict[str, str]]:
    records = _records(value, "release risk")
    if not records:
        records = [{"name": "release risk review pending", "owner": "", "description": "Review release risks before acceptance."}]
    owner = compact(hints.get("owner") or hints.get("risk_owner")) or "risk_owner"
    risks = [
        {
            "risk": row["name"],
            "owner": row["owner"] or owner,
            "severity": _severity(row.get("severity") or hints.get("severity")),
            "rationale": row["description"],
        }
        for row in records
    ]
    return sorted(risks, key=lambda row: (SEVERITY_RANK[row["severity"]], row["risk"].casefold()))


def _records(value: Any, default_name: str) -> list[dict[str, str]]:
    raw = [value] if isinstance(value, dict) else value if isinstance(value, list) else string_list(value)
    rows = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            rows.append(
                {
                    "name": compact(item.get("risk") or item.get("name") or item.get("criterion") or item.get("role")) or f"{default_name} {index}",
                    "owner": compact(item.get("owner") or item.get("approver")),
                    "description": compact(item.get("rationale") or item.get("description") or item.get("mitigation")),
                    "severity": compact(item.get("severity")),
                }
            )
        else:
            name = compact(item) or f"{default_name} {index}"
            rows.append({"name": name, "owner": "", "description": "", "severity": ""})
    return rows


def _severity(value: Any) -> str:
    text = compact(value).casefold()
    return text if text in SEVERITY_RANK else "medium"


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("release_risk_acceptance")
    return hints if isinstance(hints, dict) else {}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
