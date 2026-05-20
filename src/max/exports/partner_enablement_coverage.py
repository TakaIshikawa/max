"""Partner enablement coverage export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable, Literal, TypedDict

SCHEMA_VERSION = "max.partner_enablement_coverage.v1"
KIND = "max.partner_enablement_coverage"

ReadinessStatus = Literal["blocked", "needs_attention", "ready"]

_READINESS_ORDER = {"blocked": 0, "needs_attention": 1, "ready": 2}
_CERTIFIED = {"certified", "complete", "completed", "passed", "ready"}


class PartnerEnablementCoverageInput(TypedDict, total=False):
    partner: str
    name: str
    segment: str
    tier: str
    required_materials: list[str]
    available_materials: list[str]
    certification_status: str
    owner: str
    blocker: str
    blockers: list[str]
    readiness_status: str
    evidence: list[str]


def build_partner_enablement_coverage_report(
    records: Iterable[PartnerEnablementCoverageInput | dict[str, Any]],
    *,
    title: str = "Partner Enablement Coverage Report",
) -> dict[str, Any]:
    rows = _normalize_records(records)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(title) or "Partner Enablement Coverage Report",
        "summary": _summary(rows),
        "partner_segments": _partner_segments(rows),
        "material_gaps": _material_gaps(rows),
        "certification_gaps": _certification_gaps(rows),
        "blocker_rows": _blocker_rows(rows),
        "records": rows,
    }


def render_partner_enablement_coverage_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Partner Enablement Coverage Report'}",
        "",
        f"Schema: `{report.get('schema_version', SCHEMA_VERSION)}`",
        "",
        "## Summary",
        "",
        f"- Partners: {summary.get('partner_count', 0)}",
        f"- Segments: {summary.get('segment_count', 0)}",
        f"- Average material coverage: {summary.get('average_material_coverage_percent', 0.0)}%",
        f"- Readiness posture: {summary.get('readiness_posture', 'ready')}",
        "",
        "## Partner Segments",
        "",
    ]
    if report.get("partner_segments"):
        lines.extend(["| Segment | Partners | Coverage | Blocked | Needs Attention | Ready |", "|---------|----------|----------|---------|-----------------|-------|"])
        for row in report["partner_segments"]:
            counts = row["readiness_counts"]
            lines.append(
                f"| {_md(row['segment'])} | {row['partner_count']} | {row['average_material_coverage_percent']}% | "
                f"{counts['blocked']} | {counts['needs_attention']} | {counts['ready']} |"
            )
    else:
        lines.append("- No partner enablement records were supplied.")

    lines.extend(["", "## Launch Blockers", ""])
    if report.get("blocker_rows"):
        for row in report["blocker_rows"]:
            lines.append(f"- {row['partner']}: {', '.join(row['blockers'])} ({row['owner']})")
    else:
        lines.append("- No launch blockers supplied.")
    return "\n".join(lines).rstrip() + "\n"


def render_partner_enablement_coverage_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_records(records: Iterable[PartnerEnablementCoverageInput | dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for raw in records:
        required = _items(raw.get("required_materials") or raw.get("materials_required"))
        available = _items(raw.get("available_materials") or raw.get("materials_available"))
        missing = sorted(set(required) - set(available), key=str.lower)
        blockers = _items(raw.get("blockers") or raw.get("blocker"))
        certification = _text(raw.get("certification_status") or raw.get("certification") or "unknown").lower().replace("_", " ")
        coverage = round((len(set(required) & set(available)) / len(required)) * 100, 1) if required else 100.0
        readiness = _readiness(raw.get("readiness_status"), missing=missing, blockers=blockers, certification=certification)
        rows.append(
            {
                "partner": _text(raw.get("partner") or raw.get("name") or "Unknown partner"),
                "segment": _text(raw.get("segment") or "Unassigned segment"),
                "tier": _text(raw.get("tier") or "Unassigned tier"),
                "required_materials": required,
                "available_materials": available,
                "missing_materials": missing,
                "material_coverage_percent": coverage,
                "certification_status": certification,
                "owner": _text(raw.get("owner") or "Unassigned"),
                "blockers": blockers,
                "readiness_status": readiness,
                "evidence": _items(raw.get("evidence")),
            }
        )
    rows.sort(key=lambda row: (_READINESS_ORDER[row["readiness_status"]], row["material_coverage_percent"], row["segment"].lower(), row["partner"].lower()))
    return rows


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    readiness_counts = {status: sum(1 for row in rows if row["readiness_status"] == status) for status in ("blocked", "needs_attention", "ready")}
    return {
        "partner_count": count,
        "segment_count": len({row["segment"] for row in rows}),
        "average_material_coverage_percent": round(sum(row["material_coverage_percent"] for row in rows) / count, 1) if count else 0.0,
        "readiness_counts": readiness_counts,
        "readiness_posture": _posture(readiness_counts),
        "material_gap_count": sum(len(row["missing_materials"]) for row in rows),
        "certification_gap_count": sum(1 for row in rows if not _is_certified(row["certification_status"])),
        "blocker_count": sum(len(row["blockers"]) for row in rows),
        "unassigned_owner_count": sum(1 for row in rows if row["owner"] == "Unassigned"),
    }


def _partner_segments(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["segment"]].append(row)
    segments = []
    for segment, items in grouped.items():
        segments.append(
            {
                "segment": segment,
                "partner_count": len(items),
                "average_material_coverage_percent": round(sum(row["material_coverage_percent"] for row in items) / len(items), 1),
                "readiness_counts": {status: sum(1 for row in items if row["readiness_status"] == status) for status in ("blocked", "needs_attention", "ready")},
                "owners": sorted({row["owner"] for row in items}),
            }
        )
    segments.sort(key=lambda row: (_READINESS_ORDER[_posture(row["readiness_counts"])], row["average_material_coverage_percent"], row["segment"].lower()))
    return segments


def _material_gaps(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps = [
        {
            "partner": row["partner"],
            "segment": row["segment"],
            "missing_materials": row["missing_materials"],
            "material_coverage_percent": row["material_coverage_percent"],
            "owner": row["owner"],
        }
        for row in rows
        if row["missing_materials"]
    ]
    gaps.sort(key=lambda row: (row["material_coverage_percent"], row["segment"].lower(), row["partner"].lower()))
    return gaps


def _certification_gaps(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps = [
        {"partner": row["partner"], "segment": row["segment"], "certification_status": row["certification_status"], "owner": row["owner"]}
        for row in rows
        if not _is_certified(row["certification_status"])
    ]
    gaps.sort(key=lambda row: (row["segment"].lower(), row["partner"].lower()))
    return gaps


def _blocker_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blockers = [
        {"partner": row["partner"], "segment": row["segment"], "blockers": row["blockers"], "readiness_status": row["readiness_status"], "owner": row["owner"]}
        for row in rows
        if row["blockers"] or row["readiness_status"] == "blocked"
    ]
    blockers.sort(key=lambda row: (_READINESS_ORDER[row["readiness_status"]], row["segment"].lower(), row["partner"].lower()))
    return blockers


def _readiness(value: Any, *, missing: list[str], blockers: list[str], certification: str) -> ReadinessStatus:
    explicit = _text(value).lower().replace("_", " ")
    if explicit in {"blocked", "needs attention", "needs_attention", "ready"}:
        return "needs_attention" if explicit == "needs attention" else explicit  # type: ignore[return-value]
    if blockers:
        return "blocked"
    if missing or not _is_certified(certification):
        return "needs_attention"
    return "ready"


def _posture(counts: dict[str, int]) -> ReadinessStatus:
    if counts.get("blocked", 0):
        return "blocked"
    if counts.get("needs_attention", 0):
        return "needs_attention"
    return "ready"


def _is_certified(value: str) -> bool:
    return value.lower() in _CERTIFIED


def _items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return sorted({part.strip() for part in value.replace(";", ",").split(",") if part.strip()}, key=str.lower)
    if isinstance(value, (list, tuple, set)):
        return sorted({_text(item) for item in value if _text(item)}, key=str.lower)
    return [_text(value)] if _text(value) else []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
