"""Ideation mode conversion funnel export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.ideation_mode_conversion_funnel_report.v1"
KIND = "max.ideation_mode_conversion_funnel_report"


def generate_ideation_mode_conversion_funnel_report(records: Iterable[dict[str, Any]], *, approval_threshold: float = 0.5, publication_threshold: float = 0.25) -> dict[str, Any]:
    modes: dict[str, dict[str, Any]] = {}
    for raw in records:
        mode = _text(raw.get("ideation_mode") or raw.get("mode")) or "unknown-mode"
        row = modes.setdefault(mode, {"ideation_mode": mode, "generated": 0, "evaluated": 0, "approved": 0, "rejected": 0, "published": 0})
        row["generated"] += 1
        stage = _text(raw.get("stage") or raw.get("status")).lower()
        for name in ("evaluated", "approved", "rejected", "published"):
            if stage == name or _bool(raw.get(name)):
                row[name] += 1
    rows = []
    findings = []
    for row in modes.values():
        enriched = {**row, "approval_rate": _rate(row["approved"], row["evaluated"]), "publication_rate": _rate(row["published"], row["generated"]), "dropoff_rate": _rate(row["generated"] - row["published"], row["generated"])}
        rows.append(enriched)
        if enriched["approval_rate"] < approval_threshold or enriched["publication_rate"] < publication_threshold:
            findings.append({"ideation_mode": row["ideation_mode"], "approval_rate": enriched["approval_rate"], "publication_rate": enriched["publication_rate"], "severity": "high" if enriched["published"] == 0 else "medium", "recommendation": "Review mode prompts, evaluation criteria, and publication blockers."})
    rows.sort(key=lambda row: row["ideation_mode"].lower())
    findings.sort(key=lambda row: (_severity_rank(row["severity"]), row["ideation_mode"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"mode_count": len(rows), "flagged_mode_count": len(findings), "approval_threshold": approval_threshold, "publication_threshold": publication_threshold}, "funnel": rows, "findings": findings}


def _rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def _severity_rank(value: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(value, 3)


def _bool(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

