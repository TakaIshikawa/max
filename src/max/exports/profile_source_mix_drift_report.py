"""Profile source mix drift export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "max.profile_source_mix_drift_report.v1"
KIND = "max.profile_source_mix_drift_report"
SEVERITY_RANK = {"critical": 0, "warn": 1, "info": 2, "ok": 3}


def generate_profile_source_mix_drift_report(signals: Iterable[dict[str, Any]], target_allocations: Mapping[str, Mapping[str, Any]], *, min_sample_size: int = 10, warn_threshold: float = 0.15, critical_threshold: float = 0.3) -> dict[str, Any]:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for signal in signals:
        counts[_text(signal.get("profile")) or "default"][_text(signal.get("source")) or "unknown"] += 1
    profiles = sorted(set(counts) | {_text(profile) or "default" for profile in target_allocations})
    rows = []
    for profile in profiles:
        sources = sorted(set(counts[profile]) | {_text(source) for source in target_allocations.get(profile, {}) if _text(source)})
        total = sum(counts[profile].values())
        for source in sources:
            expected = _float(target_allocations.get(profile, {}).get(source))
            actual = counts[profile][source] / total if total else 0.0
            drift = round(actual - expected, 4)
            severity = "info" if total < min_sample_size else ("critical" if abs(drift) >= critical_threshold else ("warn" if abs(drift) >= warn_threshold else "ok"))
            rows.append({"profile": profile, "source": source, "sample_size": total, "signal_count": counts[profile][source], "expected_share": round(expected, 4), "actual_share": round(actual, 4), "drift": drift, "severity": severity, "recommendation": "Collect more samples before rebalancing." if severity == "info" else ("Rebalance source allocation." if severity != "ok" else "No action required.")})
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], row["profile"], row["source"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"row_count": len(rows), "drifted_row_count": sum(1 for row in rows if row["severity"] in {"critical", "warn"})}, "rows": rows}


def render_profile_source_mix_drift_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_profile_source_mix_drift_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Profile Source Mix Drift Report", ""]
    for row in report.get("rows") or []:
        lines.append(f"- {row['profile']} / {row['source']}: expected {row['expected_share']}, actual {row['actual_share']}, drift {row['drift']} ({row['severity']})")
    return "\n".join(lines).rstrip() + "\n"


def _float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
