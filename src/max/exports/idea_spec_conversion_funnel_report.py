"""Idea spec conversion funnel export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.idea_spec_conversion_funnel_report.v1"
KIND = "max.idea_spec_conversion_funnel_report"


def generate_idea_spec_conversion_funnel_report(records: Iterable[dict[str, Any]], *, minimum_conversion_rate: float = 0.5) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    for raw in records:
        profile = _text(raw.get("profile")) or "unknown-profile"
        row = groups.setdefault(profile, {"profile": profile, "generated_count": 0, "evaluated_count": 0, "approved_count": 0, "spec_generated_count": 0, "published_count": 0})
        row["generated_count"] += 1
        stage = _text(raw.get("stage") or raw.get("status")).lower()
        for key, aliases in {
            "evaluated_count": {"evaluated", "approved", "spec_generated", "published"},
            "approved_count": {"approved", "spec_generated", "published"},
            "spec_generated_count": {"spec_generated", "spec generated", "spec", "published"},
            "published_count": {"published"},
        }.items():
            flag = key.removesuffix("_count")
            if stage in aliases or _bool(raw.get(flag)) or _bool(raw.get(key)):
                row[key] += 1
    rows = []
    for row in groups.values():
        conversion_rate = _rate(row["published_count"], row["generated_count"])
        rows.append({**row, "conversion_rate": conversion_rate, "status": "healthy" if conversion_rate >= minimum_conversion_rate else "below_target"})
    rows.sort(key=lambda row: (row["status"] != "below_target", row["profile"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"profile_count": len(rows), "below_target_count": sum(1 for row in rows if row["status"] == "below_target"), "minimum_conversion_rate": minimum_conversion_rate}, "rows": rows}


def _rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def _bool(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes", "y"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
