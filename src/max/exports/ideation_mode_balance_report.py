"""Ideation mode balance export report."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "max.ideation_mode_balance_report.v1"
KIND = "max.ideation_mode_balance_report"
DEFAULT_TARGET_RATIOS = {"direct": 0.5, "refinement": 0.3, "cross-domain": 0.2}


def generate_ideation_mode_balance_report(
    records: Iterable[dict[str, Any]],
    *,
    target_ratios: Mapping[str, float] | None = None,
    tolerance: float = 0.1,
) -> dict[str, Any]:
    targets = {(_text(key) or "unknown").lower(): _ratio(value) for key, value in (target_ratios or DEFAULT_TARGET_RATIOS).items()}
    allowed_delta = max(0.0, _float(tolerance))
    groups: dict[str, dict[str, int]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        profile = _text(raw.get("profile") or raw.get("domain_profile") or raw.get("profile_id")) or "default"
        mode = _mode(raw)
        groups.setdefault(profile, {})[mode] = groups.setdefault(profile, {}).get(mode, 0) + _count(raw)

    rows = []
    for profile, counts in groups.items():
        total = sum(counts.values())
        details = []
        statuses = set()
        for mode in sorted(set(targets) | set(counts), key=str.lower):
            observed = round(counts.get(mode, 0) / total, 4) if total else 0.0
            target = targets.get(mode, 0.0)
            delta = round(observed - target, 4)
            status = "missing" if target and not counts.get(mode) else ("overrepresented" if delta > allowed_delta else ("underrepresented" if delta < -allowed_delta else "balanced"))
            statuses.add(status)
            details.append({"mode": mode, "count": counts.get(mode, 0), "observed_ratio": observed, "target_ratio": target, "delta": delta, "status": status})
        row_status = "imbalanced" if statuses - {"balanced"} else "balanced"
        rows.append({"profile": profile, "total_count": total, "modes": details, "missing_modes": [item["mode"] for item in details if item["status"] == "missing"], "underrepresented_modes": [item["mode"] for item in details if item["status"] == "underrepresented"], "overrepresented_modes": [item["mode"] for item in details if item["status"] == "overrepresented"], "status": row_status})
    rows.sort(key=lambda row: (row["status"] != "imbalanced", row["profile"].casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"row_count": len(rows), "imbalanced_count": sum(1 for row in rows if row["status"] == "imbalanced"), "tolerance": allowed_delta, "target_ratios": targets}, "rows": rows}


def _mode(raw: dict[str, Any]) -> str:
    value = _text(raw.get("ideation_mode") or raw.get("mode") or raw.get("generation_mode")).lower().replace("_", "-")
    return value or "unknown"


def _count(raw: dict[str, Any]) -> int:
    return max(1, _int(raw.get("count") or raw.get("unit_count")))


def _ratio(value: Any) -> float:
    return min(1.0, max(0.0, _float(value)))


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
