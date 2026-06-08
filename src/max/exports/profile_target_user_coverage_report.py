"""Profile target user coverage export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.profile_target_user_coverage_report.v1"
KIND = "max.profile_target_user_coverage_report"


def generate_profile_target_user_coverage_report(
    records: Iterable[dict[str, Any]],
    *,
    minimum_coverage_ratio: float = 0.8,
) -> dict[str, Any]:
    threshold = min(1.0, max(0.0, _float(minimum_coverage_ratio)))
    groups: dict[str, dict[str, set[str]]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        profile = _text(raw.get("profile") or raw.get("domain_profile") or raw.get("profile_id")) or "default"
        group = groups.setdefault(profile, {"targets": set(), "covered": set()})
        group["targets"].update(_segments(raw.get("target_users") or raw.get("target_user_segments") or raw.get("segments")))
        group["covered"].update(_segments(raw.get("covered_target_users") or raw.get("insight_target_users") or raw.get("unit_target_users") or raw.get("covered_segments")))

    rows = []
    for profile, group in groups.items():
        targets = group["targets"]
        covered = group["covered"] & targets if targets else group["covered"]
        missing = targets - covered
        ratio = round(len(covered) / len(targets), 4) if targets else 1.0
        rows.append({"profile": profile, "target_user_count": len(targets), "covered_count": len(covered), "missing_count": len(missing), "coverage_ratio": ratio, "covered_target_users": sorted(covered, key=str.lower), "missing_target_users": sorted(missing, key=str.lower), "status": "covered" if ratio >= threshold else "gap"})
    rows.sort(key=lambda row: (row["status"] != "gap", row["profile"].casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"row_count": len(rows), "gap_count": sum(1 for row in rows if row["status"] == "gap"), "covered_count": sum(1 for row in rows if row["status"] == "covered"), "minimum_coverage_ratio": threshold}, "rows": rows}


def _segments(value: Any) -> set[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list | tuple | set):
        items = list(value)
    else:
        items = []
    return {_text(item).lower() for item in items if _text(item)}


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
