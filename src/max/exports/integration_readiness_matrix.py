"""Integration readiness matrix export for persisted buildable units."""

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
_KNOWN = ("OpenAI", "Slack", "Stripe", "Salesforce", "HubSpot", "GitHub", "Jira", "Linear", "Datadog", "Sentry")
_ORDER = {"blocked": 0, "at_risk": 1, "ready": 2}


def build_integration_readiness_matrix_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit, integration) for unit in store.get_buildable_units(limit=1000, domain=domain) for integration in _integrations(unit)]
    rows.sort(key=lambda row: (_ORDER[row["readiness"]], row["title"], row["integration_name"], row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "integration_readiness_matrix", "domain_filter": domain},
        "summary": {
            "idea_count": len({row["idea_id"] for row in rows}),
            "integration_count": len(rows),
            "readiness_counts": {state: sum(1 for row in rows if row["readiness"] == state) for state in ("blocked", "at_risk", "ready")},
        },
        "integration_rows": rows,
        "recommendations": _recommendations(rows),
    }


def render_integration_readiness_matrix_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_integration_readiness_matrix_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in report.get("integration_rows") or []:
        writer.writerow({column: _csv(row.get(column)) for column in CSV_COLUMNS})
    return output.getvalue()


def render_integration_readiness_matrix_markdown(report: dict[str, Any]) -> str:
    lines = ["# Integration Readiness Matrix", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Integrations", ""]
    if report.get("integration_rows"):
        lines.extend(["| Idea | Integration | Readiness | Owner | Missing Artifacts | Action |", "|------|-------------|-----------|-------|-------------------|--------|"])
        for row in report["integration_rows"]:
            lines.append(f"| {_md(row['title'])} | {row['integration_name']} | {row['readiness']} | {row['owner']} | {_md(', '.join(row['missing_artifacts']) or 'None')} | {_md(row['recommended_action'])} |")
    else:
        lines.append("- No third-party integrations detected.")
    lines.extend(["", "## Recommendations", ""])
    for recommendation in report.get("recommendations") or ["Keep integration ownership and credentials current."]:
        lines.append(f"- {recommendation}")
    return "\n".join(lines).rstrip() + "\n"


def _integrations(unit: Any) -> list[str]:
    metadata = getattr(unit, "metadata", {}) or {}
    explicit = metadata.get("integrations") if isinstance(metadata, dict) else None
    if explicit:
        return _dedupe([str(item) for item in explicit] if isinstance(explicit, list) else [str(explicit)])
    text = " ".join([
        str(getattr(unit, "tech_approach", "")),
        str(getattr(unit, "composability_notes", "")),
        str(getattr(unit, "suggested_stack", "")),
        str(getattr(unit, "solution", "")),
    ]).lower()
    return [name for name in _KNOWN if name.lower() in text] or ["Primary external system"] if "integrat" in text else []


def _row(unit: Any, integration: str) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", {}) or {}
    artifacts = metadata.get("integration_artifacts", {}) if isinstance(metadata, dict) else {}
    has_credentials = bool(_nested(artifacts, integration, "credentials"))
    has_contract = bool(_nested(artifacts, integration, "contract")) or "contract" in str(getattr(unit, "composability_notes", "")).lower()
    has_tests = bool(_nested(artifacts, integration, "tests")) or "test" in str(getattr(unit, "validation_plan", "")).lower()
    owner = str(_nested(artifacts, integration, "owner") or metadata.get("integration_owner") if isinstance(metadata, dict) else "") or "integration_owner"
    missing = []
    if not has_credentials:
        missing.append("credentials")
    if not has_contract:
        missing.append("contract_assumptions")
    if not has_tests:
        missing.append("test_coverage")
    readiness = "ready" if not missing else "blocked" if "credentials" in missing and "contract_assumptions" in missing else "at_risk"
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": str(getattr(unit, "title", "Untitled")),
        "integration_name": integration,
        "readiness": readiness,
        "missing_artifacts": missing,
        "owner": owner,
        "evidence_refs": _evidence_refs(unit),
        "recommended_action": _action(readiness, missing, integration),
    }


def _recommendations(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Add integration metadata or stack notes to buildable units that depend on external systems."]
    recs = []
    if any(row["readiness"] == "blocked" for row in rows):
        recs.append("Resolve blocked credentials and contract assumptions before launch readiness review.")
    if any("test_coverage" in row["missing_artifacts"] for row in rows):
        recs.append("Add contract or sandbox tests for integrations missing coverage signals.")
    return recs or ["Keep integration readiness evidence current."]


def _nested(data: dict[str, Any], integration: str, key: str) -> Any:
    value = data.get(integration) or data.get(integration.lower()) or {}
    return value.get(key) if isinstance(value, dict) else None


def _evidence_refs(unit: Any) -> list[str]:
    return [f"signal:{item}" for item in getattr(unit, "evidence_signals", [])] + [f"insight:{item}" for item in getattr(unit, "inspiring_insights", [])]


def _action(readiness: str, missing: list[str], integration: str) -> str:
    if readiness == "ready":
        return f"Keep {integration} owner, credentials, contract, and tests attached to release evidence."
    return f"Attach {', '.join(missing)} for {integration} before integration readiness sign-off."


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for value in values:
        compact = " ".join(value.split())
        if compact and compact not in seen:
            seen.add(compact)
            result.append(compact)
    return result


def _csv(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return "" if value is None else str(value)


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
