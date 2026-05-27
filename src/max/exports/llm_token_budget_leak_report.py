"""LLM token budget leak export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.llm_token_budget_leak_report.v1"
KIND = "max.llm_token_budget_leak_report"


def generate_llm_token_budget_leak_report(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    findings = []
    planned_total = actual_total = 0
    for raw in records:
        planned_present = raw.get("planned_tokens") is not None or raw.get("budget_tokens") is not None
        planned = _int(raw.get("planned_tokens", raw.get("budget_tokens")))
        actual = _int(raw.get("actual_tokens", _int(raw.get("prompt_tokens")) + _int(raw.get("completion_tokens"))))
        planned_total += planned
        actual_total += actual
        overage = max(0, actual - planned) if planned_present else actual
        if overage or not planned_present:
            findings.append(
                {
                    "stage": _text(raw.get("stage")) or "unknown-stage",
                    "run_id": _text(raw.get("run_id")) or "unknown-run",
                    "planned_tokens": planned if planned_present else None,
                    "actual_tokens": actual,
                    "overage_tokens": overage,
                    "severity": "critical" if not planned_present or overage >= planned else "high" if overage >= planned * 0.25 else "medium",
                    "recommended_action": "Add token budget metadata." if not planned_present else "Tune prompt size or raise an approved budget.",
                }
            )
    findings.sort(key=lambda row: (_severity_rank(row["severity"]), -row["overage_tokens"], row["stage"].lower(), row["run_id"].lower()))
    overage_total = max(0, actual_total - planned_total)
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"planned_tokens": planned_total, "actual_tokens": actual_total, "overage_tokens": overage_total, "overage_ratio": round(overage_total / planned_total, 4) if planned_total else 0.0}, "findings": findings}


def _severity_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(value, 4)


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

