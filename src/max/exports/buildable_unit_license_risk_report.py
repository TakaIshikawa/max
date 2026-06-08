"""Buildable unit license risk export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.buildable_unit_license_risk_report.v1"
KIND = "max.buildable_unit_license_risk_report"
_STATUS_RANK = {"blocked": 0, "review": 1, "ok": 2}


def generate_buildable_unit_license_risk_report(
    records: Iterable[dict[str, Any]],
    *,
    blocked_licenses: Iterable[str] = ("agpl", "gpl", "sspl"),
    review_licenses: Iterable[str] = ("lgpl", "mpl", "cc-by-sa", "unknown"),
) -> dict[str, Any]:
    blocked = {_norm(item) for item in blocked_licenses if _norm(item)}
    review = {_norm(item) for item in review_licenses if _norm(item)}
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        unit = _text(raw.get("buildable_unit_id") or raw.get("unit_id") or raw.get("id") or raw.get("name")) or "unknown-unit"
        profile = _text(raw.get("profile") or raw.get("domain_profile") or raw.get("profile_id")) or "default"
        group = groups.setdefault((unit, profile), {"dependencies": 0, "allowed": 0, "review": [], "blocked": []})
        for dep in _dependencies(raw):
            name = _text(dep.get("name") or dep.get("dependency") or dep.get("package")) or "unknown-dependency"
            license_name = _text(dep.get("license") or dep.get("license_id") or dep.get("declared_license")) or "unknown"
            group["dependencies"] += 1
            normalized = _norm(license_name)
            finding = {"name": name, "license": license_name}
            if normalized in blocked:
                group["blocked"].append(finding)
            elif normalized in review:
                group["review"].append(finding)
            else:
                group["allowed"] += 1

    rows = []
    for (unit, profile), group in groups.items():
        status = "blocked" if group["blocked"] else ("review" if group["review"] else "ok")
        rows.append(
            {
                "buildable_unit_id": unit,
                "profile": profile,
                "dependency_count": group["dependencies"],
                "allowed_count": group["allowed"],
                "review_count": len(group["review"]),
                "blocked_count": len(group["blocked"]),
                "highest_risk_dependencies": sorted({item["name"] for item in group["blocked"] or group["review"]}, key=str.lower),
                "status": status,
            }
        )
    rows.sort(key=lambda row: (_STATUS_RANK[row["status"]], row["profile"].casefold(), row["buildable_unit_id"].casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"row_count": len(rows), "blocked_count": sum(1 for row in rows if row["status"] == "blocked"), "review_count": sum(1 for row in rows if row["status"] == "review"), "ok_count": sum(1 for row in rows if row["status"] == "ok")}, "rows": rows}


def _dependencies(raw: dict[str, Any]) -> list[dict[str, Any]]:
    value = raw.get("dependencies") or raw.get("declared_dependencies") or raw.get("stack_dependencies")
    if isinstance(value, dict):
        return [dict({"name": key}, **item) if isinstance(item, dict) else {"name": key, "license": item} for key, item in value.items()]
    if isinstance(value, list | tuple | set):
        return [item if isinstance(item, dict) else {"name": item} for item in value]
    return [raw]


def _norm(value: Any) -> str:
    return _text(value).lower().replace("license", "").strip()


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
