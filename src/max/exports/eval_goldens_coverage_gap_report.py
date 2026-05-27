"""Evaluation goldens coverage gap export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.eval_goldens_coverage_gap_report.v1"
KIND = "max.eval_goldens_coverage_gap_report"


def generate_eval_goldens_coverage_gap_report(
    scopes: Iterable[dict[str, Any]],
    *,
    include_healthy: bool = False,
    title: str = "Eval Goldens Coverage Gap Report",
) -> dict[str, Any]:
    rows = []
    for raw in scopes:
        scope = _text(raw.get("scope") or raw.get("dimension") or raw.get("profile") or raw.get("category")) or "unknown-scope"
        current = _int(raw.get("current_count", raw.get("actual_count", raw.get("golden_count"))))
        required = _int(raw.get("required_count", raw.get("minimum_count", raw.get("required_minimum"))))
        deficit = max(0, required - current)
        if deficit or include_healthy:
            rows.append(
                {
                    "scope": scope,
                    "current_count": current,
                    "required_count": required,
                    "deficit": deficit,
                    "severity": _severity(deficit, required),
                    "recommendation": "Coverage sufficient." if deficit == 0 else f"Add {deficit} golden example(s) for {scope}.",
                    "next_sample_target": required if deficit else current,
                }
            )
    rows.sort(key=lambda row: (_severity_rank(row["severity"]), -row["deficit"], row["scope"].lower()))
    deficits = [row for row in rows if row["deficit"] > 0]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": title,
        "summary": {
            "scope_count": len(rows),
            "gap_count": len(deficits),
            "healthy_count": len(rows) - len(deficits),
            "total_deficit": sum(row["deficit"] for row in deficits),
        },
        "coverage_gaps": rows,
    }


def _severity(deficit: int, required: int) -> str:
    if deficit <= 0:
        return "healthy"
    if required <= 0 or deficit / required >= 0.5:
        return "critical"
    if deficit >= 3:
        return "high"
    return "medium"


def _severity_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "healthy": 3}.get(value, 4)


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

