"""Onboarding activation cohorts export."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

SCHEMA_VERSION = "max.onboarding_activation_cohorts.v1"
KIND = "max.onboarding_activation_cohorts"


def export_onboarding_activation_cohorts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[_text(record.get("cohort") or record.get("cohort_key") or record.get("start_month") or "Unknown")].append(record)
    rows = [_row(cohort, items) for cohort, items in groups.items()]
    rows.sort(key=lambda row: (row["cohort"], -row["account_count"]))
    return rows


def render_onboarding_activation_cohorts_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, indent=2, sort_keys=True, default=str) + "\n"


def _row(cohort: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    activated = sum(1 for record in records if _activated(record))
    times = [_int(record.get("time_to_value_days")) for record in records if record.get("time_to_value_days") is not None]
    stalled = Counter(milestone for record in records for milestone in _items(record.get("stalled_milestones") or record.get("stalled")))
    stalled_rows = [{"milestone": name, "count": count} for name, count in sorted(stalled.items(), key=lambda item: (-item[1], item[0]))]
    activation_rate = round(activated / len(records), 4) if records else 0.0
    return {
        "cohort": cohort,
        "account_count": len(records),
        "activated_count": activated,
        "activation_rate": activation_rate,
        "average_time_to_value_days": round(sum(times) / len(times), 1) if times else None,
        "stalled_milestones": stalled_rows,
        "recommended_intervention": _intervention(activation_rate, stalled_rows, times),
    }


def _activated(record: dict[str, Any]) -> bool:
    if str(record.get("activated")).strip().lower() in {"1", "true", "yes"}:
        return True
    milestones = record.get("milestones")
    if isinstance(milestones, dict):
        return bool(milestones) and all(bool(value) for value in milestones.values())
    return False


def _intervention(rate: float, stalled: list[dict[str, Any]], times: list[int]) -> str:
    if stalled:
        return f"Assign onboarding owner to unblock {stalled[0]['milestone']}."
    if rate < 0.5:
        return "Run activation review for incomplete onboarding accounts."
    if times and sum(times) / len(times) > 30:
        return "Shorten time-to-value with guided implementation checklist."
    return "Maintain standard onboarding cadence."


def _items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    if isinstance(value, str):
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    return []


def _int(value: Any) -> int:
    try:
        return max(int(float(str(value or 0))), 0)
    except ValueError:
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
