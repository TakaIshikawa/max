"""Compliance evidence packet export for audit readiness."""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.compliance_evidence_packet.v1"
KIND = "max.compliance_evidence_packet"

_FIELDS = ["idea_id", "title", "control_id", "framework", "evidence_url", "owner", "evidence_status", "review_date", "data_category", "risk_level"]


def build_compliance_evidence_packet(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (row["framework"], row["control_id"], row["review_date"] or "9999-99-99", row["idea_id"]))
    missing = [row for row in rows if not row["evidence_url"] or row["evidence_status"] in {"failed", "missing", "rejected"}]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "compliance_evidence_packet", "domain_filter": domain},
        "summary": {"evidence_count": len(rows), "missing_evidence_count": len(missing), "framework_count": len({row["framework"] for row in rows})},
        "framework_rollups": _framework_rollups(rows),
        "missing_evidence_count": len(missing),
        "missing_evidence": missing,
        "review_schedule": [row for row in rows if row["review_date"]],
        "evidence_rows": rows,
    }


def render_compliance_evidence_packet_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Compliance Evidence Packet",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Evidence items: {summary.get('evidence_count', 0)}",
        f"- Frameworks: {summary.get('framework_count', 0)}",
        f"- Missing evidence: {summary.get('missing_evidence_count', 0)}",
        "",
        "## Framework Rollup",
        "",
        "| Framework | Evidence | Missing | High Risk |",
        "|-----------|----------|---------|-----------|",
    ]
    for row in report.get("framework_rollups", []):
        lines.append(f"| {row['framework']} | {row['evidence_count']} | {row['missing_evidence_count']} | {row['high_risk_count']} |")
    lines.extend(["", "## Missing Evidence", ""])
    for row in report.get("missing_evidence", []) or [{"control_id": "None", "title": "No missing evidence"}]:
        lines.append(f"- {row['control_id']}: {row['title']}")
    lines.extend(["", "## Evidence Table", "", "| Control | Framework | Status | Owner | Review | Risk | Evidence |", "|---------|-----------|--------|-------|--------|------|----------|"])
    for row in report.get("evidence_rows", []):
        lines.append(f"| {row['control_id']} | {row['framework']} | {row['evidence_status']} | {row['owner']} | {row['review_date'] or 'unknown'} | {row['risk_level']} | {row['evidence_url'] or 'missing'} |")
    return "\n".join(lines).rstrip() + "\n"


def render_compliance_evidence_packet_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_compliance_evidence_packet_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_FIELDS)
    writer.writeheader()
    for row in report.get("evidence_rows", []):
        writer.writerow({field: row.get(field) for field in _FIELDS})
    return output.getvalue()


def _row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": str(getattr(unit, "title", "Untitled")),
        "control_id": _string(metadata, "control_id", "unknown"),
        "framework": _string(metadata, "framework", "unknown").lower(),
        "evidence_url": _string(metadata, "evidence_url", ""),
        "owner": _string(metadata, "owner", "unassigned"),
        "evidence_status": _string(metadata, "evidence_status", "missing").lower(),
        "review_date": _string(metadata, "review_date", "") or None,
        "data_category": _string(metadata, "data_category", "unknown").lower(),
        "risk_level": _string(metadata, "risk_level", "unknown").lower(),
    }


def _framework_rollups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["framework"]].append(row)
    rollups = []
    for framework, items in sorted(groups.items()):
        rollups.append({
            "framework": framework,
            "evidence_count": len(items),
            "missing_evidence_count": sum(1 for item in items if not item["evidence_url"] or item["evidence_status"] in {"failed", "missing", "rejected"}),
            "high_risk_count": sum(1 for item in items if item["risk_level"] in {"high", "critical"}),
        })
    return rollups


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _string(metadata: dict[str, Any], key: str, default: str) -> str:
    value = metadata.get(key, default)
    return str(value).strip() if value not in (None, "") else default
