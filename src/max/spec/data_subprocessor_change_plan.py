"""Generate deterministic data subprocessor change plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-data-subprocessor-change-plan/v1"
KIND = "max.spec.data_subprocessor_change_plan"
SUPPORTED_REGIONS = {"us", "eu", "uk", "ca", "au", "jp", "global"}


def generate_data_subprocessor_change_plan(spec_like: Any) -> dict[str, Any]:
    spec = _dict(spec_like)
    plan = _nested(spec, "data_subprocessor_change")
    subprocessors = _subprocessors(plan, spec)
    notices = _rows(plan.get("customer_notice_requirements") or spec.get("customer_notice_requirements"), "notice", "DSC-N")
    dpa = _rows(plan.get("dpa_review") or spec.get("dpa_review"), "item", "DSC-D")
    objections = _rows(plan.get("objection_handling") or spec.get("objection_handling"), "path", "DSC-O")
    rollback = _rows(plan.get("rollback_options") or spec.get("rollback_options"), "option", "DSC-R")
    evidence = _evidence(plan, spec)
    warnings = _warnings(subprocessors, notices, dpa)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "subprocessor_count": len(subprocessors),
            "high_risk_count": sum(1 for row in subprocessors if row["risk"] == "high"),
            "notice_blocked_count": sum(1 for warning in warnings if warning["warning"] == "missing notice date"),
            "warning_count": len(warnings),
        },
        "subprocessors": subprocessors,
        "data_classes": sorted({item for row in subprocessors for item in row["data_classes"]}, key=str.casefold),
        "regions": sorted({item for row in subprocessors for item in row["regions"]}, key=str.casefold),
        "customer_notice_requirements": notices,
        "dpa_review": dpa,
        "objection_handling": objections,
        "rollback_options": rollback,
        "evidence_references": evidence,
        "readiness_warnings": warnings,
    }


def render_data_subprocessor_change_plan_markdown(plan_or_spec: dict[str, Any] | None = None) -> str:
    plan = plan_or_spec if isinstance(plan_or_spec, dict) and plan_or_spec.get("kind") == KIND else generate_data_subprocessor_change_plan(plan_or_spec)
    lines = ["# Data Subprocessor Change Plan", ""]
    _section(lines, "Subprocessors", plan["subprocessors"], lambda row: f"- {row['id']}: {row['name']} regions={', '.join(row['regions'])} risk={row['risk']}")
    _section(lines, "Customer Notice Requirements", plan["customer_notice_requirements"], lambda row: f"- {row['id']}: {row['notice']} date={row.get('date', 'date-required')}")
    _section(lines, "DPA Review", plan["dpa_review"], lambda row: f"- {row['id']}: {row['item']} status={row.get('status', 'missing')}")
    _section(lines, "Warnings", plan["readiness_warnings"], lambda row: f"- {row['id']}: {row['subprocessor']} {row['warning']}")
    return "\n".join(lines).rstrip() + "\n"


def _subprocessors(plan: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows = plan.get("subprocessors") or spec.get("subprocessors")
    if not isinstance(rows, list) or not rows:
        rows = [{"name": "subprocessor-required"}]
    result = []
    for item in rows:
        row = _dict(item)
        name = _text(row.get("name") or row.get("vendor") or (item if not isinstance(item, dict) else "")) or "subprocessor-required"
        regions = _values(row.get("regions") or row.get("region")) or ["region-required"]
        risk = "high" if any(region.casefold() not in SUPPORTED_REGIONS for region in regions) or _text(row.get("risk")).casefold() == "high" else (_text(row.get("risk")) or "standard")
        result.append({"id": "", "name": name, "data_classes": _values(row.get("data_classes") or row.get("data")) or ["data-class-required"], "regions": regions, "notice_date": _text(row.get("notice_date") or row.get("notice")) or "date-required", "dpa_status": _text(row.get("dpa_status") or row.get("dpa_review")) or "missing", "risk": risk})
    return _numbered(sorted(result, key=lambda row: row["name"].casefold()), "DSC-S")


def _warnings(subprocessors: list[dict[str, Any]], notices: list[dict[str, str]], dpa: list[dict[str, str]]) -> list[dict[str, str]]:
    warnings = []
    for row in subprocessors:
        if row["notice_date"] == "date-required":
            warnings.append({"subprocessor": row["name"], "warning": "missing notice date", "severity": "high"})
        if row["dpa_status"].casefold() not in {"approved", "complete", "completed"} and not dpa:
            warnings.append({"subprocessor": row["name"], "warning": "missing DPA review", "severity": "high"})
        unsupported = [region for region in row["regions"] if region.casefold() not in SUPPORTED_REGIONS]
        if unsupported:
            warnings.append({"subprocessor": row["name"], "warning": "unsupported regions", "severity": "critical", "regions": ", ".join(unsupported)})
    if notices and any(row.get("date") == "date-required" for row in notices):
        warnings.append({"subprocessor": "all", "warning": "missing notice date", "severity": "high"})
    return _numbered(warnings, "DSC-W")


def _rows(value: Any, key: str, prefix: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        row = {str(k): _text(v) for k, v in (item.items() if isinstance(item, dict) else [(key, item)]) if _text(v)}
        if row.get(key) or row.get("name"):
            row[key] = row.get(key) or row["name"]
            row.setdefault("date", row.get("notice_date") or "date-required")
            rows.append(row)
    return _numbered(sorted(rows, key=lambda row: row[key].casefold()), prefix)


def _evidence(plan: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, str]]:
    refs = _values(plan.get("evidence_references") or spec.get("evidence_references"))
    return [{"id": f"DSC-E{index:03d}", "reference": ref} for index, ref in enumerate(sorted(dict.fromkeys(refs), key=str.casefold), start=1)]


def _section(lines: list[str], title: str, rows: list[dict[str, Any]], render: Any) -> None:
    lines.extend([f"## {title}", ""])
    lines.extend(render(row) for row in rows)
    if not rows:
        lines.append("- None.")
    lines.append("")


def _nested(spec: dict[str, Any], key: str) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    return _dict(spec.get(key) or metadata.get(key))


def _numbered(rows: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    for index, row in enumerate(rows, start=1):
        row["id"] = f"{prefix}{index:03d}"
    return rows


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _values(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [_text(item) for item in values if _text(item)]


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""
