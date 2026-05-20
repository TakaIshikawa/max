"""Audit synthesized insights for stale evidence and refresh needs."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Mapping


SCHEMA_VERSION = "max.insight_staleness_audit.v1"
KIND = "max.insight_staleness_audit"


def build_insight_staleness_audit(
    insights: list[Mapping[str, Any]],
    *,
    as_of: date | datetime | str | None = None,
    stale_after_days: int = 45,
    current_after_days: int = 21,
    strong_corroboration_count: int = 2,
) -> dict[str, Any]:
    """Audit insights for stale evidence, outdated confidence, and corroboration gaps."""

    audit_date = _as_date(as_of) or date.today()
    rows = [
        _insight_row(insight, index, audit_date, stale_after_days, current_after_days, strong_corroboration_count)
        for index, insight in enumerate(insights)
    ]
    rows.sort(key=lambda row: (_tier_order(row["staleness_tier"]), -int(row["age_days"]), str(row["insight_id"])))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "insight_count": len(rows),
            "stale_count": sum(1 for row in rows if row["staleness_tier"] == "stale"),
            "watch_count": sum(1 for row in rows if row["staleness_tier"] == "watch"),
            "current_count": sum(1 for row in rows if row["staleness_tier"] == "current"),
        },
        "as_of": audit_date.isoformat(),
        "staleness_rows": rows,
    }


def render_insight_staleness_audit_markdown(audit: Mapping[str, Any]) -> str:
    """Render an insight staleness audit as deterministic Markdown."""

    summary = audit["summary"]
    lines = [
        "# Insight Staleness Audit",
        "",
        f"Schema: `{audit['schema_version']}`",
        f"As of: {audit['as_of']}",
        f"Insights analyzed: {summary['insight_count']}",
        "",
        "## Staleness Summary",
        "",
        f"- Stale: {summary['stale_count']}",
        f"- Watch: {summary['watch_count']}",
        f"- Current: {summary['current_count']}",
        "",
        "## Refresh Queue",
        "",
    ]

    rows = list(audit.get("staleness_rows", []))
    if rows:
        for row in rows:
            lines.extend(
                [
                    f"### {row['insight_id']}",
                    "",
                    f"- Age: {row['age_days']} day(s)",
                    f"- Corroborating sources: {row['corroborating_source_count']}",
                    f"- Confidence: {row['confidence']:.2f}",
                    f"- Staleness tier: {row['staleness_tier']}",
                    f"- Refresh action: {row['refresh_action']}",
                    "",
                ]
            )
    else:
        lines.append("No synthesized insights were provided.")

    return "\n".join(lines).rstrip() + "\n"


def _insight_row(
    insight: Mapping[str, Any],
    index: int,
    as_of: date,
    stale_after_days: int,
    current_after_days: int,
    strong_corroboration_count: int,
) -> dict[str, Any]:
    insight_id = _clean(insight.get("insight_id") or insight.get("id") or f"insight-{index + 1}")
    confidence = _bounded_float(insight.get("confidence", 0.5))
    evidence_dates = [_as_date(value) for value in _values(insight.get("evidence_dates", insight.get("evidence_at")))]
    evidence_dates.extend(
        _as_date(item.get("observed_at") or item.get("date") or item.get("created_at"))
        for item in insight.get("evidence", [])
        if isinstance(item, Mapping)
    )
    evidence_dates = [value for value in evidence_dates if value is not None]
    latest = max(evidence_dates) if evidence_dates else None
    age_days = max(0, (as_of - latest).days) if latest else 9999
    recent_count = sum(1 for value in evidence_dates if 0 <= (as_of - value).days <= current_after_days)
    sources = {
        _clean(item.get("source") or item.get("source_id"))
        for item in insight.get("evidence", [])
        if isinstance(item, Mapping) and _clean(item.get("source") or item.get("source_id"))
    }
    explicit_sources = {_clean(value) for value in _values(insight.get("corroborating_sources", [])) if _clean(value)}
    source_count = _nonnegative_int(
        insight.get("corroborating_source_count", insight.get("source_count", len(sources | explicit_sources)))
    )
    if source_count == 0:
        source_count = len(sources | explicit_sources)

    tier = _staleness_tier(age_days, recent_count, source_count, confidence, stale_after_days, strong_corroboration_count)
    return {
        "insight_id": insight_id,
        "age_days": age_days,
        "latest_evidence_at": latest.isoformat() if latest else None,
        "corroborating_source_count": source_count,
        "recent_corroboration_count": recent_count,
        "confidence": confidence,
        "staleness_tier": tier,
        "refresh_action": _refresh_action(tier, age_days, source_count, confidence),
    }


def _staleness_tier(
    age_days: int,
    recent_count: int,
    source_count: int,
    confidence: float,
    stale_after_days: int,
    strong_corroboration_count: int,
) -> str:
    if recent_count >= strong_corroboration_count and source_count >= strong_corroboration_count:
        return "current"
    if age_days > stale_after_days or confidence < 0.35:
        return "stale"
    if age_days > stale_after_days * 0.65 or source_count < strong_corroboration_count:
        return "watch"
    return "current"


def _refresh_action(tier: str, age_days: int, source_count: int, confidence: float) -> str:
    if tier == "stale" and confidence < 0.35:
        return "refresh evidence and recalibrate confidence before reuse"
    if tier == "stale":
        return f"collect recent corroboration because latest evidence is {age_days} day(s) old"
    if tier == "watch" and source_count < 2:
        return "add an independent corroborating source"
    if tier == "watch":
        return "schedule refresh during the next synthesis cycle"
    return "no refresh needed; retain current evidence cadence"


def _values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def _tier_order(tier: str) -> int:
    return {"stale": 0, "watch": 1, "current": 2}.get(tier, 3)


def _bounded_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return round(max(0.0, min(1.0, number)), 4)


def _nonnegative_int(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    return max(0, number)


def _clean(value: Any) -> str:
    return str(value or "").strip()
