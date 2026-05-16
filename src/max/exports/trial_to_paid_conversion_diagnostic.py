"""Trial-to-paid conversion diagnostic export."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

SCHEMA_VERSION = "max.trial_to_paid_conversion_diagnostic.v1"
KIND = "max.trial_to_paid_conversion_diagnostic"


def export_trial_to_paid_conversion_diagnostic(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[_text(record.get("cohort") or record.get("cohort_key") or "Unknown")].append(record)
    rows = [_row(cohort, items) for cohort, items in groups.items()]
    rows.sort(key=lambda row: (row["cohort"], -row["trial_count"]))
    return rows


def render_trial_to_paid_conversion_diagnostic_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, indent=2, sort_keys=True, default=str) + "\n"


def _row(cohort: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    converted = sum(1 for record in records if _truthy(record.get("converted") or record.get("paid")))
    blockers = sorted({blocker for record in records for blocker in _items(record.get("blockers"))})
    activation = sorted({signal for record in records for signal in _items(record.get("activation_signals") or record.get("activation"))})
    sales_touches = sum(_int(record.get("sales_touchpoints")) for record in records)
    rate = round(converted / len(records), 4) if records else 0.0
    return {
        "cohort": cohort,
        "trial_count": len(records),
        "converted_count": converted,
        "conversion_rate": rate,
        "activation_signals": activation or ["unknown"],
        "sales_touchpoints": sales_touches,
        "blockers": blockers or ["none"],
        "blocker_classification": _blocker_classification(blockers),
        "recommended_experiment": _experiment(rate, blockers, activation, sales_touches),
    }


def _blocker_classification(blockers: list[str]) -> str:
    text = " ".join(blockers).lower()
    if any(word in text for word in ("payment", "price", "procurement", "security")):
        return "commercial"
    if any(word in text for word in ("setup", "activation", "onboarding", "integration")):
        return "activation"
    return "none" if not blockers else "product"


def _experiment(rate: float, blockers: list[str], activation: list[str], sales_touches: int) -> str:
    classification = _blocker_classification(blockers)
    if classification == "activation" or not activation:
        return "Test guided activation checklist for stalled trials."
    if classification == "commercial":
        return "Test earlier pricing and security qualification."
    if rate < 0.25 and sales_touches == 0:
        return "Test sales assist touchpoint before trial midpoint."
    return "Continue cohort monitoring with current conversion motion."


def _items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    if isinstance(value, str):
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    return []


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "paid", "converted"}


def _int(value: Any) -> int:
    try:
        return max(int(float(str(value or 0))), 0)
    except ValueError:
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
