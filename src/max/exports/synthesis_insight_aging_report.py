"""Synthesis insight aging export report."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

SCHEMA_VERSION = "max.synthesis_insight_aging_report.v1"
KIND = "max.synthesis_insight_aging_report"


def generate_synthesis_insight_aging_report(records: Iterable[dict[str, Any]], *, now: str = "2026-05-29T00:00:00+00:00", warning_age_days: int = 14, critical_age_days: int = 30, title: str = "Synthesis Insight Aging Report") -> dict[str, Any]:
    now_dt = _dt(now)
    groups: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(lambda: {"insight_count": 0, "converted_count": 0, "ages": []})
    for raw in records:
        if not isinstance(raw, dict):
            continue
        age = _age(raw, now_dt)
        if age < warning_age_days and _converted(raw):
            continue
        key = (_text(raw.get("profile")) or "unknown-profile", _text(raw.get("theme")) or "unknown-theme", _band(raw.get("confidence") or raw.get("confidence_score")))
        group = groups[key]
        group["insight_count"] += 1
        group["ages"].append(age)
        if _converted(raw):
            group["converted_count"] += 1
    rows = [_row(*key, group, warning_age_days, critical_age_days) for key, group in groups.items()]
    rows.sort(key=lambda r: (_severity_rank(r["severity"]), -r["oldest_age_days"], r["profile"].lower(), r["theme"].lower(), r["confidence_band"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "title": title, "summary": {"row_count": len(rows), "insight_count": sum(r["insight_count"] for r in rows), "unconverted_count": sum(r["unconverted_count"] for r in rows), "warning_age_days": warning_age_days, "critical_age_days": critical_age_days}, "rows": rows}


def render_synthesis_insight_aging_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_synthesis_insight_aging_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report.get('title') or 'Synthesis Insight Aging Report'}", "", "## Summary", "", f"- Insights: {report.get('summary', {}).get('insight_count', 0)}", "", "## Aging Rows", ""]
    rows = report.get("rows") or []
    lines.extend([f"- {r['profile']} / {r['theme']} / {r['confidence_band']}: {r['unconverted_count']} unconverted, oldest {r['oldest_age_days']} days ({r['severity']})" for r in rows] or ["- No aged synthesis insights detected."])
    return "\n".join(lines).rstrip() + "\n"


def _row(profile: str, theme: str, band: str, group: dict[str, Any], warning: int, critical: int) -> dict[str, Any]:
    unconverted = group["insight_count"] - group["converted_count"]
    oldest = max(group["ages"] or [0])
    severity = "critical" if oldest >= critical and unconverted else "high" if unconverted else "low"
    return {"profile": profile, "theme": theme, "confidence_band": band, "insight_count": group["insight_count"], "converted_count": group["converted_count"], "unconverted_count": unconverted, "oldest_age_days": oldest, "conversion_ratio": _ratio(group["converted_count"], group["insight_count"]), "severity": severity, "recommended_action": "Assign owner to convert or archive aged insights." if unconverted else "No action required beyond routine review."}


def _age(raw: dict[str, Any], now: datetime) -> int:
    if raw.get("age_days") is not None:
        return _int(raw.get("age_days"))
    created = _dt(raw.get("created_at") or raw.get("first_seen_at") or raw.get("insight_at"))
    return max((now - created).days, 0)


def _dt(value: Any) -> datetime:
    text = _text(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime(2026, 5, 29, tzinfo=timezone.utc)


def _converted(raw: dict[str, Any]) -> bool:
    return _bool(raw.get("converted") or raw.get("buildable_unit_id")) or _text(raw.get("status")).lower() in {"converted", "built"}


def _band(value: Any) -> str:
    score = _float(value)
    return "high" if score >= 0.75 else "medium" if score >= 0.4 else "low"


def _ratio(n: int, d: int) -> float:
    return round(n / d, 4) if d else 0.0


def _severity_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(value, 4)


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _bool(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes", "y"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
