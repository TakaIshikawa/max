"""Integration dependency health export for external service risk."""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.integration_dependency_health.v1"
KIND = "max.integration_dependency_health"
_FIELDS = ["idea_id", "unit_title", "provider", "criticality", "status", "sync_failure_count", "stale_sync", "fallback_available", "risk_level", "recommended_action"]


def build_integration_dependency_health_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    units = store.get_buildable_units(limit=1000, domain=domain)
    generated_at = datetime.now(timezone.utc)
    rows = [row for unit in units for row in _rows(unit, generated_at)]
    rows.sort(key=lambda row: (_risk_rank(row["risk_level"]), row["provider"], row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": generated_at.isoformat(),
        "source": {"project": "max", "entity_type": "integration_dependency_health", "domain_filter": domain},
        "integration_count": len(rows),
        "integrations": rows,
        "summary": _summary(rows),
    }


def render_integration_dependency_health_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Integration Dependency Health",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Integrations",
        "",
        "| Provider | Unit | Criticality | Status | Stale Sync | Fallback | Risk | Recommended Action |",
        "|----------|------|-------------|--------|------------|----------|------|--------------------|",
    ]
    for row in report.get("integrations", []):
        lines.append(f"| {row['provider']} | {row['unit_title']} | {row['criticality']} | {row['status']} | {row['stale_sync']} | {row['fallback_available']} | {row['risk_level']} | {row['recommended_action']} |")
    lines.extend(["", "## Provider Rollup", "", "| Provider | Integrations | High | Medium | Low |", "|----------|--------------|------|--------|-----|"])
    for row in report.get("summary", {}).get("by_provider", []):
        lines.append(f"| {row['provider']} | {row['integration_count']} | {row['risk_counts']['high']} | {row['risk_counts']['medium']} | {row['risk_counts']['low']} |")
    return "\n".join(lines).rstrip() + "\n"


def render_integration_dependency_health_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_integration_dependency_health_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_FIELDS)
    writer.writeheader()
    for row in report.get("integrations", []):
        writer.writerow({field: row.get(field) for field in _FIELDS})
    return output.getvalue()


def _rows(unit: Any, generated_at: datetime) -> list[dict[str, Any]]:
    metadata = _metadata(unit)
    integrations = _integration_values(metadata)
    if not integrations and metadata.get("dependency_status"):
        integrations = [{"provider": "unknown"}]
    rows = []
    for item in integrations:
        details = item if isinstance(item, dict) else {"provider": item}
        provider = str(details.get("provider") or details.get("name") or details.get("service") or "unknown")
        status = str(details.get("dependency_status") or details.get("status") or metadata.get("dependency_status") or "healthy").lower()
        criticality = str(details.get("criticality") or metadata.get("criticality") or "medium").lower()
        failures = int(_float(details.get("sync_failure_count", metadata.get("sync_failure_count", 0)), 0))
        stale = _stale(details.get("last_successful_sync", metadata.get("last_successful_sync")), generated_at)
        fallback = _bool(details.get("fallback_available", metadata.get("fallback_available", False)))
        risk = _risk(status, criticality, failures, stale, fallback)
        rows.append({
            "idea_id": str(getattr(unit, "id", "")),
            "unit_title": str(getattr(unit, "title", "Untitled")),
            "provider": provider,
            "criticality": criticality,
            "status": "stale" if stale and status == "healthy" else status,
            "sync_failure_count": failures,
            "stale_sync": stale,
            "fallback_available": fallback,
            "risk_level": risk,
            "recommended_action": _action(risk, stale, fallback),
        })
    return rows


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["provider"]].append(row)
    return {
        "risk_counts": {level: sum(1 for row in rows if row["risk_level"] == level) for level in ["low", "medium", "high"]},
        "by_provider": [
            {"provider": provider, "integration_count": len(items), "risk_counts": {level: sum(1 for row in items if row["risk_level"] == level) for level in ["low", "medium", "high"]}}
            for provider, items in sorted(groups.items())
        ],
    }


def _integration_values(metadata: dict[str, Any]) -> list[Any]:
    value = metadata.get("integrations", metadata.get("external_services", []))
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, dict):
        return [dict(details, provider=provider) if isinstance(details, dict) else {"provider": provider, "status": details} for provider, details in value.items()]
    return []


def _risk(status: str, criticality: str, failures: int, stale: bool, fallback: bool) -> str:
    score = 0
    if status in {"down", "failed", "outage"}:
        score += 4
    elif status in {"degraded", "stale"}:
        score += 2
    score += min(failures, 3)
    if stale:
        score += 2
    if criticality == "critical":
        score += 2
    elif criticality == "high":
        score += 1
    if not fallback:
        score += 1
    if score >= 4:
        return "high"
    if score >= 1:
        return "medium"
    return "low"


def _action(risk: str, stale: bool, fallback: bool) -> str:
    if risk == "high":
        return "Escalate owner review and validate recovery path"
    if stale:
        return "Refresh sync and confirm provider health"
    if not fallback:
        return "Document fallback or graceful degradation"
    return "Continue monitoring"


def _stale(value: Any, generated_at: datetime) -> bool:
    parsed = _parse_dt(value)
    return bool(parsed and (generated_at - parsed).days > 7)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _risk_rank(value: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(value, 3)
