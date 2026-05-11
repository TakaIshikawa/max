"""Customer success QBR export for account outcome reviews."""

from __future__ import annotations

import csv
import io
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.customer_success_qbr.v1"
KIND = "max.customer_success_qbr"

_FIELDS = ["account_name", "segment", "health_score", "health_band", "usage_growth", "open_risks", "achieved_outcomes", "renewal_date", "expansion_value", "idea_id", "title"]


def build_customer_success_qbr_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (row["renewal_date"] or "9999-99-99", row["segment"], row["account_name"], row["idea_id"]))
    risks = [risk for row in rows for risk in row["risks"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "customer_success_qbr", "domain_filter": domain},
        "account_count": len(rows),
        "summary": {
            "account_count": len(rows),
            "average_health_score": round(sum(row["health_score"] for row in rows) / len(rows), 1) if rows else 0.0,
            "average_usage_growth": round(sum(row["usage_growth"] for row in rows) / len(rows), 3) if rows else 0.0,
            "risk_count": len(risks),
            "expansion_value": round(sum(row["expansion_value"] for row in rows), 2),
        },
        "risk_rollups": dict(sorted(Counter(row["segment"] for row in rows if row["open_risks"]).items())),
        "expansion_rollups": _expansion_rollups(rows),
        "risks": risks,
        "accounts": rows,
    }


def render_customer_success_qbr_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Customer Success QBR",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Executive Summary",
        "",
        f"- Accounts: {summary.get('account_count', 0)}",
        f"- Average health: {summary.get('average_health_score', 0.0):.1f}",
        f"- Expansion value: ${summary.get('expansion_value', 0.0):,.0f}",
        f"- Open risks: {summary.get('risk_count', 0)}",
        "",
        "## Account Table",
        "",
        "| Account | Segment | Health | Growth | Renewal | Expansion | Risks |",
        "|---------|---------|--------|--------|---------|-----------|-------|",
    ]
    for row in report.get("accounts", []):
        lines.append(f"| {row['account_name']} | {row['segment']} | {row['health_score']:.1f} | {row['usage_growth']:.1%} | {row['renewal_date'] or 'unknown'} | ${row['expansion_value']:,.0f} | {row['open_risks']} |")
    lines.extend(["", "## Risks", ""])
    for risk in report.get("risks", []) or [{"account_name": "No open risks", "risk": ""}]:
        lines.append(f"- {risk['account_name']}: {risk['risk']}".rstrip(": "))
    return "\n".join(lines).rstrip() + "\n"


def render_customer_success_qbr_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_customer_success_qbr_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_FIELDS)
    writer.writeheader()
    for row in report.get("accounts", []):
        writer.writerow({field: row.get(field) for field in _FIELDS})
    return output.getvalue()


def _row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    risks = _list(metadata.get("open_risks"))
    outcomes = _list(metadata.get("achieved_outcomes"))
    health = min(max(_number(metadata, "health_score", 0.0), 0.0), 100.0)
    account = _string(metadata, "account_name", str(getattr(unit, "title", "Unknown account")))
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": str(getattr(unit, "title", "Untitled")),
        "account_name": account,
        "segment": _string(metadata, "segment", "unknown").lower(),
        "health_score": round(health, 1),
        "health_band": "healthy" if health >= 75 else "watch" if health >= 50 else "at_risk",
        "usage_growth": round(_number(metadata, "usage_growth", 0.0), 3),
        "open_risks": len(risks),
        "risks": [{"account_name": account, "risk": risk} for risk in risks],
        "achieved_outcomes": len(outcomes),
        "outcomes": outcomes,
        "renewal_date": _string(metadata, "renewal_date", "") or None,
        "expansion_value": round(max(_number(metadata, "expansion_value", 0.0), 0.0), 2),
    }


def _expansion_rollups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["segment"]].append(row)
    return [{"segment": segment, "account_count": len(items), "expansion_value": round(sum(item["expansion_value"] for item in items), 2)} for segment, items in sorted(groups.items())]


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _number(metadata: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(metadata.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _string(metadata: dict[str, Any], key: str, default: str) -> str:
    value = metadata.get(key, default)
    return str(value).strip() if value not in (None, "") else default


def _list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]
