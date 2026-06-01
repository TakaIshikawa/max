"""Signal taxonomy coverage export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.signal_taxonomy_coverage_report.v1"
KIND = "max.signal_taxonomy_coverage_report"


def generate_signal_taxonomy_coverage_report(
    signals: Iterable[dict[str, Any]],
    required_roles: Iterable[Any],
    *,
    required_categories: Iterable[Any] | None = None,
) -> dict[str, Any]:
    roles = sorted({_text(role) for role in required_roles if _text(role)}, key=str.casefold)
    categories = sorted({_text(category) for category in required_categories or [] if _text(category)}, key=str.casefold)
    observed: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(lambda: {"roles": set(), "categories": set()})
    for raw in signals:
        profile = _text(raw.get("profile") or raw.get("profile_id")) or "unknown-profile"
        source = _text(raw.get("source") or raw.get("source_id")) or "unknown-source"
        role = _text(raw.get("role") or raw.get("signal_role"))
        category = _text(raw.get("category") or raw.get("signal_category"))
        if role:
            observed[(profile, source)]["roles"].add(role)
        if category:
            observed[(profile, source)]["categories"].add(category)

    rows = []
    for (profile, source), values in observed.items():
        missing_roles = sorted(set(roles) - values["roles"], key=str.casefold)
        missing_categories = sorted(set(categories) - values["categories"], key=str.casefold)
        rows.append(
            {
                "profile": profile,
                "source": source,
                "observed_roles": sorted(values["roles"], key=str.casefold),
                "missing_roles": missing_roles,
                "role_coverage": _coverage(len(roles) - len(missing_roles), len(roles)),
                "observed_categories": sorted(values["categories"], key=str.casefold),
                "missing_categories": missing_categories,
                "category_coverage": _coverage(len(categories) - len(missing_categories), len(categories)),
            }
        )
    rows.sort(key=lambda row: (row["profile"].casefold(), row["source"].casefold()))
    profile_rows = []
    for profile in sorted({row["profile"] for row in rows}, key=str.casefold):
        profile_roles = set().union(*(observed[(row["profile"], row["source"])]["roles"] for row in rows if row["profile"] == profile))
        profile_categories = set().union(*(observed[(row["profile"], row["source"])]["categories"] for row in rows if row["profile"] == profile))
        missing_roles = sorted(set(roles) - profile_roles, key=str.casefold)
        missing_categories = sorted(set(categories) - profile_categories, key=str.casefold)
        profile_rows.append(
            {
                "profile": profile,
                "missing_roles": missing_roles,
                "role_coverage": _coverage(len(roles) - len(missing_roles), len(roles)),
                "missing_categories": missing_categories,
                "category_coverage": _coverage(len(categories) - len(missing_categories), len(categories)),
            }
        )
    overall_missing_roles = sorted(set(roles) - set().union(*(values["roles"] for values in observed.values())) if observed else set(roles), key=str.casefold)
    overall_missing_categories = sorted(set(categories) - set().union(*(values["categories"] for values in observed.values())) if observed else set(categories), key=str.casefold)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "profile_source_count": len(rows),
            "required_role_count": len(roles),
            "required_category_count": len(categories),
            "role_coverage": _coverage(len(roles) - len(overall_missing_roles), len(roles)),
            "category_coverage": _coverage(len(categories) - len(overall_missing_categories), len(categories)),
            "gap_count": sum(len(row["missing_roles"]) + len(row["missing_categories"]) for row in rows),
        },
        "required_roles": roles,
        "required_categories": categories,
        "profiles": profile_rows,
        "coverage": rows,
        "missing_roles": overall_missing_roles,
        "missing_categories": overall_missing_categories,
    }


def _coverage(observed: int, required: int) -> float:
    return round(observed / required, 4) if required else 1.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
