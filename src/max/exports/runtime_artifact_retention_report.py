"""Runtime artifact retention export report."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.runtime_artifact_retention_report.v1"
KIND = "max.runtime_artifact_retention_report"
DEFAULT_GENERATED_AT = "2026-06-01T00:00:00+00:00"


def generate_runtime_artifact_retention_report(artifacts: Iterable[dict[str, Any]], *, generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    rows = [_artifact(row, index) for index, row in enumerate(artifacts, start=1)]
    breaches = [row for row in rows if row["retention_status"] != "retained"]
    breach_rate = round(len(breaches) / len(rows), 4) if rows else 0.0
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": generated_at, "summary": {"status": "degraded" if breaches else "healthy", "artifact_count": len(rows), "retained_count": len(rows) - len(breaches), "expired_count": sum(1 for row in rows if row["retention_status"] == "expired"), "oversized_count": sum(1 for row in rows if row["retention_status"] == "oversized"), "missing_count": sum(1 for row in rows if row["retention_status"] == "missing"), "breach_count": len(breaches), "breach_rate": breach_rate}, "artifacts": rows, "artifact_types": _groups(rows, "artifact_type"), "run_ids": _groups(rows, "run_id"), "top_breach_reasons": _top_reasons(breaches), "recommended_actions": _actions(breaches)}


def render_runtime_artifact_retention_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def render_runtime_artifact_retention_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = ["# Runtime Artifact Retention Report", "", f"Artifacts: {summary.get('artifact_count', 0)}", f"Breaches: {summary.get('breach_count', 0)} ({summary.get('breach_rate', 0.0)})", ""]
    for reason in report.get("top_breach_reasons") or []:
        lines.append(f"- {reason['reason']}: {reason['count']}")
    return "\n".join(lines).rstrip() + "\n"


def _artifact(item: dict[str, Any], index: int) -> dict[str, Any]:
    status = _text(item.get("retention_status") or item.get("status") or "retained")
    if status not in {"retained", "expired", "oversized", "missing"}:
        status = "expired" if status in {"breached", "breach"} else "retained"
    return {"artifact_id": _text(item.get("artifact_id") or item.get("id") or f"artifact-{index}"), "artifact_type": _text(item.get("artifact_type") or item.get("type") or "unknown"), "run_id": _text(item.get("run_id") or "unknown"), "retention_status": status, "breach_reason": _text(item.get("breach_reason") or item.get("reason") or (status if status != "retained" else ""))}


def _groups(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row[field]].append(row)
    output = []
    for value, items in grouped.items():
        breach_count = sum(1 for item in items if item["retention_status"] != "retained")
        output.append({field: value, "artifact_count": len(items), "retained_count": len(items) - breach_count, "expired_count": sum(1 for item in items if item["retention_status"] == "expired"), "oversized_count": sum(1 for item in items if item["retention_status"] == "oversized"), "missing_count": sum(1 for item in items if item["retention_status"] == "missing"), "breach_count": breach_count, "breach_rate": round(breach_count / len(items), 4) if items else 0.0})
    return sorted(output, key=lambda row: (-row["breach_count"], row[field]))


def _top_reasons(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["breach_reason"] or row["retention_status"] for row in rows)
    return [{"reason": reason, "count": count} for reason, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _actions(rows: list[dict[str, Any]]) -> list[str]:
    reasons = {row["retention_status"] for row in rows}
    actions = []
    if "expired" in reasons:
        actions.append("Delete expired artifacts after preservation checks.")
    if "oversized" in reasons:
        actions.append("Compress or move oversized artifacts to long-term storage.")
    if "missing" in reasons:
        actions.append("Rehydrate missing required artifacts or mark the run incomplete.")
    return actions


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

