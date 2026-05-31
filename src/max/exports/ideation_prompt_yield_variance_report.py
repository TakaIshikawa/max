"""Ideation prompt yield variance export report."""

from __future__ import annotations

import json
from collections import defaultdict
from statistics import median
from typing import Any, Iterable

SCHEMA_VERSION = "max.ideation_prompt_yield_variance_report.v1"
KIND = "max.ideation_prompt_yield_variance_report"
DEFAULT_GENERATED_AT = "2026-05-31T00:00:00+00:00"
SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def generate_ideation_prompt_yield_variance_report(records: Iterable[dict[str, Any]], *, generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    groups: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"attempts": 0, "generated": 0, "approved": 0})
    for index, item in enumerate(records, start=1):
        key = (_text(item.get("profile")) or "default", _text(item.get("prompt_template") or item.get("template")) or f"template-{index}")
        groups[key]["attempts"] += _int(item.get("attempts") or item.get("attempt_count") or 1)
        groups[key]["generated"] += _int(item.get("generated_units") or item.get("generated_count"))
        groups[key]["approved"] += _int(item.get("approved_units") or item.get("approved_count"))
    medians = {profile: median([values["generated"] / values["attempts"] if values["attempts"] else 0.0 for (row_profile, _), values in groups.items() if row_profile == profile]) for profile in {key[0] for key in groups}}
    rows = []
    for (profile, template), values in groups.items():
        attempts = values["attempts"]
        generated = values["generated"]
        approved = values["approved"]
        yield_rate = generated / attempts if attempts else 0.0
        approval_rate = approved / generated if generated else 0.0
        variance = yield_rate - medians[profile]
        severity = "critical" if variance <= -0.25 else ("warn" if variance < 0 else "ok")
        rows.append({"profile": profile, "prompt_template": template, "attempts": attempts, "generated_units": generated, "approved_units": approved, "yield_rate": round(yield_rate, 4), "approval_rate": round(approval_rate, 4), "median_yield_rate": round(medians[profile], 4), "variance": round(variance, 4), "severity": severity, "recommended_action": "Retire or redesign prompt template." if severity == "critical" else ("Review prompt examples and constraints." if severity == "warn" else "No action required.")})
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], row["variance"], row["profile"], row["prompt_template"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": generated_at, "summary": {"template_count": len(rows), "underperforming_template_count": sum(1 for row in rows if row["variance"] < 0), "generated_unit_count": sum(row["generated_units"] for row in rows)}, "rows": rows}


def render_ideation_prompt_yield_variance_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_ideation_prompt_yield_variance_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Ideation Prompt Yield Variance Report", "", f"Underperforming templates: {report.get('summary', {}).get('underperforming_template_count', 0)}", ""]
    for row in report.get("rows") or []:
        lines.append(f"- {row['profile']} / {row['prompt_template']}: yield {row['yield_rate']}, variance {row['variance']} ({row['severity']})")
    return "\n".join(lines).rstrip() + "\n"


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
