"""Spec generation failure taxonomy export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.spec_generation_failure_taxonomy_report.v1"
KIND = "max.spec_generation_failure_taxonomy_report"
DEFAULT_GENERATED_AT = "2026-05-31T00:00:00+00:00"
SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def generate_spec_generation_failure_taxonomy_report(records: Iterable[dict[str, Any]], *, generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = defaultdict(lambda: {"count": 0, "retryable": 0, "last_seen_at": ""})
    for item in records:
        key = (_text(item.get("profile")) or "default", _text(item.get("generator") or item.get("generator_name")) or "generator", _text(item.get("failure_type") or item.get("error_code") or item.get("category")) or "unknown", _text(item.get("stage")) or "unknown")
        groups[key]["count"] += 1
        groups[key]["retryable"] += 1 if bool(item.get("retryable")) else 0
        groups[key]["last_seen_at"] = max(groups[key]["last_seen_at"], _text(item.get("last_seen_at") or item.get("created_at") or item.get("timestamp")))
    rows = []
    for (profile, generator, failure_type, stage), values in groups.items():
        severity = "critical" if values["count"] >= 3 and values["retryable"] < values["count"] else ("warn" if values["count"] else "ok")
        rows.append({"profile": profile, "generator": generator, "failure_type": failure_type, "stage": stage, "failure_count": values["count"], "retryable_count": values["retryable"], "last_seen_at": values["last_seen_at"], "severity": severity, "recommended_action": "Fix non-retryable generator failure path." if severity == "critical" else "Inspect retry and prompt handling."})
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], -row["failure_count"], row["profile"], row["generator"], row["failure_type"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": generated_at, "summary": {"failure_count": sum(row["failure_count"] for row in rows), "failure_type_count": len({row["failure_type"] for row in rows}), "retryable_failure_count": sum(row["retryable_count"] for row in rows), "critical_row_count": sum(1 for row in rows if row["severity"] == "critical")}, "rows": rows}


def render_spec_generation_failure_taxonomy_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_spec_generation_failure_taxonomy_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Spec Generation Failure Taxonomy Report", "", f"Failures: {report.get('summary', {}).get('failure_count', 0)}", ""]
    for row in report.get("rows") or []:
        lines.append(f"- {row['profile']} / {row['generator']} / {row['failure_type']} / {row['stage']}: {row['failure_count']} ({row['severity']})")
    return "\n".join(lines).rstrip() + "\n"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
