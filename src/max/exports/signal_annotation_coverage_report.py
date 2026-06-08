"""Signal annotation coverage export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.signal_annotation_coverage_report.v1"
KIND = "max.signal_annotation_coverage_report"


def generate_signal_annotation_coverage_report(
    records: Iterable[dict[str, Any]],
    *,
    minimum_coverage: float = 0.9,
    required_roles: Iterable[Any] = ("owner", "reviewer", "approver"),
) -> dict[str, Any]:
    threshold = _ratio(minimum_coverage)
    required = sorted({_text(role) for role in required_roles if _text(role)}, key=str.casefold)
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        profile = _text(raw.get("profile") or raw.get("profile_id") or raw.get("domain_profile")) or "default"
        source = _text(raw.get("source") or raw.get("source_id") or raw.get("source_name")) or "unknown-source"
        group = groups.setdefault((profile, source), {"total": 0, "annotated": 0, "roles": set()})
        group["total"] += 1
        roles = _roles(raw)
        if roles:
            group["annotated"] += 1
            group["roles"].update(roles)

    rows = []
    for (profile, source), group in groups.items():
        missing_roles = sorted(set(required) - group["roles"], key=str.casefold)
        total = group["total"]
        annotated = group["annotated"]
        coverage_rate = round(annotated / total, 4) if total else 1.0
        rows.append(
            {
                "profile": profile,
                "source": source,
                "total_signals": total,
                "annotated_signals": annotated,
                "unannotated_signals": total - annotated,
                "coverage_rate": coverage_rate,
                "missing_roles": missing_roles,
                "status": "complete" if coverage_rate >= threshold and not missing_roles else "incomplete",
            }
        )
    rows.sort(key=lambda row: (row["profile"].casefold(), row["source"].casefold()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "row_count": len(rows),
            "total_signals": sum(row["total_signals"] for row in rows),
            "annotated_signals": sum(row["annotated_signals"] for row in rows),
            "incomplete_count": sum(1 for row in rows if row["status"] == "incomplete"),
            "minimum_coverage": threshold,
        },
        "required_roles": required,
        "rows": rows,
    }


def _roles(raw: dict[str, Any]) -> set[str]:
    roles = {_text(raw.get("role") or raw.get("annotation_role") or raw.get("signal_role"))}
    annotations = raw.get("annotations")
    if isinstance(annotations, dict):
        annotations = list(annotations.values())
    if isinstance(annotations, list | tuple | set):
        for item in annotations:
            if isinstance(item, dict):
                roles.add(_text(item.get("role") or item.get("annotation_role") or item.get("name")))
            else:
                roles.add(_text(item))
    return {role for role in roles if role}


def _ratio(value: Any) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.9


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
