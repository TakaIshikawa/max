"""LLM prompt failure recovery export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.llm_prompt_failure_recovery_report.v1"
KIND = "max.llm_prompt_failure_recovery_report"


def generate_llm_prompt_failure_recovery_report(records: Iterable[dict[str, Any]], *, minimum_recovery_rate: float = 0.8) -> dict[str, Any]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in records:
        stage = _text(raw.get("stage")) or "unknown-stage"
        prompt_version = _text(raw.get("prompt_version") or raw.get("version")) or "unknown-version"
        row = groups.setdefault((stage, prompt_version), {"stage": stage, "prompt_version": prompt_version, "failure_count": 0, "retry_count": 0, "recovered_count": 0, "unrecovered_count": 0})
        row["failure_count"] += _int(raw.get("failure_count")) or 1
        row["retry_count"] += _int(raw.get("retry_count") or raw.get("retries"))
        recovered = _int(raw.get("recovered_count"))
        unrecovered = _int(raw.get("unrecovered_count"))
        outcome = _text(raw.get("recovery_outcome") or raw.get("outcome") or raw.get("status")).lower()
        row["recovered_count"] += recovered or (1 if outcome in {"recovered", "retry_succeeded", "success"} or _bool(raw.get("recovered")) else 0)
        row["unrecovered_count"] += unrecovered or (1 if outcome in {"unrecovered", "failed", "failure"} or _bool(raw.get("unrecovered")) else 0)
    rows = []
    for row in groups.values():
        if row["unrecovered_count"] == 0:
            row["unrecovered_count"] = max(0, row["failure_count"] - row["recovered_count"])
        recovery_rate = _rate(row["recovered_count"], row["failure_count"])
        rows.append({**row, "recovery_rate": recovery_rate, "status": "healthy" if recovery_rate >= minimum_recovery_rate else "below_target"})
    rows.sort(key=lambda row: (row["status"] != "below_target", row["stage"].lower(), row["prompt_version"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"group_count": len(rows), "below_target_count": sum(1 for row in rows if row["status"] == "below_target"), "minimum_recovery_rate": minimum_recovery_rate}, "rows": rows}


def _rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def _bool(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes", "y"}


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
