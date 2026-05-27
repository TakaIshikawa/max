"""Synthesis prompt failure export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.synthesis_prompt_failure_report.v1"
KIND = "max.synthesis_prompt_failure_report"


def generate_synthesis_prompt_failure_report(attempts: Iterable[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    total = 0
    for raw in attempts:
        if _text(raw.get("status")).lower() not in {"failed", "error", "timeout"}:
            continue
        total += 1
        key = (
            _text(raw.get("profile")) or "unknown-profile",
            _text(raw.get("stage")) or "unknown-stage",
            _text(raw.get("template_id") or raw.get("prompt_template")) or "unknown-template",
            _text(raw.get("error_class")) or "unknown-error",
        )
        row = groups.setdefault(
            key,
            {
                "profile": key[0],
                "stage": key[1],
                "template_id": key[2],
                "error_class": key[3],
                "failed_attempts": 0,
                "retry_exhausted_count": 0,
                "severity": "low",
                "next_action": "Inspect failing prompt template and retry policy.",
            },
        )
        row["failed_attempts"] += 1
        row["retry_exhausted_count"] += 1 if _bool(raw.get("retry_exhausted")) else 0
        row["severity"] = _severity(row["failed_attempts"], row["retry_exhausted_count"])
    rows = sorted(groups.values(), key=lambda row: (_severity_rank(row["severity"]), -row["failed_attempts"], row["profile"].lower(), row["stage"].lower(), row["template_id"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"failed_attempt_count": total, "group_count": len(rows), "retry_exhausted_count": sum(row["retry_exhausted_count"] for row in rows)}, "failures": rows}


def _severity(failed: int, exhausted: int) -> str:
    if exhausted or failed >= 5:
        return "critical"
    if failed >= 3:
        return "high"
    return "medium"


def _severity_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(value, 4)


def _bool(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes", "exhausted"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

