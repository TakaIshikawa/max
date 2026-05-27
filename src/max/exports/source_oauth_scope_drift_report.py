"""Source OAuth scope drift export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.source_oauth_scope_drift_report.v1"
KIND = "max.source_oauth_scope_drift_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"
RISK_RANK = {"critical": 0, "warning": 1, "none": 2}


def build_source_oauth_scope_drift_report(records: Iterable[dict[str, Any]] | dict[str, Any], *, title: str = "Source OAuth Scope Drift Report", generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    source = records.get("records") if isinstance(records, dict) else records
    for raw in source or []:
        if isinstance(raw, dict):
            groups[(_text(raw.get("source") or raw.get("adapter")) or "unknown-source", _text(raw.get("integration") or raw.get("integration_id")) or "unknown-integration")].append(raw)
    rows = [_row(source, integration, items) for (source, integration), items in groups.items()]
    rows.sort(key=lambda row: (RISK_RANK[row["risk_level"]], row["source"].lower(), row["integration"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT, "title": _text(title) or "Source OAuth Scope Drift Report", "summary": {"integration_count": len(rows), "drifted_integration_count": sum(1 for row in rows if row["missing_scopes"] or row["extra_scopes"]), "missing_scope_count": sum(len(row["missing_scopes"]) for row in rows), "extra_scope_count": sum(len(row["extra_scopes"]) for row in rows), "critical_count": sum(1 for row in rows if row["risk_level"] == "critical")}, "drift_rows": rows}


def render_source_oauth_scope_drift_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_source_oauth_scope_drift_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report.get('title') or 'Source OAuth Scope Drift Report'}", "", "## Scope Drift", ""]
    lines.extend([f"- {r['source']} {r['integration']}: missing={', '.join(r['missing_scopes']) or 'none'} extra={', '.join(r['extra_scopes']) or 'none'} ({r['risk_level']})" for r in report.get("drift_rows") or []] or ["- No OAuth scope drift detected."])
    return "\n".join(lines).rstrip() + "\n"


def _row(source: str, integration: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    required = set().union(*[_scope_set(item.get("required_scopes")) for item in items]) if items else set()
    observed = set().union(*[_scope_set(item.get("observed_scopes") or item.get("granted_scopes")) for item in items]) if items else set()
    active_ops = sum(_int(item.get("affected_operation_count", item.get("active_operation_count", item.get("operation_count", 0)))) for item in items)
    missing = sorted(required - observed)
    extra = sorted(observed - required)
    risk = "critical" if missing and active_ops else ("warning" if missing or extra else "none")
    last_observed = max((_text(item.get("last_observed_at")) for item in items), default="") or None
    return {"source": source, "integration": integration, "missing_scopes": missing, "extra_scopes": extra, "last_observed_at": last_observed, "affected_operation_count": active_ops, "risk_level": risk}


def _scope_set(value: Any) -> set[str]:
    if isinstance(value, str):
        return {_text(part) for part in value.split(",") if _text(part)}
    if isinstance(value, list):
        return {_text(item) for item in value if _text(item)}
    return set()


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
