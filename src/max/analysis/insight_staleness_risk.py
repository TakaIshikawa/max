"""Insight staleness risk report from insight and evidence timestamps."""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.insight_staleness_risk.v1"
KIND = "max.insight_staleness_risk"
CSV_COLUMNS = (
    "insight_id",
    "profile",
    "domain",
    "evidence_count",
    "insight_age_days",
    "newest_evidence_age_days",
    "risk_band",
    "risk_reasons",
)
_RISK_ORDER = {"high": 0, "moderate": 1, "healthy": 2}


@dataclass(frozen=True)
class StalenessThresholds:
    stale_after_days: int = 45
    quiet_after_days: int = 21


@dataclass(frozen=True)
class StalenessRow:
    insight_id: str
    profile: str
    domain: str
    evidence_count: int
    insight_age_days: int
    newest_evidence_age_days: int | None
    risk_band: str
    risk_reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "insight_id": self.insight_id,
            "profile": self.profile,
            "domain": self.domain,
            "evidence_count": self.evidence_count,
            "insight_age_days": self.insight_age_days,
            "newest_evidence_age_days": self.newest_evidence_age_days,
            "risk_band": self.risk_band,
            "risk_reasons": list(self.risk_reasons),
        }


def build_insight_staleness_risk_report(
    store: "Store",
    *,
    limit: int = 500,
    stale_after_days: int = 45,
    quiet_after_days: int = 21,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a deterministic report for aging insights and quiet evidence streams."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if stale_after_days < 1:
        raise ValueError("stale_after_days must be at least 1")
    if quiet_after_days < 1:
        raise ValueError("quiet_after_days must be at least 1")

    current = _aware_utc(now or datetime.now(UTC))
    thresholds = StalenessThresholds(stale_after_days=stale_after_days, quiet_after_days=quiet_after_days)
    signals = store.get_signals(limit=limit)
    signal_map = {signal.id: signal for signal in signals}
    rows = [_row_for_insight(insight, signal_map, thresholds, current) for insight in store.get_insights(limit=limit)]
    rows.sort(key=_row_sort_key)
    risk_counts = Counter(row.risk_band for row in rows)
    stale_rows = [row for row in rows if row.risk_band != "healthy"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {
            "limit": limit,
            "stale_after_days": stale_after_days,
            "quiet_after_days": quiet_after_days,
        },
        "summary": {
            "insight_count": len(rows),
            "high_risk_count": risk_counts.get("high", 0),
            "moderate_risk_count": risk_counts.get("moderate", 0),
            "healthy_count": risk_counts.get("healthy", 0),
            "stale_or_quiet_count": len(stale_rows),
        },
        "rows": [row.as_dict() for row in rows],
        "stale_or_quiet_insights": [row.as_dict() for row in stale_rows],
        "next_actions": _next_actions(stale_rows),
    }


def render_insight_staleness_risk_report(report: Mapping[str, Any], *, fmt: str = "json") -> str:
    """Render insight staleness risk as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported insight staleness risk report format: {fmt}")

    summary = _mapping(report.get("summary"))
    lines = [
        "# Insight Staleness Risk",
        "",
        f"Schema: `{report.get('schema_version')}`",
        f"Insights analyzed: {summary.get('insight_count', 0)}",
        f"High risk: {summary.get('high_risk_count', 0)}",
        f"Moderate risk: {summary.get('moderate_risk_count', 0)}",
        "",
        "## Ranked Insights",
        "",
        "| Insight | Profile | Domain | Evidence | Insight Age | Newest Evidence Age | Risk | Reasons |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    rows = _sorted_row_maps(report.get("rows"))
    if rows:
        for row in rows:
            lines.append(
                "| `{}` | `{}` | `{}` | {} | {} | {} | {} | {} |".format(
                    row.get("insight_id") or "",
                    row.get("profile") or "",
                    row.get("domain") or "",
                    row.get("evidence_count", 0),
                    row.get("insight_age_days", 0),
                    _age_text(row.get("newest_evidence_age_days")),
                    row.get("risk_band") or "",
                    ", ".join(row.get("risk_reasons") or []),
                )
            )
    else:
        lines.append("| none | none | none | 0 | 0 | n/a | healthy |  |")

    lines.extend(["", "## Next Actions", ""])
    actions = report.get("next_actions")
    lines.extend(f"- {item}" for item in actions) if isinstance(actions, list) and actions else lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def _render_csv(report: Mapping[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _sorted_row_maps(report.get("rows")):
        writer.writerow(
            {
                **{key: row.get(key, "") for key in CSV_COLUMNS},
                "newest_evidence_age_days": row.get("newest_evidence_age_days")
                if row.get("newest_evidence_age_days") is not None
                else "",
                "risk_reasons": "; ".join(row.get("risk_reasons") or []),
            }
        )
    return output.getvalue()


def _row_for_insight(
    insight: Any,
    signal_map: Mapping[str, Any],
    thresholds: StalenessThresholds,
    now: datetime,
) -> StalenessRow:
    evidence_ids = list(getattr(insight, "evidence", []) or [])
    evidence = [signal_map[item] for item in evidence_ids if item in signal_map]
    newest_timestamp = max((_signal_timestamp(signal) for signal in evidence), default=None)
    insight_age = _age_days(getattr(insight, "created_at", None), now)
    evidence_age = _age_days(newest_timestamp, now) if newest_timestamp is not None else None
    missing_count = len(evidence_ids) - len(evidence)
    reasons = []
    if insight_age >= thresholds.stale_after_days:
        reasons.append("stale_insight")
    if evidence_age is None:
        reasons.append("no_resolved_evidence")
    elif evidence_age >= thresholds.quiet_after_days:
        reasons.append("quiet_evidence_stream")
    if missing_count > 0:
        reasons.append("unresolved_evidence")

    if "stale_insight" in reasons and ("quiet_evidence_stream" in reasons or "no_resolved_evidence" in reasons):
        risk_band = "high"
    elif reasons:
        risk_band = "moderate"
    else:
        risk_band = "healthy"

    return StalenessRow(
        insight_id=str(getattr(insight, "id", "") or ""),
        profile=_profile(evidence),
        domain=_domain(insight),
        evidence_count=len(evidence_ids),
        insight_age_days=insight_age,
        newest_evidence_age_days=evidence_age,
        risk_band=risk_band,
        risk_reasons=tuple(reasons),
    )


def _next_actions(stale_rows: list[StalenessRow]) -> list[str]:
    if not stale_rows:
        return ["All analyzed insights have recent creation and supporting evidence timestamps."]
    actions = []
    high = [row for row in stale_rows if row.risk_band == "high"]
    moderate = [row for row in stale_rows if row.risk_band == "moderate"]
    if high:
        actions.append(f"Refresh or retire {len(high)} high-risk stale insight(s) before using them for synthesis.")
    if moderate:
        actions.append(f"Review {len(moderate)} moderate-risk insight(s) for missing or quiet supporting evidence.")
    return actions


def _row_sort_key(row: StalenessRow) -> tuple[int, int, int, str]:
    evidence_age = row.newest_evidence_age_days if row.newest_evidence_age_days is not None else 999_999
    return (_RISK_ORDER[row.risk_band], -evidence_age, -row.insight_age_days, row.insight_id)


def _sorted_row_maps(value: Any) -> list[Mapping[str, Any]]:
    rows = _list_of_maps(value)
    return sorted(
        rows,
        key=lambda row: (
            _RISK_ORDER.get(str(row.get("risk_band")), len(_RISK_ORDER)),
            -_int_or_default(row.get("newest_evidence_age_days"), 999_999),
            -_int_or_default(row.get("insight_age_days"), 0),
            str(row.get("insight_id") or ""),
        ),
    )


def _profile(evidence: list[Any]) -> str:
    counts = Counter(str((getattr(signal, "metadata", {}) or {}).get("profile") or "unspecified") for signal in evidence)
    if not counts:
        return "unspecified"
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _domain(insight: Any) -> str:
    domains = list(getattr(insight, "domains", []) or [])
    return str(domains[0]) if domains else "unspecified"


def _signal_timestamp(signal: Any) -> datetime:
    return _aware_utc(getattr(signal, "published_at", None) or getattr(signal, "fetched_at"))


def _age_days(value: Any, now: datetime) -> int:
    timestamp = _aware_utc(value) if isinstance(value, datetime) else now
    return max((now - timestamp).days, 0)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _age_text(value: Any) -> str:
    return "n/a" if value is None else str(value)


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_maps(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []
