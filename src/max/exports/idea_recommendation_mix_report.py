"""Idea recommendation mix export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

RECOMMENDATIONS = ("approve", "review", "reject", "defer")


def build_idea_recommendation_mix_report(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for raw in records:
        key = (_text(raw.get("profile")) or "unknown-profile", _text(raw.get("evaluator")) or "unknown-evaluator", _text(raw.get("source_mode")) or _text(raw.get("mode")) or "unknown-source-mode")
        row = groups.setdefault(key, {"profile": key[0], "evaluator": key[1], "source_mode": key[2], "recommendation_counts": {name: 0 for name in RECOMMENDATIONS}})
        row["recommendation_counts"][_recommendation(raw.get("recommendation") or raw.get("decision"))] += _int(raw.get("count") or 1)
    rows = []
    for row in groups.values():
        total = sum(row["recommendation_counts"].values())
        approvals = row["recommendation_counts"]["approve"]
        rejects = row["recommendation_counts"]["reject"]
        row["total_count"] = total
        row["approval_rate"] = round(approvals / total, 4) if total else 0.0
        row["rejection_rate"] = round(rejects / total, 4) if total else 0.0
        row["mix_status"] = "approval_heavy" if row["approval_rate"] >= 0.7 else "rejection_heavy" if row["rejection_rate"] >= 0.4 else "balanced"
        rows.append(row)
    rows.sort(key=lambda row: (row["approval_rate"], row["profile"].lower(), row["evaluator"].lower(), row["source_mode"].lower()))
    return rows


def render_idea_recommendation_mix_report_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, indent=2, sort_keys=True, default=str) + "\n"


def render_idea_recommendation_mix_report_markdown(rows: list[dict[str, Any]]) -> str:
    lines = ["# Idea Recommendation Mix Report", "", "| Profile | Evaluator | Source mode | Total | Approval rate | Rejection rate | Status |", "| --- | --- | --- | ---: | ---: | ---: | --- |"]
    for row in rows:
        lines.append(f"| {row['profile']} | {row['evaluator']} | {row['source_mode']} | {row['total_count']} | {row['approval_rate']} | {row['rejection_rate']} | {row['mix_status']} |")
    return "\n".join(lines).rstrip() + "\n"


def _recommendation(value: Any) -> str:
    text = _text(value).lower().replace(" ", "_").replace("-", "_")
    return {"approved": "approve", "accept": "approve", "accepted": "approve", "needs_review": "review", "manual_review": "review", "rejected": "reject", "deny": "reject", "denied": "reject", "deferred": "defer", "hold": "defer"}.get(text, text if text in RECOMMENDATIONS else "review")


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
