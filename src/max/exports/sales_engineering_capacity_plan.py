"""Sales engineering capacity plan export."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.sales_engineering_capacity_plan.v1"
KIND = "max.sales_engineering_capacity_plan"


def build_sales_engineering_capacity_plan_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    units = store.get_buildable_units(limit=1000, domain=domain)
    demands = [_demand_row(unit) for unit in units]
    buckets = _buckets(demands)
    weekly_capacity_hours = _capacity(units)
    total_effort = round(sum(row["estimated_effort_hours"] for row in demands), 1)
    gap = round(total_effort - weekly_capacity_hours, 1)
    risk = "high" if weekly_capacity_hours == 0 and total_effort > 0 else "high" if gap > weekly_capacity_hours * 0.5 else "medium" if gap > 0 else "low"
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "sales_engineering_capacity_plan", "domain_filter": domain},
        "summary": {"demand_count": len(demands), "total_effort_hours": total_effort, "weekly_capacity_hours": weekly_capacity_hours, "capacity_gap_hours": gap, "risk_level": risk},
        "demand_buckets": buckets,
        "demand_rows": sorted(demands, key=lambda row: (-row["estimated_effort_hours"], row["title"], row["idea_id"])),
        "staffing_recommendations": _recommendations(risk, gap),
    }


def render_sales_engineering_capacity_plan_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = ["# Sales Engineering Capacity Plan", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Summary", "", f"- Demand: {summary.get('total_effort_hours', 0):.1f} hours", f"- Capacity: {summary.get('weekly_capacity_hours', 0):.1f} hours", f"- Gap: {summary.get('capacity_gap_hours', 0):.1f} hours", f"- Risk: {summary.get('risk_level', 'low')}", "", "## Demand Buckets", ""]
    if report.get("demand_buckets"):
        lines.extend(["| Bucket | Opportunities | Effort |", "|--------|---------------|--------|"])
        for bucket in report["demand_buckets"]:
            lines.append(f"| {_md(bucket['bucket'])} | {bucket['demand_count']} | {bucket['estimated_effort_hours']:.1f} |")
    else:
        lines.append("- No sales engineering demand identified.")
    return "\n".join(lines).rstrip() + "\n"


def render_sales_engineering_capacity_plan_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def _demand_row(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None) if isinstance(getattr(unit, "metadata", None), dict) else {}
    complexity = _text(metadata.get("implementation_complexity") or metadata.get("complexity")).lower()
    integrations = _list(metadata.get("integrations"))
    support = _text(metadata.get("support_need") or metadata.get("support_load")).lower()
    effort = _number(metadata.get("estimated_effort_hours"))
    if effort == 0:
        effort = 8 + len(integrations) * 4
        if any(word in complexity for word in ("high", "complex", "enterprise")):
            effort += 24
        elif any(word in complexity for word in ("medium", "moderate")):
            effort += 12
        if any(word in support for word in ("high", "custom", "onsite")):
            effort += 10
    return {"idea_id": str(getattr(unit, "id", "")), "title": str(getattr(unit, "title", "Untitled")), "bucket": _bucket(metadata, complexity), "estimated_effort_hours": round(effort, 1), "integrations": integrations, "risk_level": "high" if effort >= 32 else "medium" if effort >= 16 else "low"}


def _buckets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["bucket"]].append(row)
    return sorted(({"bucket": bucket, "demand_count": len(items), "estimated_effort_hours": round(sum(item["estimated_effort_hours"] for item in items), 1)} for bucket, items in grouped.items()), key=lambda row: (-row["estimated_effort_hours"], row["bucket"]))


def _capacity(units: list[Any]) -> float:
    for unit in units:
        metadata = getattr(unit, "metadata", None)
        if isinstance(metadata, dict) and "weekly_capacity_hours" in metadata:
            return _number(metadata["weekly_capacity_hours"])
    return 0.0


def _bucket(metadata: dict[str, Any], complexity: str) -> str:
    explicit = _text(metadata.get("demand_bucket") or metadata.get("pipeline_stage"))
    if explicit:
        return explicit.lower().replace(" ", "_")
    if any(word in complexity for word in ("high", "enterprise", "complex")):
        return "enterprise_complex"
    return "standard"


def _recommendations(risk: str, gap: float) -> list[str]:
    if risk == "low":
        return ["Current sales engineering capacity covers estimated demand."]
    return [f"Add contractor coverage or rebalance presales work for {max(gap, 0):.1f} hours of uncovered demand."]


def _number(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    return [_text(value)] if _text(value) else []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
