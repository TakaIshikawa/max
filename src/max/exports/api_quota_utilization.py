"""API quota utilization export for usage governance."""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.api_quota_utilization.v1"
KIND = "max.api_quota_utilization"

_ROW_FIELDS = [
    "idea_id",
    "title",
    "domain",
    "owner",
    "rate_limit_tier",
    "api_calls_monthly",
    "quota_limit_monthly",
    "utilization_pct",
    "projected_overage",
    "quota_cost_per_1k",
    "estimated_overage_cost",
    "risk_level",
]


def build_api_quota_utilization_export(
    store: Store,
    domain: str | None = None,
) -> dict[str, Any]:
    """Build API quota utilization report from buildable unit metadata."""
    units = store.get_buildable_units(limit=1000, domain=domain)
    rows = [_build_quota_row(unit) for unit in units]
    rows.sort(key=lambda row: (_risk_rank(row["risk_level"]), -row["utilization_pct"], row["owner"], row["idea_id"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "api_quota_utilization",
            "domain_filter": domain,
        },
        "quota_row_count": len(rows),
        "quota_rows": rows,
        "summary": _build_summary(rows),
    }


def render_api_quota_utilization_markdown(report: dict[str, Any]) -> str:
    """Render API quota utilization report as Markdown."""
    summary = report.get("summary", {})
    lines = [
        "# API Quota Utilization",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        f"Units analyzed: {report.get('quota_row_count', 0)}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total API calls | {summary.get('total_api_calls_monthly', 0):,.0f} |",
        f"| Total quota limit | {summary.get('total_quota_limit_monthly', 0):,.0f} |",
        f"| Projected overage | {summary.get('total_projected_overage', 0):,.0f} |",
        f"| Estimated overage cost | ${summary.get('total_estimated_overage_cost', 0.0):,.2f} |",
        f"| High risk units | {summary.get('risk_counts', {}).get('high', 0)} |",
        "",
        "## Unit Quotas",
        "",
    ]

    if report.get("quota_rows"):
        lines.extend([
            "| Unit | Owner | Domain | Tier | Calls | Limit | Utilization | Overage | Cost | Risk |",
            "|------|-------|--------|------|-------|-------|-------------|---------|------|------|",
        ])
        for row in report["quota_rows"]:
            lines.append(
                f"| {row['title']} | {row['owner']} | {row['domain']} | {row['rate_limit_tier']} | "
                f"{row['api_calls_monthly']:,.0f} | {row['quota_limit_monthly']:,.0f} | "
                f"{row['utilization_pct']:.1f}% | {row['projected_overage']:,.0f} | "
                f"${row['estimated_overage_cost']:,.2f} | {row['risk_level']} |"
            )
    else:
        lines.append("- No buildable units available for quota analysis.")

    lines.extend([
        "",
        "## Owner Rollup",
        "",
        "| Owner | Units | Calls | Limit | Overage | Cost | Highest Risk |",
        "|-------|-------|-------|-------|---------|------|--------------|",
    ])
    for owner in summary.get("by_owner", []):
        lines.append(
            f"| {owner['owner']} | {owner['unit_count']} | {owner['api_calls_monthly']:,.0f} | "
            f"{owner['quota_limit_monthly']:,.0f} | {owner['projected_overage']:,.0f} | "
            f"${owner['estimated_overage_cost']:,.2f} | {owner['highest_risk_level']} |"
        )

    lines.extend([
        "",
        "## Domain Rollup",
        "",
        "| Domain | Units | Calls | Limit | Overage | Cost | Highest Risk |",
        "|--------|-------|-------|-------|---------|------|--------------|",
    ])
    for domain_row in summary.get("by_domain", []):
        lines.append(
            f"| {domain_row['domain']} | {domain_row['unit_count']} | {domain_row['api_calls_monthly']:,.0f} | "
            f"{domain_row['quota_limit_monthly']:,.0f} | {domain_row['projected_overage']:,.0f} | "
            f"${domain_row['estimated_overage_cost']:,.2f} | {domain_row['highest_risk_level']} |"
        )

    return "\n".join(lines).rstrip() + "\n"


def render_api_quota_utilization_json(report: dict[str, Any]) -> str:
    """Render API quota utilization report as stable formatted JSON."""
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_api_quota_utilization_csv(report: dict[str, Any]) -> str:
    """Render API quota rows as CSV."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_ROW_FIELDS)
    writer.writeheader()
    for row in report.get("quota_rows", []):
        writer.writerow({field: row.get(field) for field in _ROW_FIELDS})
    return output.getvalue()


def _build_quota_row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    api_calls = max(_number_from_metadata(metadata, ["api_calls_monthly", "monthly_api_calls"], 0.0), 0.0)
    quota_limit = max(_number_from_metadata(metadata, ["quota_limit_monthly", "monthly_quota_limit"], 0.0), 0.0)
    cost_per_1k = max(_number_from_metadata(metadata, ["quota_cost_per_1k", "overage_cost_per_1k"], 0.0), 0.0)
    utilization = round((api_calls / quota_limit) * 100, 1) if quota_limit > 0 else 0.0
    overage = max(api_calls - quota_limit, 0.0) if quota_limit > 0 else 0.0
    overage_cost = round((overage / 1000.0) * cost_per_1k, 2)

    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": str(getattr(unit, "title", "Untitled")),
        "domain": str(getattr(unit, "domain", "") or "general"),
        "owner": _string_from_metadata(metadata, ["owner", "quota_owner"], "unassigned"),
        "rate_limit_tier": _string_from_metadata(metadata, ["rate_limit_tier", "api_tier"], "standard"),
        "api_calls_monthly": round(api_calls, 2),
        "quota_limit_monthly": round(quota_limit, 2),
        "utilization_pct": utilization,
        "projected_overage": round(overage, 2),
        "quota_cost_per_1k": round(cost_per_1k, 2),
        "estimated_overage_cost": overage_cost,
        "risk_level": _risk_level(utilization, overage, quota_limit),
    }


def _build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_api_calls_monthly": round(sum(row["api_calls_monthly"] for row in rows), 2),
        "total_quota_limit_monthly": round(sum(row["quota_limit_monthly"] for row in rows), 2),
        "total_projected_overage": round(sum(row["projected_overage"] for row in rows), 2),
        "total_estimated_overage_cost": round(sum(row["estimated_overage_cost"] for row in rows), 2),
        "risk_counts": {level: sum(1 for row in rows if row["risk_level"] == level) for level in ["low", "medium", "high"]},
        "by_owner": _rollups(rows, "owner"),
        "by_domain": _rollups(rows, "domain"),
    }


def _rollups(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "unit_count": 0,
            "api_calls_monthly": 0.0,
            "quota_limit_monthly": 0.0,
            "projected_overage": 0.0,
            "estimated_overage_cost": 0.0,
            "highest_risk_level": "low",
        }
    )
    for row in rows:
        group = groups[str(row[key])]
        group["unit_count"] += 1
        group["api_calls_monthly"] += row["api_calls_monthly"]
        group["quota_limit_monthly"] += row["quota_limit_monthly"]
        group["projected_overage"] += row["projected_overage"]
        group["estimated_overage_cost"] += row["estimated_overage_cost"]
        if _risk_rank(row["risk_level"]) < _risk_rank(group["highest_risk_level"]):
            group["highest_risk_level"] = row["risk_level"]

    return [
        {
            key: name,
            "unit_count": int(values["unit_count"]),
            "api_calls_monthly": round(values["api_calls_monthly"], 2),
            "quota_limit_monthly": round(values["quota_limit_monthly"], 2),
            "projected_overage": round(values["projected_overage"], 2),
            "estimated_overage_cost": round(values["estimated_overage_cost"], 2),
            "highest_risk_level": values["highest_risk_level"],
        }
        for name, values in sorted(groups.items())
    ]


def _risk_level(utilization_pct: float, overage: float, quota_limit: float) -> str:
    if quota_limit <= 0:
        return "low"
    if overage > 0 or utilization_pct >= 95:
        return "high"
    if utilization_pct >= 80:
        return "medium"
    return "low"


def _risk_rank(value: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(value, 3)


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _number_from_metadata(metadata: dict[str, Any], keys: list[str], default: float) -> float:
    for key in keys:
        if key in metadata:
            return _coerce_float(metadata[key], default)
    quota = metadata.get("api_quota")
    if isinstance(quota, dict):
        for key in keys:
            if key in quota:
                return _coerce_float(quota[key], default)
    return default


def _string_from_metadata(metadata: dict[str, Any], keys: list[str], default: str) -> str:
    for key in keys:
        value = metadata.get(key)
        if value is not None and value != "":
            return str(value).strip()
    quota = metadata.get("api_quota")
    if isinstance(quota, dict):
        for key in keys:
            value = quota.get(key)
            if value is not None and value != "":
                return str(value).strip()
    return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
