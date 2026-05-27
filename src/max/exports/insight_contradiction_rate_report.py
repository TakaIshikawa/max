"""Insight contradiction rate export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

OPPOSING = {("positive", "negative"), ("supporting", "opposing"), ("pro", "con")}


def build_insight_contradiction_rate_report(records: Iterable[Any], *, high_risk_threshold: float = 0.3) -> dict[str, Any]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    seen: dict[tuple[str, str], set[str]] = {}
    contradictory: dict[tuple[str, str], set[str]] = {}
    for raw in records:
        profile = _text(_get(raw, "profile")) or "unknown-profile"
        domain = _text(_get(raw, "domain")) or "unknown-domain"
        key = (profile, domain)
        insight_id = _text(_get(raw, "insight_id") or _get(raw, "id")) or "unknown-insight"
        row = groups.setdefault(key, {"profile": profile, "domain": domain, "total_insights": 0, "contradictory_insight_count": 0, "contradiction_rate": 0.0, "top_contradictory_insight_ids": [], "high_risk": False})
        seen.setdefault(key, set()).add(insight_id)
        labels = {_norm(item) for item in _list(_get(raw, "evidence_labels") or _get(raw, "labels"))}
        roles = {_norm(item) for item in _list(_get(raw, "source_roles") or _get(raw, "roles"))}
        if _has_opposition(labels) or _has_opposition(roles):
            contradictory.setdefault(key, set()).add(insight_id)
    rows = []
    for key, row in groups.items():
        total = len(seen.get(key, set()))
        count = len(contradictory.get(key, set()))
        row["total_insights"] = total
        row["contradictory_insight_count"] = count
        row["contradiction_rate"] = round(count / total, 4) if total else 0.0
        row["top_contradictory_insight_ids"] = sorted(contradictory.get(key, set()))[:5]
        row["high_risk"] = row["contradiction_rate"] >= high_risk_threshold
        rows.append(row)
    rows.sort(key=lambda row: (row["profile"].lower(), row["domain"].lower()))
    return {"schema_version": "max.insight_contradiction_rate_report.v1", "kind": "max.insight_contradiction_rate_report", "summary": {"group_count": len(rows), "flagged_group_count": sum(1 for row in rows if row["high_risk"])}, "groups": rows, "flagged_groups": [row for row in rows if row["high_risk"]]}


def render_insight_contradiction_rate_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_insight_contradiction_rate_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Insight Contradiction Rate Report", "", "| Profile | Domain | Insights | Contradictions | Rate | Risk |", "| --- | --- | ---: | ---: | ---: | --- |"]
    for row in report.get("groups", []):
        lines.append(f"| {row['profile']} | {row['domain']} | {row['total_insights']} | {row['contradictory_insight_count']} | {row['contradiction_rate']} | {'high-risk' if row['high_risk'] else 'normal'} |")
    return "\n".join(lines).rstrip() + "\n"


def _has_opposition(values: set[str]) -> bool:
    return any(left in values and right in values for left, right in OPPOSING)


def _get(raw: Any, key: str) -> Any:
    return raw.get(key) if isinstance(raw, dict) else getattr(raw, key, None)


def _list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    return list(value) if isinstance(value, (list, tuple, set)) else [value]


def _norm(value: Any) -> str:
    return _text(value).lower().replace(" ", "_").replace("-", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
