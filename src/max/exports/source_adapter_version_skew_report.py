"""Source adapter version skew export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.source_adapter_version_skew_report.v1"
KIND = "max.source_adapter_version_skew_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"


def build_source_adapter_version_skew_report(records: Iterable[dict[str, Any]], *, title: str = "Source Adapter Version Skew Report", generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in records:
        if isinstance(raw, dict):
            groups[_text(raw.get("adapter")) or "unknown-adapter"].append(raw)
    rows = []
    for adapter, items in groups.items():
        versions = sorted({_text(i.get("observed_version") or i.get("version")) or "unknown" for i in items})
        expected = _text(items[0].get("expected_version")) or versions[0]
        if len(versions) > 1 or "unknown" in versions or expected not in versions:
            severity = _severity(expected, versions)
            rows.append({"adapter": adapter, "expected_version": expected, "observed_versions": versions, "environment_ids": sorted(_text(i.get("environment") or i.get("environment_id") or i.get("run_id")) or "unknown" for i in items), "skew_severity": severity, "rollout_recommendation": _recommendation(severity)})
    rows.sort(key=lambda r: ({"major_minor": 0, "unknown": 1, "patch": 2, "none": 3}[r["skew_severity"]], r["adapter"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT, "title": _text(title) or "Source Adapter Version Skew Report", "summary": {"adapter_count": len(groups), "skewed_adapter_count": len(rows), "unknown_version_count": sum(1 for r in rows if "unknown" in r["observed_versions"])}, "skew_rows": rows}


def render_source_adapter_version_skew_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_source_adapter_version_skew_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report.get('title') or 'Source Adapter Version Skew Report'}", "", "## Version Skew", ""]
    lines.extend([f"- {r['adapter']}: {', '.join(r['observed_versions'])} ({r['skew_severity']})" for r in report.get("skew_rows") or []] or ["- No adapter version skew detected."])
    return "\n".join(lines).rstrip() + "\n"


def _severity(expected: str, versions: list[str]) -> str:
    if "unknown" in versions or expected == "unknown":
        return "unknown"
    parsed = [_semver(v) for v in versions + [expected]]
    if any(p is None for p in parsed):
        return "unknown"
    majors = {p[0] for p in parsed if p}
    minors = {(p[0], p[1]) for p in parsed if p}
    return "major_minor" if len(majors) > 1 or len(minors) > 1 else "patch"


def _semver(value: str) -> tuple[int, int, int] | None:
    parts = value.lstrip("v").split(".")
    if len(parts) < 2:
        return None
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
    except ValueError:
        return None


def _recommendation(severity: str) -> str:
    if severity == "major_minor":
        return "pause rollout and align adapter major/minor versions"
    if severity == "patch":
        return "complete patch rollout"
    return "inventory unknown adapter versions before rollout"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
