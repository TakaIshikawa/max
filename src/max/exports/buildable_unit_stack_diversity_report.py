"""Buildable unit stack diversity export report."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.buildable_unit_stack_diversity_report.v1"
KIND = "max.buildable_unit_stack_diversity_report"


def build_buildable_unit_stack_diversity_report_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    units = list(store.get_buildable_units(limit=1000, domain=domain))
    unit_rows = [_unit_row(unit) for unit in units]
    technology_rows = _technology_rows(unit_rows)
    overused = [row for row in technology_rows if row["concentration_warning"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "buildable_unit_stack_diversity_report", "domain_filter": domain},
        "summary": {
            "unit_count": len(unit_rows),
            "technology_count": len(technology_rows),
            "overused_technology_count": len(overused),
            "diversity_score": _diversity_score(technology_rows),
        },
        "technology_rows": technology_rows,
        "unit_rows": unit_rows,
        "overused_stacks": overused,
        "underrepresented_alternatives": [row for row in technology_rows if row["usage_count"] == 1],
    }


def render_buildable_unit_stack_diversity_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_buildable_unit_stack_diversity_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Buildable Unit Stack Diversity Report", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Technology Concentration", ""]
    rows = report.get("technology_rows") or []
    if rows:
        lines.extend(["| Technology | Usage | Categories | Warning |", "|------------|-------|------------|---------|"])
        for row in rows:
            lines.append(f"| {_md(row['technology'])} | {row['usage_count']} ({row['percentage']}%) | {_md(', '.join(row['categories']))} | {_md(row['concentration_warning'])} |")
    else:
        lines.append("- No stack metadata found.")
    lines.extend(["", "## Underrepresented Alternatives", ""])
    alternatives = report.get("underrepresented_alternatives") or []
    lines.extend([f"- {row['technology']} ({', '.join(row['categories'])})" for row in alternatives] or ["- No underrepresented alternatives detected."])
    return "\n".join(lines).rstrip() + "\n"


def _unit_row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    categories = {
        "language": _list(metadata.get("languages") or metadata.get("language")),
        "framework": _list(metadata.get("frameworks") or metadata.get("framework")),
        "stack": _list(metadata.get("stacks") or metadata.get("stack")),
        "database": _list(metadata.get("databases") or metadata.get("database")),
        "platform": _list(metadata.get("platforms") or metadata.get("platform")),
    }
    technologies = sorted({item for values in categories.values() for item in values}, key=str.casefold)
    return {
        "unit_id": str(getattr(unit, "id", "")),
        "title": _text(getattr(unit, "title", "")) or str(getattr(unit, "id", "")),
        "owner": _text(metadata.get("owner")) or "Unassigned",
        "technologies": technologies,
        "categories": {key: values for key, values in categories.items() if values},
        "recommended_action": "Add stack metadata" if not technologies else "Monitor stack diversity",
    }


def _technology_rows(unit_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total = len(unit_rows)
    categories: dict[str, set[str]] = defaultdict(set)
    counts: dict[str, int] = defaultdict(int)
    for row in unit_rows:
        for category, values in row["categories"].items():
            for value in values:
                categories[value].add(category)
        for value in row["technologies"]:
            counts[value] += 1
    rows = []
    for technology, count in counts.items():
        percentage = round((count / total) * 100, 2) if total else 0.0
        warning = "overused stack" if percentage >= 60 and count > 1 else ""
        rows.append({"technology": technology, "usage_count": count, "percentage": percentage, "categories": sorted(categories[technology]), "concentration_warning": warning})
    rows.sort(key=lambda row: (-row["percentage"], -row["usage_count"], row["technology"].casefold()))
    return rows


def _diversity_score(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return round(100 - max(row["percentage"] for row in rows), 2)


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return sorted({_text(item) for item in value if _text(item)}, key=str.casefold)
    if isinstance(value, str) and ("," in value or ";" in value):
        return sorted({_text(item) for item in value.replace(";", ",").split(",") if _text(item)}, key=str.casefold)
    text = _text(value)
    return [text] if text else []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
