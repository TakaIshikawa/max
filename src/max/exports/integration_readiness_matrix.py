"""Integration readiness matrix export for buildable unit metadata."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.integration_readiness_matrix.v1"
KIND = "max.integration_readiness_matrix"
CSV_COLUMNS = ("idea_id", "title", "integration_name", "readiness", "missing_artifacts", "owner", "evidence_refs", "recommended_action")


def build_integration_readiness_matrix_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    units = store.get_buildable_units(limit=1000, domain=domain)
    rows = [row for unit in units for row in _rows(unit)]
    rows.sort(key=lambda row: ({"blocked": 0, "at_risk": 1, "ready": 2}[row["readiness"]], row["integration_name"], row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "integration_readiness_matrix", "domain_filter": domain},
        "summary": {
            "idea_count": len(units),
            "integration_count": len(rows),
            "readiness_counts": {state: sum(1 for row in rows if row["readiness"] == state) for state in ("blocked", "at_risk", "ready")},
        },
        "integration_rows": rows,
        "recommendations": _recommendations(rows),
    }


def render_integration_readiness_matrix_markdown(report: dict[str, Any]) -> str:
    lines = ["# Integration Readiness Matrix", "", f"Schema: `{report.get('schema_version')}`", "", "## Integrations", ""]
    if report.get("integration_rows"):
        lines.extend(["| Idea | Integration | Readiness | Owner | Missing | Action |", "|------|-------------|-----------|-------|---------|--------|"])
        for row in report["integration_rows"]:
            lines.append(f"| {_md(row['title'])} | {_md(row['integration_name'])} | {row['readiness']} | {_md(row['owner'])} | {_md(', '.join(row['missing_artifacts']) or 'None')} | {_md(row['recommended_action'])} |")
    else:
        lines.append("- No third-party integrations detected.")
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {item}" for item in report.get("recommendations", []))
    return "\n".join(lines).rstrip() + "\n"


def render_integration_readiness_matrix_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_integration_readiness_matrix_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in report.get("integration_rows", []):
        writer.writerow({**row, "missing_artifacts": json.dumps(row.get("missing_artifacts", [])), "evidence_refs": json.dumps(row.get("evidence_refs", []))})
    return output.getvalue()


def _rows(unit: Any) -> list[dict[str, Any]]:
    metadata = getattr(unit, "metadata", None) if isinstance(getattr(unit, "metadata", None), dict) else {}
    integrations = _integrations(unit, metadata)
    if not integrations:
        return []
    credentials = set(_list(metadata.get("credentials") or metadata.get("required_credentials")))
    contracts = set(_list(metadata.get("contracts") or metadata.get("contract_assumptions")))
    tests = set(_list(metadata.get("integration_tests") or metadata.get("test_coverage")))
    owner = _text(metadata.get("integration_owner") or metadata.get("owner")) or "integration owner"
    rows = []
    for integration in integrations:
        missing = []
        lowered = integration.lower()
        if not any(lowered in item.lower() for item in credentials):
            missing.append("credentials")
        if not any(lowered in item.lower() for item in contracts):
            missing.append("contract assumptions")
        if not any(lowered in item.lower() for item in tests):
            missing.append("test coverage")
        readiness = "blocked" if len(missing) >= 2 else "at_risk" if missing else "ready"
        rows.append({
            "idea_id": str(getattr(unit, "id", "")),
            "title": str(getattr(unit, "title", "Untitled")),
            "integration_name": integration,
            "readiness": readiness,
            "missing_artifacts": missing,
            "owner": owner,
            "evidence_refs": ["metadata.integrations", "metadata.credentials", "metadata.integration_tests"],
            "recommended_action": _action(readiness, integration, missing),
        })
    return rows


def _integrations(unit: Any, metadata: dict[str, Any]) -> list[str]:
    values = _list(metadata.get("integrations") or metadata.get("third_party_systems") or metadata.get("external_systems"))
    stack = metadata.get("suggested_stack")
    if isinstance(stack, dict):
        values.extend(str(value) for value in stack.values())
    text = " ".join([str(getattr(unit, "tech_approach", "")), str(metadata.get("tech_approach", "")), str(metadata.get("technical_approach", ""))]).lower()
    known = ("Slack", "Salesforce", "Stripe", "OpenAI", "GitHub", "Datadog", "HubSpot", "Twilio")
    values.extend(name for name in known if name.lower() in text)
    return sorted(set(_text(value) for value in values if _text(value)))


def _recommendations(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Capture third-party systems, credentials, contracts, tests, and owners for each integration."]
    blocked = [row for row in rows if row["readiness"] == "blocked"]
    if blocked:
        return ["Resolve blocked integration artifacts before launch readiness signoff."]
    return ["Keep integration credentials, contracts, tests, and owners current during rollout."]


def _action(readiness: str, integration: str, missing: list[str]) -> str:
    if readiness == "ready":
        return f"Keep {integration} readiness evidence current."
    return f"Add {', '.join(missing)} for {integration} before launch."


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
    if isinstance(value, dict):
        return [f"{key}: {value[key]}" for key in sorted(value) if _text(value[key])]
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, (list, tuple, set)) else [str(value)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
