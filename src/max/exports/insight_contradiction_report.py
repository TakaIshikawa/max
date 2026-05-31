"""Insight contradiction export report."""

from __future__ import annotations

import json
from itertools import combinations
from typing import Any, Iterable

SCHEMA_VERSION = "max.insight_contradiction_report.v1"
KIND = "max.insight_contradiction_report"
DEFAULT_GENERATED_AT = "2026-05-31T00:00:00+00:00"
SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}
OPPOSING_STANCES = {("negative", "positive"), ("against", "for"), ("con", "pro"), ("decrease", "increase"), ("down", "up"), ("false", "true"), ("no", "yes")}


def generate_insight_contradiction_report(records: Iterable[dict[str, Any]], *, generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for index, item in enumerate(records, start=1):
        insight = _insight(item, index)
        grouped.setdefault((insight["profile"], insight["market"], insight["category"], insight["theme"]), []).append(insight)
    rows = []
    for (profile, market, category, theme), insights in grouped.items():
        pairs = [_pair(left, right) for left, right in combinations(insights, 2) if _conflicts(left, right)]
        if pairs:
            severity = min((pair["severity"] for pair in pairs), key=lambda value: SEVERITY_RANK[value])
            rows.append({"profile": profile, "market": market, "category": category, "theme": theme, "severity": severity, "contradiction_count": len(pairs), "pairs": pairs})
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], row["profile"], row["market"], row["category"], row["theme"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": generated_at, "summary": {"group_count": len(rows), "contradiction_count": sum(row["contradiction_count"] for row in rows), "critical_count": sum(1 for row in rows if row["severity"] == "critical")}, "rows": rows}


def render_insight_contradiction_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_insight_contradiction_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Insight Contradiction Report", "", f"Contradictions: {report.get('summary', {}).get('contradiction_count', 0)}", ""]
    if not report.get("rows"):
        lines.append("No insight contradictions found.")
    for row in report.get("rows") or []:
        lines.append(f"## {row['profile']} / {row['category']} / {row['theme']} ({row['severity']})")
        for pair in row["pairs"]:
            lines.append(f"- {pair['left_id']} ({pair['left_evidence_count']} evidence) conflicts with {pair['right_id']} ({pair['right_evidence_count']} evidence): {pair['reason']}")
    return "\n".join(lines).rstrip() + "\n"


def _insight(item: dict[str, Any], index: int) -> dict[str, Any]:
    return {"id": _text(item.get("insight_id") or item.get("id")) or f"insight-{index}", "profile": _text(item.get("profile")) or "default", "market": _text(item.get("market")) or "default", "category": _text(item.get("category")) or "uncategorized", "theme": _text(item.get("theme") or item.get("topic")) or "unthemed", "stance": _norm(item.get("stance") or item.get("stance_label") or item.get("sentiment")), "claim": _norm(item.get("claim") or item.get("claim_label")), "confidence": _float(item.get("confidence")), "evidence_count": len(_list(item.get("evidence_ids") or item.get("evidence"))) or _int(item.get("evidence_count"))}


def _conflicts(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return _opposes(left["stance"], right["stance"]) or _opposes(left["claim"], right["claim"])


def _pair(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    confidence = min(left["confidence"], right["confidence"])
    evidence = min(left["evidence_count"], right["evidence_count"])
    severity = "critical" if confidence >= 0.8 and evidence >= 2 else ("warn" if confidence >= 0.6 or evidence >= 2 else "ok")
    reason = "opposing stance labels" if _opposes(left["stance"], right["stance"]) else "mutually exclusive claims"
    first, second = sorted([left, right], key=lambda item: item["id"])
    return {"left_id": first["id"], "right_id": second["id"], "left_evidence_count": first["evidence_count"], "right_evidence_count": second["evidence_count"], "left_confidence": round(first["confidence"], 3), "right_confidence": round(second["confidence"], 3), "severity": severity, "reason": reason}


def _opposes(left: str, right: str) -> bool:
    return bool(left and right and left != right and tuple(sorted((left, right))) in OPPOSING_STANCES)


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else ([] if value in (None, "") else [value])


def _float(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value or 0)))
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _norm(value: Any) -> str:
    return _text(value).lower().replace("_", "-")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
