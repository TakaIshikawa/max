"""Profile signal mix allocation recommendations from observed source metrics."""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from io import StringIO
from typing import Any


SCHEMA_VERSION = "max.profile_signal_mix_recommendations.v1"
KIND = "max.profile_signal_mix_recommendations"
CSV_COLUMNS = (
    "profile",
    "source",
    "recommendation",
    "priority",
    "observed_volume",
    "observed_share",
    "quality_score",
    "approval_contribution",
    "approval_share",
    "minimum_share",
    "opportunity_score",
    "reasons",
)
_RECOMMENDATION_ORDER = {"increase": 0, "investigate": 1, "decrease": 2, "hold": 3}


@dataclass(frozen=True)
class ProfileSignalMixObservation:
    """Observed profile/source metrics used by the recommendation report."""

    profile: str
    source: str
    observed_volume: int
    quality_score: float
    approval_contribution: float
    minimum_share: float | None = None


@dataclass(frozen=True)
class ProfileSignalMixRecommendation:
    """One allocation recommendation for a profile/source pair."""

    profile: str
    source: str
    recommendation: str
    priority: int
    observed_volume: int
    observed_share: float
    quality_score: float
    approval_contribution: float
    approval_share: float
    minimum_share: float
    opportunity_score: float
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "source": self.source,
            "recommendation": self.recommendation,
            "priority": self.priority,
            "observed_volume": self.observed_volume,
            "observed_share": self.observed_share,
            "quality_score": self.quality_score,
            "approval_contribution": self.approval_contribution,
            "approval_share": self.approval_share,
            "minimum_share": self.minimum_share,
            "opportunity_score": self.opportunity_score,
            "reasons": list(self.reasons),
        }


def build_profile_signal_mix_recommendations(
    observations: Iterable[ProfileSignalMixObservation | Mapping[str, Any]],
    *,
    default_minimum_share: float = 0.1,
    low_quality_threshold: float = 0.35,
    strong_quality_threshold: float = 0.6,
    approval_gap_threshold: float = 0.15,
    top_opportunity_limit: int = 5,
) -> dict[str, Any]:
    """Recommend per-profile source allocation changes from signal mix metrics."""
    if not 0 <= default_minimum_share <= 1:
        raise ValueError("default_minimum_share must be between 0 and 1")
    if not 0 <= low_quality_threshold <= 1:
        raise ValueError("low_quality_threshold must be between 0 and 1")
    if not 0 <= strong_quality_threshold <= 1:
        raise ValueError("strong_quality_threshold must be between 0 and 1")
    if approval_gap_threshold < 0:
        raise ValueError("approval_gap_threshold must be non-negative")
    if top_opportunity_limit < 1:
        raise ValueError("top_opportunity_limit must be at least 1")

    metrics = [_normalize_observation(item, default_minimum_share) for item in observations]
    totals = _profile_totals(metrics)
    rows = [_recommendation_row(item, totals[item.profile], low_quality_threshold, strong_quality_threshold, approval_gap_threshold) for item in metrics]
    rows.sort(key=_row_sort_key)
    counts = Counter(row.recommendation for row in rows)
    top_opportunities = [
        row.as_dict()
        for row in sorted(
            [row for row in rows if row.recommendation in {"increase", "investigate"}],
            key=lambda row: (-row.opportunity_score, _RECOMMENDATION_ORDER[row.recommendation], row.profile, row.source),
        )[:top_opportunity_limit]
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {
            "default_minimum_share": default_minimum_share,
            "low_quality_threshold": low_quality_threshold,
            "strong_quality_threshold": strong_quality_threshold,
            "approval_gap_threshold": approval_gap_threshold,
            "top_opportunity_limit": top_opportunity_limit,
        },
        "summary": {
            "profile_count": len({row.profile for row in rows}),
            "source_count": len(rows),
            "increase_count": counts.get("increase", 0),
            "decrease_count": counts.get("decrease", 0),
            "hold_count": counts.get("hold", 0),
            "investigate_count": counts.get("investigate", 0),
            "top_opportunities": top_opportunities,
        },
        "recommendations": [row.as_dict() for row in rows],
    }


def render_profile_signal_mix_recommendations(report: Mapping[str, Any], *, fmt: str = "json") -> str:
    """Render profile signal mix recommendations as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported profile signal mix recommendations format: {fmt}")

    summary = _mapping(report.get("summary"))
    lines = [
        "# Profile Signal Mix Recommendations",
        "",
        f"Schema: `{report.get('schema_version')}`",
        f"Profiles analyzed: {summary.get('profile_count', 0)}",
        f"Sources analyzed: {summary.get('source_count', 0)}",
        "",
        "## Summary",
        "",
        f"- Increase: {summary.get('increase_count', 0)}",
        f"- Decrease: {summary.get('decrease_count', 0)}",
        f"- Hold: {summary.get('hold_count', 0)}",
        f"- Investigate: {summary.get('investigate_count', 0)}",
        "",
        "## Recommendations",
        "",
        "| Profile | Source | Recommendation | Priority | Volume | Observed Share | Quality | Approval Share | Minimum Share | Reasons |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    rows = _sorted_row_maps(report.get("recommendations"))
    if rows:
        for row in rows:
            lines.append(
                "| `{}` | `{}` | {} | {} | {} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {} |".format(
                    row.get("profile") or "",
                    row.get("source") or "",
                    row.get("recommendation") or "",
                    row.get("priority", 0),
                    row.get("observed_volume", 0),
                    float(row.get("observed_share") or 0.0),
                    float(row.get("quality_score") or 0.0),
                    float(row.get("approval_share") or 0.0),
                    float(row.get("minimum_share") or 0.0),
                    ", ".join(row.get("reasons") or []),
                )
            )
    else:
        lines.append("| none | none | hold | 0 | 0 | 0.000 | 0.000 | 0.000 | 0.000 |  |")

    lines.extend(["", "## Top Opportunities", ""])
    opportunities = _list_of_maps(summary.get("top_opportunities"))
    if opportunities:
        for row in opportunities:
            lines.append(
                "- `{}` / `{}`: {} (score {:.3f})".format(
                    row.get("profile") or "",
                    row.get("source") or "",
                    row.get("recommendation") or "",
                    float(row.get("opportunity_score") or 0.0),
                )
            )
    else:
        lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def _render_csv(report: Mapping[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _sorted_row_maps(report.get("recommendations")):
        writer.writerow({**{key: row.get(key, "") for key in CSV_COLUMNS}, "reasons": "; ".join(row.get("reasons") or [])})
    return output.getvalue()


def _normalize_observation(
    item: ProfileSignalMixObservation | Mapping[str, Any],
    default_minimum_share: float,
) -> ProfileSignalMixObservation:
    if isinstance(item, ProfileSignalMixObservation):
        observation = item
    else:
        observation = ProfileSignalMixObservation(
            profile=str(item.get("profile") or "unspecified"),
            source=str(item.get("source") or item.get("source_adapter") or "unknown"),
            observed_volume=_nonnegative_int(item.get("observed_volume", item.get("signal_count", 0))),
            quality_score=_bounded_rate(item.get("quality_score", 0.0)),
            approval_contribution=_nonnegative_float(item.get("approval_contribution", 0.0)),
            minimum_share=_optional_rate(item.get("minimum_share")),
        )
    if observation.observed_volume < 0:
        raise ValueError("observed_volume must be non-negative")
    return ProfileSignalMixObservation(
        profile=observation.profile or "unspecified",
        source=observation.source or "unknown",
        observed_volume=observation.observed_volume,
        quality_score=_bounded_rate(observation.quality_score),
        approval_contribution=_nonnegative_float(observation.approval_contribution),
        minimum_share=default_minimum_share if observation.minimum_share is None else _bounded_rate(observation.minimum_share),
    )


def _profile_totals(rows: list[ProfileSignalMixObservation]) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, float]] = {}
    for row in rows:
        totals.setdefault(row.profile, {"volume": 0.0, "approval": 0.0})
        totals[row.profile]["volume"] += row.observed_volume
        totals[row.profile]["approval"] += row.approval_contribution
    return totals


def _recommendation_row(
    row: ProfileSignalMixObservation,
    totals: Mapping[str, float],
    low_quality_threshold: float,
    strong_quality_threshold: float,
    approval_gap_threshold: float,
) -> ProfileSignalMixRecommendation:
    total_volume = totals.get("volume", 0.0)
    total_approval = totals.get("approval", 0.0)
    observed_share = round(row.observed_volume / total_volume, 4) if total_volume else 0.0
    approval_share = round(row.approval_contribution / total_approval, 4) if total_approval else 0.0
    minimum_share = float(row.minimum_share or 0.0)
    reasons: list[str] = []

    below_minimum = observed_share < minimum_share
    under_allocated_approval = approval_share >= observed_share + approval_gap_threshold
    weak_quality = row.quality_score <= low_quality_threshold
    strong_quality = row.quality_score >= strong_quality_threshold

    if row.observed_volume == 0:
        recommendation = "investigate"
        reasons.append("No observed signal volume for a configured source floor.")
    elif below_minimum and weak_quality:
        recommendation = "investigate"
        reasons.append("Observed share is below the configured minimum and quality is weak.")
    elif (below_minimum or under_allocated_approval) and not weak_quality:
        recommendation = "increase"
        if below_minimum:
            reasons.append("Observed share is below the configured minimum.")
        if under_allocated_approval:
            reasons.append("Approval contribution outpaces observed signal share.")
    elif observed_share > minimum_share and weak_quality and approval_share < max(observed_share - approval_gap_threshold, observed_share * 0.5):
        recommendation = "decrease"
        reasons.append("Observed share is high relative to weak quality and approval contribution.")
    else:
        recommendation = "hold"
        reasons.append("Observed volume, quality, approval contribution, and minimum share are balanced.")

    if strong_quality and recommendation in {"increase", "hold"}:
        reasons.append("Quality score is strong.")

    opportunity_score = _opportunity_score(
        recommendation=recommendation,
        observed_share=observed_share,
        approval_share=approval_share,
        minimum_share=minimum_share,
        quality_score=row.quality_score,
    )
    return ProfileSignalMixRecommendation(
        profile=row.profile,
        source=row.source,
        recommendation=recommendation,
        priority=_priority(recommendation, opportunity_score),
        observed_volume=row.observed_volume,
        observed_share=observed_share,
        quality_score=round(row.quality_score, 4),
        approval_contribution=round(row.approval_contribution, 4),
        approval_share=approval_share,
        minimum_share=round(minimum_share, 4),
        opportunity_score=opportunity_score,
        reasons=tuple(reasons),
    )


def _opportunity_score(
    *,
    recommendation: str,
    observed_share: float,
    approval_share: float,
    minimum_share: float,
    quality_score: float,
) -> float:
    if recommendation == "increase":
        return round(max(minimum_share - observed_share, 0.0) + max(approval_share - observed_share, 0.0) + quality_score, 4)
    if recommendation == "investigate":
        return round(max(minimum_share - observed_share, 0.0) + (1.0 - quality_score), 4)
    if recommendation == "decrease":
        return round(max(observed_share - approval_share, 0.0) + (1.0 - quality_score), 4)
    return round(quality_score, 4)


def _priority(recommendation: str, opportunity_score: float) -> int:
    if recommendation == "hold":
        return 3
    if opportunity_score >= 1.0:
        return 1
    return 2


def _row_sort_key(row: ProfileSignalMixRecommendation) -> tuple[int, int, float, str, str]:
    return (_RECOMMENDATION_ORDER[row.recommendation], row.priority, -row.opportunity_score, row.profile, row.source)


def _sorted_row_maps(value: Any) -> list[Mapping[str, Any]]:
    rows = _list_of_maps(value)
    return sorted(
        rows,
        key=lambda row: (
            _RECOMMENDATION_ORDER.get(str(row.get("recommendation")), len(_RECOMMENDATION_ORDER)),
            _nonnegative_int(row.get("priority", 99)),
            -_nonnegative_float(row.get("opportunity_score", 0.0)),
            str(row.get("profile") or ""),
            str(row.get("source") or ""),
        ),
    )


def _optional_rate(value: Any) -> float | None:
    return None if value is None else _bounded_rate(value)


def _bounded_rate(value: Any) -> float:
    try:
        return min(max(float(value or 0.0), 0.0), 1.0)
    except (TypeError, ValueError):
        return 0.0


def _nonnegative_float(value: Any) -> float:
    try:
        return max(float(value or 0.0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def _nonnegative_int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_maps(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []
