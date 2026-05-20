"""Spec generation readiness audit for approved buildable units."""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.spec_generation_readiness_audit.v1"
KIND = "max.spec_generation_readiness_audit"
CSV_COLUMNS = (
    "unit_id",
    "title",
    "missing_fields",
    "blocker_count",
    "warning_count",
    "readiness_band",
)
REQUIRED_BLOCKER_FIELDS = ("problem", "solution", "target_users", "suggested_stack", "evidence_signals")
REQUIRED_WARNING_FIELDS = ("validation_plan", "domain_risks", "inspiring_insights")
_READINESS_ORDER = {"blocked": 0, "warning": 1, "ready": 2}


@dataclass(frozen=True)
class SpecReadinessIssue:
    field: str
    severity: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"field": self.field, "severity": self.severity, "message": self.message}


@dataclass(frozen=True)
class SpecReadinessRow:
    unit_id: str
    title: str
    missing_fields: tuple[str, ...]
    blocker_count: int
    warning_count: int
    readiness_band: str
    issues: tuple[SpecReadinessIssue, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "title": self.title,
            "missing_fields": list(self.missing_fields),
            "blocker_count": self.blocker_count,
            "warning_count": self.warning_count,
            "readiness_band": self.readiness_band,
            "issues": [issue.as_dict() for issue in self.issues],
        }


def build_spec_generation_readiness_audit(store: "Store", *, limit: int = 500) -> dict[str, Any]:
    """Audit approved buildable units for inputs needed to generate tact-compatible specs."""
    if limit < 1:
        raise ValueError("limit must be at least 1")

    units = store.get_buildable_units(limit=limit, status="approved")
    rows = [_row_for_unit(unit) for unit in units]
    rows.sort(key=_row_sort_key)
    counts = Counter(row.readiness_band for row in rows)
    blocked = [row.as_dict() for row in rows if row.readiness_band == "blocked"]
    warning_only = [row.as_dict() for row in rows if row.readiness_band == "warning"]
    ready = [row.as_dict() for row in rows if row.readiness_band == "ready"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {"limit": limit, "status": "approved"},
        "summary": {
            "approved_unit_count": len(rows),
            "blocked_count": counts.get("blocked", 0),
            "warning_only_count": counts.get("warning", 0),
            "ready_count": counts.get("ready", 0),
            "blocker_count": sum(row.blocker_count for row in rows),
            "warning_count": sum(row.warning_count for row in rows),
        },
        "rows": [row.as_dict() for row in rows],
        "blocked_units": blocked,
        "warning_only_units": warning_only,
        "ready_units": ready,
    }


def render_spec_generation_readiness_audit(report: Mapping[str, Any], *, fmt: str = "json") -> str:
    """Render spec generation readiness audit as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported spec generation readiness audit format: {fmt}")

    summary = _mapping(report.get("summary"))
    lines = [
        "# Spec Generation Readiness Audit",
        "",
        f"Schema: `{report.get('schema_version')}`",
        f"Approved units analyzed: {summary.get('approved_unit_count', 0)}",
        f"Blocked: {summary.get('blocked_count', 0)}",
        f"Warning-only: {summary.get('warning_only_count', 0)}",
        f"Ready: {summary.get('ready_count', 0)}",
        "",
    ]
    _append_section(lines, "Blocked Units", report.get("blocked_units"))
    _append_section(lines, "Warning-Only Units", report.get("warning_only_units"))
    _append_section(lines, "Ready Units", report.get("ready_units"))
    return "\n".join(lines).rstrip() + "\n"


def _render_csv(report: Mapping[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _sorted_row_maps(report.get("rows")):
        writer.writerow({**{key: row.get(key, "") for key in CSV_COLUMNS}, "missing_fields": "; ".join(row.get("missing_fields") or [])})
    return output.getvalue()


def _row_for_unit(unit: Any) -> SpecReadinessRow:
    issues: list[SpecReadinessIssue] = []
    for field in REQUIRED_BLOCKER_FIELDS:
        if _is_missing(getattr(unit, field, None)):
            issues.append(SpecReadinessIssue(field, "blocker", f"{field} is required before tact spec generation."))
    for field in REQUIRED_WARNING_FIELDS:
        if _is_missing(getattr(unit, field, None)):
            issues.append(SpecReadinessIssue(field, "warning", f"{field} improves generated spec quality."))

    blockers = sum(1 for issue in issues if issue.severity == "blocker")
    warnings = sum(1 for issue in issues if issue.severity == "warning")
    band = "blocked" if blockers else "warning" if warnings else "ready"
    return SpecReadinessRow(
        unit_id=str(getattr(unit, "id", "") or ""),
        title=str(getattr(unit, "title", "") or ""),
        missing_fields=tuple(issue.field for issue in issues),
        blocker_count=blockers,
        warning_count=warnings,
        readiness_band=band,
        issues=tuple(issues),
    )


def _append_section(lines: list[str], title: str, rows_value: Any) -> None:
    lines.extend([f"## {title}", "", "| Unit | Title | Missing Fields | Blockers | Warnings | Band |", "| --- | --- | --- | ---: | ---: | --- |"])
    rows = _sorted_row_maps(rows_value)
    if rows:
        for row in rows:
            lines.append(
                "| `{}` | {} | {} | {} | {} | {} |".format(
                    row.get("unit_id") or "",
                    row.get("title") or "",
                    ", ".join(row.get("missing_fields") or []) or "none",
                    row.get("blocker_count", 0),
                    row.get("warning_count", 0),
                    row.get("readiness_band") or "",
                )
            )
    else:
        lines.append("| none |  | none | 0 | 0 |  |")
    lines.append("")


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip() or value.strip().lower() in {"unknown", "unspecified", "both"}
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _row_sort_key(row: SpecReadinessRow) -> tuple[int, int, int, str]:
    return (_READINESS_ORDER[row.readiness_band], -row.blocker_count, -row.warning_count, row.unit_id)


def _sorted_row_maps(value: Any) -> list[Mapping[str, Any]]:
    rows = _list_of_maps(value)
    return sorted(
        rows,
        key=lambda row: (
            _READINESS_ORDER.get(str(row.get("readiness_band")), len(_READINESS_ORDER)),
            -_int(row.get("blocker_count")),
            -_int(row.get("warning_count")),
            str(row.get("unit_id") or ""),
        ),
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_maps(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
