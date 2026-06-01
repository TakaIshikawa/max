"""Generate deterministic tokenizer drift reconciliation plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base

SCHEMA_VERSION = "max.spec.tokenizer_drift_reconciliation_plan.v1"
KIND = "max.spec.tokenizer_drift_reconciliation_plan"


def generate_tokenizer_drift_reconciliation_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, hints, evidence_ids = base(spec_like, "tokenizer_drift_reconciliation")
    rows = _rows(hints) or _rows(spec)
    findings = sorted((_finding(row, index, evidence_ids) for index, row in enumerate(rows, start=1)), key=_rank)
    high_risk = [item for item in findings if item["risk_level"] in {"critical", "high"}]
    fallback = not findings
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": {
            "title": ctx["title"],
            "status": "monitor" if fallback else ("critical" if any(i["risk_level"] == "critical" for i in findings) else "warning" if high_risk else "healthy"),
            "drift_row_count": len(findings),
            "high_risk_count": len(high_risk),
            "changed_tokenizer_count": sum(1 for item in findings if item["tokenizer_changed"]),
            "max_drift_percent": max((item["drift_percent"] for item in findings), default=0.0),
        },
        "drift_findings": findings,
        "reconciliation_steps": _steps(findings, evidence_ids),
        "owner_assignments": _owners(findings, evidence_ids),
        "verification_gates": _gates(fallback, evidence_ids),
        "evidence_references": ctx["evidence_references"],
    }


def _rows(source: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("rows", "tokenizers", "models", "prompts", "tokenizer", "model"):
        value = source.get(key) if isinstance(source, dict) else None
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [value]
    return []


def _finding(row: dict[str, Any], index: int, evidence_ids: list[str]) -> dict[str, Any]:
    old_count = _num(row.get("old_token_count") or row.get("previous_token_count") or row.get("baseline_tokens"))
    new_count = _num(row.get("new_token_count") or row.get("current_token_count") or row.get("tokens"))
    old_name = compact(row.get("old_tokenizer") or row.get("previous_tokenizer") or row.get("baseline_tokenizer"))
    new_name = compact(row.get("new_tokenizer") or row.get("current_tokenizer") or row.get("tokenizer"))
    drift = round(((new_count - old_count) / old_count) * 100, 2) if old_count else 0.0
    changed = bool(old_name and new_name and old_name != new_name)
    abs_drift = abs(drift)
    risk = "critical" if abs_drift > 50 or (changed and abs_drift > 20) else "high" if abs_drift > 20 or changed else "medium" if abs_drift > 5 else "low"
    name = compact(row.get("prompt_id") or row.get("id") or row.get("model") or row.get("name")) or f"tokenizer-row-{index}"
    return {
        "id": f"TDR{index}",
        "prompt_id": name,
        "model": compact(row.get("model")) or "unknown",
        "old_tokenizer": old_name,
        "new_tokenizer": new_name,
        "old_token_count": old_count,
        "new_token_count": new_count,
        "drift_percent": drift,
        "tokenizer_changed": changed,
        "risk_level": risk,
        "owner": compact(row.get("owner")) or "ml_platform_owner",
        "action": "rebaseline budget and regenerate prompt token estimates" if risk in {"critical", "high"} else "monitor on next tokenizer calibration",
        "evidence_reference_ids": evidence_ids,
    }


def _steps(findings: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    targets = findings[:3] or [{"prompt_id": "tokenizer inventory"}]
    return [
        {"id": f"TDS{index}", "name": item["prompt_id"], "owner": item.get("owner", "ml_platform_owner"), "action": "recompute token estimates, update stored baselines, and rerun budget projections", "evidence_reference_ids": evidence_ids}
        for index, item in enumerate(targets, start=1)
    ]


def _owners(findings: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    owners = sorted({item.get("owner") or "ml_platform_owner" for item in findings} or {"ml_platform_owner"})
    return [{"id": f"TDO{index}", "owner": owner, "responsibility": "approve tokenizer baseline reconciliation", "evidence_reference_ids": evidence_ids} for index, owner in enumerate(owners, start=1)]


def _gates(fallback: bool, evidence_ids: list[str]) -> list[dict[str, Any]]:
    checks = ["tokenizer drift input rows are present"] if fallback else ["all high-drift prompts have refreshed token counts"]
    checks.extend(["tokenizer names match current model routing", "cost projection fixtures pass with reconciled token counts"])
    return [{"id": f"TDG{index}", "check": check, "owner": "quality_owner", "evidence_reference_ids": evidence_ids} for index, check in enumerate(checks, start=1)]


def _rank(item: dict[str, Any]) -> tuple[int, float, str]:
    return ({"critical": 0, "high": 1, "medium": 2, "low": 3}[item["risk_level"]], -abs(item["drift_percent"]), item["prompt_id"])


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
