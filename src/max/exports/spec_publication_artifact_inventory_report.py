"""Spec publication artifact inventory export report."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.spec_publication_artifact_inventory_report.v1"
KIND = "max.spec_publication_artifact_inventory_report"
DEFAULT_GENERATED_AT = "2026-05-20T00:00:00+00:00"


class SpecPublicationArtifactInput(TypedDict, total=False):
    artifact_id: str
    unit_id: str
    spec_id: str
    destination: str
    format: str
    status: str
    path: str
    published_at: str
    error: str


def build_spec_publication_artifact_inventory_report(
    records: Iterable[SpecPublicationArtifactInput | dict[str, Any]],
    *,
    title: str = "Spec Publication Artifact Inventory Report",
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    artifacts = _normalize_artifacts(records)
    failed_artifacts = [artifact for artifact in artifacts if artifact["status"] in {"failed", "error", "blocked"} or artifact["error"]]
    failed_artifacts.sort(key=lambda row: (row["destination"].lower(), row["artifact_id"].lower(), row["path"].lower()))
    missing_traceability = _missing_traceability(artifacts)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Spec Publication Artifact Inventory Report",
        "summary": _summary(artifacts, failed_artifacts, missing_traceability),
        "artifacts": artifacts,
        "failed_artifacts": failed_artifacts,
        "destination_totals": _dimension_totals(artifacts, "destination"),
        "format_totals": _dimension_totals(artifacts, "format"),
        "missing_traceability": missing_traceability,
    }


def render_spec_publication_artifact_inventory_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Spec Publication Artifact Inventory Report'}",
        "",
        "## Summary",
        "",
        f"- Artifacts: {summary.get('artifact_count', 0)}",
        f"- Destinations: {summary.get('destination_count', 0)}",
        f"- Formats: {summary.get('format_count', 0)}",
        f"- Failed artifacts: {summary.get('failed_artifact_count', 0)}",
        f"- Missing traceability: {summary.get('missing_traceability_count', 0)}",
        "",
        "## Failed Artifacts",
        "",
    ]
    failed = report.get("failed_artifacts") or []
    if failed:
        for artifact in failed:
            lines.append(f"- {artifact['artifact_id']}: {artifact['destination']} {artifact['status']} ({artifact['error'] or 'no error supplied'})")
    else:
        lines.append("- No failed artifacts were found.")
    lines.extend(["", "## Missing Traceability", ""])
    missing = report.get("missing_traceability") or []
    if missing:
        for row in missing:
            lines.append(f"- {row['artifact_id']}: missing {', '.join(row['missing_fields'])}")
    else:
        lines.append("- No missing traceability fields were found.")
    return "\n".join(lines).rstrip() + "\n"


def render_spec_publication_artifact_inventory_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_artifacts(records: Iterable[SpecPublicationArtifactInput | dict[str, Any]]) -> list[dict[str, Any]]:
    artifacts = []
    for index, raw in enumerate(records):
        artifact_id = _text(raw.get("artifact_id"))
        artifacts.append(
            {
                "artifact_id": artifact_id,
                "inventory_id": artifact_id or f"artifact-{index + 1}",
                "unit_id": _text(raw.get("unit_id")),
                "spec_id": _text(raw.get("spec_id")),
                "destination": _text(raw.get("destination")) or "unspecified-destination",
                "format": _text(raw.get("format")).lower() or "unspecified-format",
                "status": _status(raw.get("status")),
                "path": _text(raw.get("path")),
                "published_at": _text(raw.get("published_at")),
                "error": _text(raw.get("error")),
            }
        )
    artifacts.sort(key=lambda row: (row["destination"].lower(), row["format"].lower(), row["inventory_id"].lower(), row["path"].lower()))
    return artifacts


def _summary(artifacts: list[dict[str, Any]], failed_artifacts: list[dict[str, Any]], missing_traceability: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(artifact["status"] for artifact in artifacts)
    return {
        "artifact_count": len(artifacts),
        "destination_count": len({artifact["destination"] for artifact in artifacts}),
        "format_count": len({artifact["format"] for artifact in artifacts}),
        "published_count": status_counts.get("published", 0),
        "queued_count": status_counts.get("queued", 0),
        "failed_artifact_count": len(failed_artifacts),
        "missing_traceability_count": len(missing_traceability),
    }


def _dimension_totals(artifacts: list[dict[str, Any]], dimension: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for artifact in artifacts:
        grouped[artifact[dimension]].append(artifact)

    totals = []
    for value, items in grouped.items():
        status_counts = Counter(item["status"] for item in items)
        totals.append(
            {
                dimension: value,
                "artifact_count": len(items),
                "published_count": status_counts.get("published", 0),
                "queued_count": status_counts.get("queued", 0),
                "failed_count": sum(status_counts.get(status, 0) for status in ("failed", "error", "blocked")),
            }
        )
    totals.sort(key=lambda row: (-row["artifact_count"], row[dimension].lower()))
    return totals


def _missing_traceability(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    missing = []
    for artifact in artifacts:
        missing_fields = [field for field in ("artifact_id", "unit_id", "spec_id") if not artifact[field]]
        if missing_fields:
            missing.append(
                {
                    "artifact_id": artifact["artifact_id"] or artifact["inventory_id"],
                    "destination": artifact["destination"],
                    "path": artifact["path"],
                    "missing_fields": missing_fields,
                }
            )
    missing.sort(key=lambda row: (row["artifact_id"].lower(), row["destination"].lower(), row["path"].lower()))
    return missing


def _status(value: Any) -> str:
    status = _text(value).lower()
    if status in {"published", "queued", "failed", "error", "blocked", "pending", "written"}:
        return "published" if status == "written" else status
    return "unknown"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
