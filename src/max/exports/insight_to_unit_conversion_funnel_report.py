"""Insight to unit conversion funnel export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

STAGES = ("insight", "candidate_unit", "evaluated_unit", "approved_unit", "spec_generated")


def build_insight_to_unit_conversion_funnel_report(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in records:
        key = (_text(raw.get("profile")) or "unknown-profile", _text(raw.get("domain")) or "unknown-domain")
        row = groups.setdefault(key, {"profile": key[0], "domain": key[1], **{f"{stage}_count": 0 for stage in STAGES}})
        stage = _stage(raw)
        reached = STAGES[: STAGES.index(stage) + 1]
        count = _int(raw.get("count") or raw.get("item_count") or 1)
        for name in reached:
            row[f"{name}_count"] += count
    rows = []
    for row in groups.values():
        insight_count = row["insight_count"]
        row["conversion_rate"] = round(row["spec_generated_count"] / insight_count, 4) if insight_count else 0.0
        row["dropoff_stage"] = _dropoff_stage(row)
        row["recommended_action"] = _action(row["dropoff_stage"])
        rows.append(row)
    rows.sort(key=lambda row: (row["profile"].lower(), row["domain"].lower()))
    return rows


def render_insight_to_unit_conversion_funnel_report_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, indent=2, sort_keys=True, default=str) + "\n"


def render_insight_to_unit_conversion_funnel_report_markdown(rows: list[dict[str, Any]]) -> str:
    lines = ["# Insight To Unit Conversion Funnel Report", "", "| Profile | Domain | Insights | Candidates | Evaluated | Approved | Specs | Conversion | Dropoff | Action |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |"]
    for row in rows:
        lines.append(f"| {row['profile']} | {row['domain']} | {row['insight_count']} | {row['candidate_unit_count']} | {row['evaluated_unit_count']} | {row['approved_unit_count']} | {row['spec_generated_count']} | {row['conversion_rate']} | {row['dropoff_stage']} | {row['recommended_action']} |")
    return "\n".join(lines).rstrip() + "\n"


def _stage(raw: dict[str, Any]) -> str:
    value = _text(raw.get("stage") or raw.get("status")).lower().replace("-", "_").replace(" ", "_")
    aliases = {"candidate": "candidate_unit", "unit_candidate": "candidate_unit", "evaluated": "evaluated_unit", "approved": "approved_unit", "spec": "spec_generated", "generated_spec": "spec_generated"}
    return aliases.get(value, value if value in STAGES else "insight")


def _dropoff_stage(row: dict[str, Any]) -> str:
    pairs = list(zip(STAGES, STAGES[1:]))
    drops = [(left, row[f"{left}_count"] - row[f"{right}_count"]) for left, right in pairs]
    stage, drop = max(drops, key=lambda item: (item[1], -STAGES.index(item[0])))
    return stage if drop > 0 else "none"


def _action(stage: str) -> str:
    return {
        "insight": "Prioritize insight triage into candidate units.",
        "candidate_unit": "Add evaluation capacity for candidate units.",
        "evaluated_unit": "Resolve approval criteria for evaluated units.",
        "approved_unit": "Schedule tact spec generation for approved units.",
        "none": "Maintain current conversion flow.",
    }.get(stage, "Review funnel health.")


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
