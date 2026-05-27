"""Profile weight conflict export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.profile_weight_conflict_report.v1"
KIND = "max.profile_weight_conflict_report"


def generate_profile_weight_conflict_report(
    profiles: Iterable[dict[str, Any]],
    *,
    required_dimensions: Iterable[str],
    max_weight: float = 1.0,
) -> dict[str, Any]:
    required = [_text(item) for item in required_dimensions if _text(item)]
    rows = []
    checked = 0
    for profile in profiles:
        checked += 1
        profile_id = _text(profile.get("profile_id") or profile.get("id") or profile.get("profile")) or "unknown-profile"
        weights = profile.get("weights") if isinstance(profile.get("weights"), dict) else {}
        for dimension in required:
            if dimension not in weights:
                rows.append(_row(profile_id, dimension, None, "missing_dimension"))
                continue
            weight = _float(weights.get(dimension), signed=True)
            if weight < 0:
                rows.append(_row(profile_id, dimension, weight, "negative_weight"))
            elif weight > max_weight:
                rows.append(_row(profile_id, dimension, weight, "above_allowed_bounds"))
    rows.sort(key=lambda row: (row["profile_id"].lower(), row["dimension"].lower(), row["issue_type"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "profiles_checked": checked,
            "conflict_count": len(rows),
            "missing_dimension_count": sum(1 for row in rows if row["issue_type"] == "missing_dimension"),
            "out_of_range_count": sum(1 for row in rows if row["issue_type"] != "missing_dimension"),
        },
        "conflicts": rows,
    }


def _row(profile_id: str, dimension: str, observed_weight: float | None, issue_type: str) -> dict[str, Any]:
    return {
        "profile_id": profile_id,
        "dimension": dimension,
        "observed_weight": observed_weight,
        "issue_type": issue_type,
        "recommendation": f"Set a valid weight for {dimension} on {profile_id}.",
    }


def _float(value: Any, *, signed: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(number if signed else max(0.0, number), 4)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

