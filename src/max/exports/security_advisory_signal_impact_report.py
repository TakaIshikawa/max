"""Security advisory signal impact export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

SCHEMA_VERSION = "max.security_advisory_signal_impact_report.v1"
KIND = "max.security_advisory_signal_impact_report"
DEFAULT_GENERATED_AT = "2026-05-31T00:00:00+00:00"
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}


def generate_security_advisory_signal_impact_report(advisories: Iterable[dict[str, Any]], artifacts: Iterable[dict[str, Any]], *, generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    artifact_rows = [_artifact(item, index) for index, item in enumerate(artifacts, start=1)]
    rows = []
    unmatched = []
    for index, advisory in enumerate(advisories, start=1):
        package = _text(advisory.get("package") or advisory.get("package_name") or advisory.get("dependency")).lower()
        affected = [artifact for artifact in artifact_rows if package and package in artifact["dependencies"]]
        row = {"advisory_id": _text(advisory.get("advisory_id") or advisory.get("id")) or f"advisory-{index}", "package": package or "unknown", "severity": _sev(advisory.get("severity")), "affected_artifact_ids": [artifact["artifact_id"] for artifact in affected], "profiles": sorted({artifact["profile"] for artifact in affected}), "recommended_disposition": _action(_sev(advisory.get("severity")), bool(affected))}
        if affected:
            rows.append(row)
        else:
            unmatched.append(row)
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], row["package"], row["advisory_id"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": generated_at, "summary": {"advisory_count": len(rows) + len(unmatched), "matched_advisory_count": len(rows), "unmatched_advisory_count": len(unmatched), "affected_artifact_count": len({artifact_id for row in rows for artifact_id in row["affected_artifact_ids"]})}, "rows": rows, "unmatched_advisories": unmatched}


def render_security_advisory_signal_impact_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_security_advisory_signal_impact_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Security Advisory Signal Impact Report", "", f"Matched advisories: {report.get('summary', {}).get('matched_advisory_count', 0)}", ""]
    for row in report.get("rows") or []:
        lines.append(f"- {row['advisory_id']} / {row['package']} ({row['severity']}): {', '.join(row['affected_artifact_ids'])} - {row['recommended_disposition']}")
    for row in report.get("unmatched_advisories") or []:
        lines.append(f"- {row['advisory_id']} / {row['package']}: unmatched")
    return "\n".join(lines).rstrip() + "\n"


def _artifact(item: dict[str, Any], index: int) -> dict[str, Any]:
    return {"artifact_id": _text(item.get("artifact_id") or item.get("unit_id") or item.get("spec_id") or item.get("id")) or f"artifact-{index}", "profile": _text(item.get("profile")) or "default", "dependencies": {_text(dep).lower() for dep in _list(item.get("dependencies") or item.get("packages")) if _text(dep)}}


def _action(severity: str, affected: bool) -> str:
    return "Patch or quarantine affected artifacts." if affected and severity in {"critical", "high"} else ("Track advisory until dependency appears." if not affected else "Plan dependency update.")


def _sev(value: Any) -> str:
    text = _text(value).lower()
    return text if text in SEVERITY_RANK else "unknown"


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else ([] if value in (None, "") else [value])


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
