"""Profile signal mix export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.profile_signal_mix_report.v1"
KIND = "max.profile_signal_mix_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"


def build_profile_signal_mix_report(records: Iterable[dict[str, Any]], *, title: str = "Profile Signal Mix Report", generated_at: str = DEFAULT_GENERATED_AT, concentration_threshold: float = 0.7) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str, str, str], int] = defaultdict(int)
    roles_by_profile: dict[str, set[str]] = defaultdict(set)
    threshold = min(max(float(concentration_threshold), 0.0), 1.0)
    for raw in records:
        profile = _text(raw.get("profile")) or "unknown-profile"
        source = _text(raw.get("source")) or "unknown-source"
        role = _text(raw.get("role")) or "unknown-role"
        category = _text(raw.get("category")) or "unknown-category"
        freshness = _text(raw.get("freshness_bucket")) or "unknown-freshness"
        count = _int(raw.get("signal_count")) or 1
        grouped[(profile, source, role, category, freshness)] += count
        roles_by_profile[profile].add(role)
    rows = [{"profile": p, "source": s, "role": r, "category": c, "freshness_bucket": f, "signal_count": n} for (p, s, r, c, f), n in grouped.items()]
    rows.sort(key=lambda row: (row["profile"].lower(), row["source"].lower(), row["role"].lower(), row["category"].lower(), row["freshness_bucket"].lower()))
    profile_totals = []
    for profile in sorted({row["profile"] for row in rows}, key=str.lower):
        total = sum(row["signal_count"] for row in rows if row["profile"] == profile)
        source_counts = {source: sum(row["signal_count"] for row in rows if row["profile"] == profile and row["source"] == source) for source in {row["source"] for row in rows if row["profile"] == profile}}
        dominant_source, dominant_count = max(source_counts.items(), key=lambda item: (item[1], item[0].lower())) if source_counts else (None, 0)
        share = round(dominant_count / total, 4) if total else 0.0
        missing_roles = sorted({"buyer", "user", "technical"} - roles_by_profile.get(profile, set()))
        profile_totals.append({"profile": profile, "signal_count": total, "source_mix": {source: round(count / total, 4) if total else 0.0 for source, count in sorted(source_counts.items())}, "dominant_source": dominant_source, "dominant_source_share": share, "concentration_warning": share >= threshold, "missing_role_warnings": missing_roles, "triangulation_coverage": round(len(source_counts) / 3, 4) if source_counts else 0.0})
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT, "title": _text(title) or "Profile Signal Mix Report", "summary": {"profile_count": len(profile_totals), "signal_count": sum(row["signal_count"] for row in rows), "concentration_warning_count": sum(1 for row in profile_totals if row["concentration_warning"])}, "signal_mix": rows, "profile_totals": profile_totals}


def render_profile_signal_mix_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_profile_signal_mix_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    return "\n".join([f"# {report.get('title') or 'Profile Signal Mix Report'}", "", "## Summary", "", f"- Profiles: {summary.get('profile_count', 0)}", f"- Signals: {summary.get('signal_count', 0)}", f"- Concentration warnings: {summary.get('concentration_warning_count', 0)}"]).rstrip() + "\n"


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
