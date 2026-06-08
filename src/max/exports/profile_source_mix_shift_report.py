"""Profile source mix shift export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

SCHEMA_VERSION = "max.profile_source_mix_shift_report.v1"
KIND = "max.profile_source_mix_shift_report"
_STATUS_ORDER = {"imbalanced": 0, "shifted": 1, "stable": 2}


def generate_profile_source_mix_shift_report(payload: dict[str, Any], *, shifted_threshold: float = 10.0, imbalanced_threshold: float = 30.0) -> dict[str, Any]:
    baseline = _counts(payload.get("baseline") or payload.get("baseline_counts") or [])
    observed = _counts(payload.get("observed") or payload.get("observed_counts") or [])
    profiles = sorted(set(baseline) | set(observed))
    rows = []
    for profile in profiles:
        sources = sorted(set(baseline[profile]) | set(observed[profile]))
        base_total = sum(baseline[profile].values())
        obs_total = sum(observed[profile].values())
        shifts = {}
        missing = []
        for source in sources:
            base_pct = baseline[profile][source] / base_total * 100 if base_total else 0.0
            obs_pct = observed[profile][source] / obs_total * 100 if obs_total else 0.0
            shifts[source] = round(obs_pct - base_pct, 2)
            if baseline[profile][source] and not observed[profile][source]:
                missing.append(source)
        total_drift = round(sum(abs(value) for value in shifts.values()) / 2, 2)
        rows.append({"profile": profile, "baseline_total": base_total, "observed_total": obs_total, "source_shifts": shifts, "total_drift": total_drift, "missing_source_count": len(missing), "missing_sources": missing, "status": "imbalanced" if missing or total_drift >= imbalanced_threshold else ("shifted" if total_drift >= shifted_threshold else "stable")})
    rows.sort(key=lambda row: (_STATUS_ORDER[row["status"]], row["profile"].casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": rows[0]["status"] if rows else "stable", "profile_count": len(rows), "missing_source_count": sum(row["missing_source_count"] for row in rows)}, "rows": rows}


def _counts(records: Any) -> dict[str, defaultdict[str, int]]:
    output: dict[str, defaultdict[str, int]] = defaultdict(lambda: defaultdict(int))
    if isinstance(records, dict):
        for profile, values in records.items():
            if isinstance(values, dict):
                for source, count in values.items():
                    output[_text(profile) or "default"][_text(source) or "unknown-source"] += _int(count)
        return output
    for raw in records if isinstance(records, list) else []:
        if isinstance(raw, dict):
            output[_text(raw.get("profile") or raw.get("profile_id")) or "default"][_text(raw.get("source") or raw.get("source_name")) or "unknown-source"] += _int(raw.get("count") or raw.get("signals"))
    return output


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
