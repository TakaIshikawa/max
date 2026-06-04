"""Spec acceptance criteria risk export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.spec_acceptance_criteria_risk_report.v1"
KIND = "max.spec_acceptance_criteria_risk_report"
VAGUE_KEYWORDS = ("etc", "maybe", "appropriate", "reasonable", "as needed", "tbd")
RISK_RANK = {"high": 0, "medium": 1, "low": 2}


def generate_spec_acceptance_criteria_risk_report(specs: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for raw in specs:
        criteria = _criteria(raw.get("acceptance_criteria") or raw.get("criteria"))
        verification = raw.get("verification") or raw.get("verification_command") or raw.get("verification_commands")
        has_verification = bool(_text(verification)) if not isinstance(verification, list) else bool(verification)
        vague = sum(1 for item in criteria if any(keyword in item.casefold() for keyword in VAGUE_KEYWORDS))
        risk = _risk(len(criteria), has_verification, vague)
        rows.append({"spec_id": _text(raw.get("spec_id") or raw.get("id") or raw.get("unit_id")) or "unknown-spec", "criteria_count": len(criteria), "has_verification": has_verification, "vague_criteria_count": vague, "risk": risk})
    rows.sort(key=lambda row: (RISK_RANK[row["risk"]], row["criteria_count"], -row["vague_criteria_count"], row["spec_id"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"spec_count": len(rows), "risky_spec_count": sum(1 for r in rows if r["risk"] != "low"), "missing_verification_count": sum(1 for r in rows if not r["has_verification"])}, "rows": rows}


def _risk(criteria_count: int, has_verification: bool, vague_count: int) -> str:
    if criteria_count == 0 or not has_verification:
        return "high"
    if criteria_count < 2 or vague_count > 0:
        return "medium"
    return "low"


def _criteria(value: Any) -> list[str]:
    if isinstance(value, list | tuple | set):
        return [_text(item.get("text") if isinstance(item, dict) else item) for item in value if _text(item.get("text") if isinstance(item, dict) else item)]
    text = _text(value)
    return [text] if text else []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
