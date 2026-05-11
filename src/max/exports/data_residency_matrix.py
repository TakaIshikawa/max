"""Data residency matrix export for regional deployment planning."""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.data_residency_matrix.v1"
KIND = "max.data_residency_matrix"
_FIELDS = ["idea_id", "title", "required_region", "coverage_status", "hosting_regions", "customer_regions", "regulated_data_types", "replication_strategy", "residency_exceptions", "unresolved_gaps"]


def build_data_residency_matrix_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    units = store.get_buildable_units(limit=1000, domain=domain)
    rows = [row for unit in units for row in _rows(unit)]
    rows.sort(key=lambda row: (_status_rank(row["coverage_status"]), row["required_region"], row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "data_residency_matrix", "domain_filter": domain},
        "region_row_count": len(rows),
        "region_rows": rows,
        "summary": _summary(rows),
    }


def render_data_residency_matrix_markdown(report: dict[str, Any]) -> str:
    lines = ["# Data Residency Matrix", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Region Requirements", "", "| Unit | Required Region | Status | Data Types | Gaps |", "|------|-----------------|--------|------------|------|"]
    for row in report.get("region_rows", []):
        lines.append(f"| {row['title']} | {row['required_region']} | {row['coverage_status']} | {', '.join(row['regulated_data_types'])} | {', '.join(row['unresolved_gaps']) or 'none'} |")
    lines.extend(["", "## Region Coverage", "", "| Region | Requirements | Covered | Exceptions | Gaps |", "|--------|--------------|---------|------------|------|"])
    for row in report.get("summary", {}).get("by_required_region", []):
        lines.append(f"| {row['required_region']} | {row['requirement_count']} | {row['covered_count']} | {row['exception_count']} | {row['gap_count']} |")
    return "\n".join(lines).rstrip() + "\n"


def render_data_residency_matrix_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_data_residency_matrix_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_FIELDS)
    writer.writeheader()
    for row in report.get("region_rows", []):
        writer.writerow({**{field: row.get(field) for field in _FIELDS}, "hosting_regions": "; ".join(row.get("hosting_regions", [])), "customer_regions": "; ".join(row.get("customer_regions", [])), "regulated_data_types": "; ".join(row.get("regulated_data_types", [])), "residency_exceptions": "; ".join(row.get("residency_exceptions", [])), "unresolved_gaps": "; ".join(row.get("unresolved_gaps", []))})
    return output.getvalue()


def _rows(unit: Any) -> list[dict[str, Any]]:
    metadata = _metadata(unit)
    required = _items(metadata.get("data_regions_required"))
    hosting = _items(metadata.get("hosting_regions"))
    customers = _items(metadata.get("customer_regions"))
    data_types = _items(metadata.get("regulated_data_types"))
    exceptions = _items(metadata.get("residency_exceptions"))
    strategy = str(metadata.get("replication_strategy") or "unspecified")
    rows = []
    for region in required:
        if region in hosting:
            status = "covered"
            gaps: list[str] = []
        elif region in exceptions:
            status = "exception-approved"
            gaps = []
        else:
            status = "gap"
            gaps = [f"missing_hosting_region:{region}"]
        rows.append({
            "idea_id": str(getattr(unit, "id", "")),
            "title": str(getattr(unit, "title", "Untitled")),
            "required_region": region,
            "coverage_status": status,
            "hosting_regions": hosting,
            "customer_regions": customers,
            "regulated_data_types": data_types,
            "replication_strategy": strategy,
            "residency_exceptions": exceptions,
            "unresolved_gaps": gaps,
        })
    return rows


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_region: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_region[row["required_region"]].append(row)
        for data_type in row["regulated_data_types"] or ["unspecified"]:
            by_type[data_type].append(row)
    return {
        "by_required_region": [_coverage_row("required_region", region, items) for region, items in sorted(by_region.items())],
        "by_data_type": [_coverage_row("data_type", data_type, items) for data_type, items in sorted(by_type.items())],
    }


def _coverage_row(key: str, name: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        key: name,
        "requirement_count": len(items),
        "covered_count": sum(1 for row in items if row["coverage_status"] == "covered"),
        "exception_count": sum(1 for row in items if row["coverage_status"] == "exception-approved"),
        "gap_count": sum(1 for row in items if row["coverage_status"] == "gap"),
    }


def _items(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [str(key) for key, enabled in value.items() if _bool(enabled)]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"true", "1", "yes", "approved", "covered", "required"}


def _status_rank(value: str) -> int:
    return {"gap": 0, "exception-approved": 1, "covered": 2}.get(value, 3)
