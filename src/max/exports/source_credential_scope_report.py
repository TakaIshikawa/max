"""Source credential scope export report."""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "max.source_credential_scope_report.v1"
KIND = "max.source_credential_scope_report"
SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def generate_source_credential_scope_report(credentials: Iterable[dict[str, Any]], required_scopes_by_source: Mapping[str, Any], *, allowed_scopes_by_source: Mapping[str, Any] | None = None) -> dict[str, Any]:
    allowed_scopes_by_source = allowed_scopes_by_source or {}
    rows = []
    for index, credential in enumerate(credentials, start=1):
        source = _text(credential.get("source")) or f"source-{index}"
        environment = _text(credential.get("environment") or credential.get("env")) or "default"
        configured = _items(credential.get("scopes") or credential.get("scope"))
        required = _items(required_scopes_by_source.get(source))
        allowed = _items(allowed_scopes_by_source.get(source)) or sorted(set(required) | set(configured))
        missing = sorted(set(required) - set(configured))
        excessive = sorted(set(configured) - set(allowed))
        severity = "critical" if missing else ("warn" if excessive else "ok")
        rows.append({"source": source, "environment": environment, "configured_scopes": configured, "required_scopes": required, "missing_scopes": missing, "excessive_scopes": excessive, "severity": severity, "recommendation": "Grant missing required scopes before enabling adapter." if missing else ("Remove excessive credential scopes." if excessive else "No action required.")})
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], row["source"], row["environment"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"credential_count": len(rows), "missing_scope_count": sum(len(row["missing_scopes"]) for row in rows), "excessive_scope_count": sum(len(row["excessive_scopes"]) for row in rows)}, "rows": rows}


def render_source_credential_scope_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_source_credential_scope_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Source Credential Scope Report", ""]
    for row in report.get("rows") or []:
        lines.append(f"- {row['source']} / {row['environment']}: missing {', '.join(row['missing_scopes']) or '-'}; excessive {', '.join(row['excessive_scopes']) or '-'}; {row['recommendation']}")
    return "\n".join(lines).rstrip() + "\n"


def _items(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        value = value.get("required") or value.get("scopes") or value.keys()
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, Iterable):
        parts = list(value)
    else:
        parts = []
    return sorted({_text(part) for part in parts if _text(part)})


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
