"""Evidence trace depth export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

LINKS = ("signal_ids", "insight_ids", "unit_ids", "spec_id")


def build_evidence_trace_depth_report(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for raw in records:
        values = {
            "signal_ids": _list(raw.get("signal_ids") or raw.get("signals")),
            "insight_ids": _list(raw.get("insight_ids") or raw.get("insights")),
            "unit_ids": _list(raw.get("unit_ids") or raw.get("units") or raw.get("buildable_unit_ids")),
            "spec_id": _list(raw.get("spec_id") or raw.get("spec_ids") or raw.get("tact_spec_id")),
        }
        present = sum(1 for value in values.values() if value)
        missing = len(LINKS) - present
        evidence_count = sum(len(value) for value in values.values())
        risk = "high" if missing >= 2 else "medium" if missing == 1 else "low"
        rows.append({"idea_id": _text(raw.get("idea_id")) or "unknown-idea", "spec_id": values["spec_id"][0] if values["spec_id"] else "missing-spec", "trace_depth": present, "missing_link_count": missing, "evidence_count": evidence_count, "risk_level": risk, "recommended_action": _action(risk), "signal_ids": values["signal_ids"], "insight_ids": values["insight_ids"], "unit_ids": values["unit_ids"], "spec_ids": values["spec_id"]})
    rows.sort(key=lambda row: ({"high": 0, "medium": 1, "low": 2}[row["risk_level"]], row["spec_id"].lower(), row["idea_id"].lower()))
    return rows


def render_evidence_trace_depth_report_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, indent=2, sort_keys=True, default=str) + "\n"


def render_evidence_trace_depth_report_markdown(rows: list[dict[str, Any]]) -> str:
    lines = ["# Evidence Trace Depth Report", "", "| Idea | Spec | Depth | Missing links | Evidence | Risk | Action |", "| --- | --- | ---: | ---: | ---: | --- | --- |"]
    for row in rows:
        lines.append(f"| {row['idea_id']} | {row['spec_id']} | {row['trace_depth']} | {row['missing_link_count']} | {row['evidence_count']} | {row['risk_level']} | {row['recommended_action']} |")
    return "\n".join(lines).rstrip() + "\n"


def _action(risk: str) -> str:
    return {"high": "Rebuild missing trace links before spec handoff.", "medium": "Fill the remaining trace gap before publication.", "low": "Trace is complete enough for handoff."}[risk]


def _list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple, set)):
        return sorted({_text(item) for item in value if _text(item)})
    return [_text(value)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
