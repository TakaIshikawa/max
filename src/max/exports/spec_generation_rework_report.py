"""Spec generation rework export report."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any, Mapping

SCHEMA_VERSION = "max.spec_generation_rework_report.v1"
KIND = "max.spec_generation_rework_report"


def build_spec_generation_rework_report(records: list[Mapping[str, Any]], *, min_revisions: int = 3, generated_at: str = "2026-06-01T00:00:00+00:00") -> dict[str, Any]:
    specs: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    reasons: Counter[str] = Counter()
    reviewers: Counter[str] = Counter()
    gaps = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        spec_id = _text(record.get("spec_id")) or "unknown-spec"
        specs[spec_id].append(record)
        reason = _text(record.get("rejection_reason"))
        if reason:
            reasons[reason] += 1
        reviewer = _text(record.get("reviewer")) or "unassigned"
        if _text(record.get("status")).lower() in {"pending", "rejected", "needs_rework"}:
            reviewers[reviewer] += 1
        if _truthy(record.get("evidence_gap")):
            gaps.append({"spec_id": spec_id, "unit_id": _text(record.get("unit_id")) or "unknown-unit", "evidence_gap": _text(record.get("evidence_gap"))})
    spec_rows = [{"spec_id": spec_id, "revision_count": len(items), "latest_status": _text(sorted(items, key=lambda item: int(item.get("revision") or 0))[-1].get("status")) or "unknown"} for spec_id, items in specs.items()]
    high = [row for row in spec_rows if row["revision_count"] >= min_revisions]
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": generated_at, "summary": {"spec_count": len(specs), "revision_count": sum(len(items) for items in specs.values()), "average_revisions_per_spec": round(sum(len(items) for items in specs.values()) / len(specs), 2) if specs else 0.0, "unresolved_gap_count": len(gaps), "high_rework_count": len(high)}, "top_rejection_reasons": _counter_rows(reasons, "reason"), "high_rework_specs": sorted(high, key=lambda row: (-row["revision_count"], row["spec_id"])), "unresolved_evidence_gaps": sorted(gaps, key=lambda row: (row["spec_id"], row["unit_id"])), "reviewer_queues": _counter_rows(reviewers, "reviewer")}


def render_spec_generation_rework_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_spec_generation_rework_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Spec Generation Rework Report", "", "## High-Rework Specs", ""]
    lines.extend([f"- {row['spec_id']}: {row['revision_count']} revisions" for row in report.get("high_rework_specs") or []] or ["- No high-rework specs."])
    lines.extend(["", "## Top Rejection Reasons", ""])
    lines.extend([f"- {row['reason']}: {row['count']}" for row in report.get("top_rejection_reasons") or []] or ["- No rejection reasons."])
    return "\n".join(lines).rstrip() + "\n"


def _counter_rows(counter: Counter[str], key: str) -> list[dict[str, Any]]:
    return [{key: name, "count": count} for name, count in sorted(counter.items(), key=lambda item: (-item[1], item[0].lower()))]


def _truthy(value: Any) -> bool:
    return bool(value) and str(value).lower() not in {"false", "0", "none"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
