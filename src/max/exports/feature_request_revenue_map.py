"""Feature request revenue map export."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.feature_request_revenue_map.v1"
KIND = "max.feature_request_revenue_map"


def build_feature_request_revenue_map_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    units = store.get_buildable_units(limit=1000, domain=domain)
    grouped = _group(units)
    ranked = sorted(grouped, key=lambda row: (-row["ranking_score"], -row["pipeline_value_usd"], -row["account_count"], row["feature_request"]))
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "feature_request_revenue_map", "domain_filter": domain},
        "summary": {"feature_request_count": len(ranked), "total_pipeline_value_usd": round(sum(row["pipeline_value_usd"] for row in ranked), 2)},
        "feature_requests": ranked,
    }


def render_feature_request_revenue_map_markdown(report: dict[str, Any]) -> str:
    lines = ["# Feature Request Revenue Map", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Ranked Requests", ""]
    if report.get("feature_requests"):
        lines.extend(["| Rank | Feature | Value | Accounts | Urgency | Evidence |", "|------|---------|-------|----------|---------|----------|"])
        for row in report["feature_requests"]:
            lines.append(f"| {row['rank']} | {_md(row['feature_request'])} | ${row['pipeline_value_usd']:,.0f} | {row['account_count']} | {row['urgency']} | {row['evidence_strength']} |")
    else:
        lines.append("- No feature requests available.")
    return "\n".join(lines).rstrip() + "\n"


def render_feature_request_revenue_map_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def _group(units: list[Any]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for unit in units:
        metadata = getattr(unit, "metadata", None) if isinstance(getattr(unit, "metadata", None), dict) else {}
        feature = _text(metadata.get("feature_request") or metadata.get("feature") or getattr(unit, "title", "Untitled"))
        key = feature.lower().strip()
        buckets[key].append({
            "feature_request": feature,
            "account": _text(metadata.get("account") or metadata.get("customer")),
            "pipeline_value_usd": _number(metadata.get("pipeline_value_usd") or metadata.get("arr_usd") or metadata.get("revenue_usd")),
            "retention_risk_usd": _number(metadata.get("retention_risk_usd")),
            "urgency_score": _urgency(metadata.get("urgency") or metadata.get("priority")),
            "evidence": _list(metadata.get("evidence_references") or metadata.get("evidence")),
        })
    rows = []
    for items in buckets.values():
        accounts = sorted({item["account"] for item in items if item["account"]})
        evidence_count = sum(len(item["evidence"]) for item in items)
        value = round(sum(item["pipeline_value_usd"] + item["retention_risk_usd"] for item in items), 2)
        urgency_score = max((item["urgency_score"] for item in items), default=0)
        strength = "strong" if evidence_count >= 3 else "moderate" if evidence_count >= 1 else "weak"
        rows.append({
            "rank": 0,
            "feature_request": items[0]["feature_request"],
            "accounts": accounts,
            "account_count": len(accounts) or len(items),
            "pipeline_value_usd": value,
            "urgency": "high" if urgency_score >= 3 else "medium" if urgency_score == 2 else "low",
            "evidence_strength": strength,
            "evidence_count": evidence_count,
            "ranking_score": round(value / 1000 + (len(accounts) or len(items)) * 10 + urgency_score * 15 + evidence_count * 5, 2),
        })
    return rows


def _urgency(value: Any) -> int:
    text = _text(value).lower()
    if any(word in text for word in ("critical", "high", "urgent")):
        return 3
    if any(word in text for word in ("medium", "soon")):
        return 2
    return 1 if text else 0


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
