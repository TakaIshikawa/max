"""Prompt redaction leak export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.prompt_redaction_leak_report.v1"
KIND = "max.prompt_redaction_leak_report"
SENSITIVE_FIELDS = {"password", "secret", "token", "api_key", "ssn", "email", "phone"}


def generate_prompt_redaction_leak_report(records: Iterable[dict[str, Any]], *, title: str = "Prompt Redaction Leak Report") -> dict[str, Any]:
    groups: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(lambda: {"sample_count": 0, "leak_count": 0, "last_seen_at": ""})
    for raw in records:
        if not isinstance(raw, dict):
            continue
        key = (
            _text(raw.get("profile") or raw.get("profile_id")) or "unknown-profile",
            _text(raw.get("prompt_template") or raw.get("template")) or "unknown-template",
            _text(raw.get("field_name") or raw.get("field")) or "unknown-field",
        )
        group = groups[key]
        group["sample_count"] += 1
        leaked = _bool(raw.get("leaked") or raw.get("redaction_failed") or raw.get("sensitive_token_present")) or _text(raw.get("sensitive_token")) or _text(raw.get("unredacted_value"))
        if leaked:
            group["leak_count"] += 1
        seen = _text(raw.get("seen_at") or raw.get("last_seen_at") or raw.get("created_at"))
        if seen > group["last_seen_at"]:
            group["last_seen_at"] = seen
    rows = [_row(*key, group) for key, group in groups.items() if group["leak_count"]]
    rows.sort(key=lambda row: (_severity_rank(row["severity"]), -row["leak_count"], row["profile"].lower(), row["prompt_template"].lower(), row["field_name"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "title": title, "summary": {"row_count": len(rows), "leak_count": sum(r["leak_count"] for r in rows), "sample_count": sum(r["sample_count"] for r in rows), "critical_row_count": sum(1 for r in rows if r["severity"] == "critical")}, "rows": rows}


def render_prompt_redaction_leak_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_prompt_redaction_leak_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report.get('title') or 'Prompt Redaction Leak Report'}", "", "## Summary", "", f"- Leaks: {report.get('summary', {}).get('leak_count', 0)}", "", "## Leak Rows", ""]
    rows = report.get("rows") or []
    lines.extend([f"- {r['profile']} / {r['prompt_template']} / {r['field_name']}: {r['leak_count']} leaks ({r['severity']})" for r in rows] or ["- No prompt redaction leaks detected."])
    return "\n".join(lines).rstrip() + "\n"


def _row(profile: str, template: str, field: str, group: dict[str, Any]) -> dict[str, Any]:
    sensitive = field.lower() in SENSITIVE_FIELDS or any(term in field.lower() for term in ("secret", "token", "password", "key"))
    severity = "critical" if sensitive and group["leak_count"] >= 2 else "high" if sensitive else "medium"
    return {"profile": profile, "prompt_template": template, "field_name": field, "leak_count": group["leak_count"], "sample_count": group["sample_count"], "last_seen_at": group["last_seen_at"] or "unknown", "severity": severity, "recommended_action": "Block prompt release and add regression redaction checks." if severity == "critical" else "Patch redaction rule and replay prompt audit samples."}


def _severity_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(value, 4)


def _bool(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes", "failed", "leaked"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
