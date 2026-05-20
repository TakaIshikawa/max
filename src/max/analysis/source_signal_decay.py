"""Rank external sources by signal decay risk."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Mapping


SCHEMA_VERSION = "max.source_signal_decay.v1"
KIND = "max.source_signal_decay"


def build_source_signal_decay_analysis(
    sources: list[Mapping[str, Any]],
    *,
    as_of: date | datetime | str | None = None,
    stale_after_days: int = 45,
) -> dict[str, Any]:
    """Analyze source-level signal counts and rank highest decay risk first."""

    analysis_date = _as_date(as_of) or date.today()
    rows = [_source_row(source, index, analysis_date, stale_after_days) for index, source in enumerate(sources)]
    rows.sort(key=lambda row: (-float(row["decay_risk_score"]), str(row["source"])))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "source_count": len(rows),
            "critical_count": sum(1 for row in rows if row["decay_risk"] == "critical"),
            "high_count": sum(1 for row in rows if row["decay_risk"] == "high"),
            "fallback_count": sum(1 for row in rows if row["fallback_status"] != "ok"),
        },
        "as_of": analysis_date.isoformat(),
        "decay_rows": rows,
    }


def render_source_signal_decay_markdown(analysis: Mapping[str, Any]) -> str:
    """Render source signal decay analysis as deterministic Markdown."""

    summary = analysis["summary"]
    lines = [
        "# Source Signal Decay Analysis",
        "",
        f"Schema: `{analysis['schema_version']}`",
        f"As of: {analysis['as_of']}",
        f"Sources analyzed: {summary['source_count']}",
        "",
        "## Decay Risk Queue",
        "",
    ]

    rows = list(analysis.get("decay_rows", []))
    if rows:
        for row in rows:
            lines.extend(
                [
                    f"### {row['source']}",
                    "",
                    f"- Decay risk: {row['decay_risk']}",
                    f"- Last-seen age: {row['last_seen_age_days']} day(s)",
                    f"- Volume trend: {row['volume_trend']}",
                    f"- Recommended action: {row['recommended_action']}",
                    "",
                ]
            )
    else:
        lines.append("No source signal inputs were provided.")

    return "\n".join(lines).rstrip() + "\n"


def _source_row(source: Mapping[str, Any], index: int, as_of: date, stale_after_days: int) -> dict[str, Any]:
    name = _clean(source.get("source") or source.get("name") or source.get("id") or f"source-{index + 1}")
    recent = _nonnegative_float(source.get("recent_count", source.get("new_signal_count", 0)))
    historical = _nonnegative_float(source.get("historical_count", source.get("old_signal_count", 0)))
    newest = _as_date(source.get("newest_timestamp") or source.get("newest_at") or source.get("last_seen_at"))
    oldest = _as_date(source.get("oldest_timestamp") or source.get("oldest_at") or source.get("first_seen_at"))
    quality = _bounded_float(source.get("quality_score", source.get("quality", 0.5)))

    fallback_status = "ok"
    if newest is None:
        fallback_status = "missing_newest_timestamp"
    elif historical == 0:
        fallback_status = "zero_historical_volume"

    last_seen_age = max(0, (as_of - newest).days) if newest else 9999
    trend_ratio = recent / historical if historical > 0 else None
    volume_trend = _volume_trend(trend_ratio, fallback_status)
    decay_score = _decay_score(last_seen_age, trend_ratio, quality, fallback_status, stale_after_days)
    risk = _risk(decay_score, fallback_status)

    return {
        "source": name,
        "recent_count": round(recent, 4),
        "historical_count": round(historical, 4),
        "newest_timestamp": newest.isoformat() if newest else None,
        "oldest_timestamp": oldest.isoformat() if oldest else None,
        "last_seen_age_days": last_seen_age,
        "quality_score": quality,
        "volume_trend": volume_trend,
        "trend_ratio": round(trend_ratio, 4) if trend_ratio is not None else None,
        "fallback_status": fallback_status,
        "decay_risk_score": decay_score,
        "decay_risk": risk,
        "recommended_action": _recommended_action(risk, fallback_status, volume_trend),
    }


def _decay_score(
    last_seen_age: int,
    trend_ratio: float | None,
    quality: float,
    fallback_status: str,
    stale_after_days: int,
) -> float:
    if fallback_status == "missing_newest_timestamp":
        return 1.0
    if fallback_status == "zero_historical_volume":
        return 0.55
    age_risk = min(1.0, last_seen_age / max(1, stale_after_days))
    trend_risk = 1.0 - min(1.0, trend_ratio if trend_ratio is not None else 0.0)
    quality_risk = 1.0 - quality
    return round(age_risk * 0.45 + trend_risk * 0.40 + quality_risk * 0.15, 4)


def _risk(score: float, fallback_status: str) -> str:
    if fallback_status == "missing_newest_timestamp":
        return "critical"
    if score >= 0.75:
        return "critical"
    if score >= 0.50:
        return "high"
    if score >= 0.30:
        return "moderate"
    return "low"


def _volume_trend(trend_ratio: float | None, fallback_status: str) -> str:
    if fallback_status == "missing_newest_timestamp":
        return "unknown_missing_timestamp"
    if fallback_status == "zero_historical_volume":
        return "new_or_unbaselined"
    if trend_ratio is None:
        return "unknown"
    if trend_ratio < 0.4:
        return "rapid_decline"
    if trend_ratio < 0.8:
        return "declining"
    if trend_ratio <= 1.2:
        return "stable"
    return "growing"


def _recommended_action(risk: str, fallback_status: str, volume_trend: str) -> str:
    if fallback_status == "missing_newest_timestamp":
        return "repair timestamp ingestion before using this source for freshness decisions"
    if fallback_status == "zero_historical_volume":
        return "collect baseline volume before ranking long-term decay"
    if risk in {"critical", "high"} and volume_trend == "rapid_decline":
        return "refresh source query strategy and inspect adapter health"
    if risk in {"critical", "high"}:
        return "increase monitoring and verify whether the source is stale"
    if volume_trend == "growing":
        return "keep source active and watch for quality drift"
    return "maintain current source cadence"


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


def _bounded_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return round(max(0.0, min(1.0, number)), 4)


def _nonnegative_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return max(0.0, number)


def _clean(value: Any) -> str:
    return str(value or "").strip()
