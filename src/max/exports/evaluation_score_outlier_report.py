"""Evaluation score outlier export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.evaluation_score_outlier_report.v1"
KIND = "max.evaluation_score_outlier_report"
_REJECT = {"reject", "rejected", "fail", "failed", "revise", "needs work"}
_APPROVE = {"approve", "approved", "accept", "accepted", "ship", "pass", "passed"}


def generate_evaluation_score_outlier_report(
    records: Iterable[dict[str, Any]],
    *,
    outlier_delta: float = 0.2,
    high_score_threshold: float = 0.8,
    low_score_threshold: float = 0.4,
) -> dict[str, Any]:
    rows = [_row(raw, index) for index, raw in enumerate(records, start=1) if isinstance(raw, dict)]
    baselines = _baselines(rows)
    threshold = max(0.0, _float(outlier_delta))
    output = []
    for row in rows:
        profile_baseline = baselines["profiles"].get(row["profile"], {})
        global_baseline = baselines["global"]
        outliers = []
        for dimension, score in row["scores"].items():
            baseline = profile_baseline.get(dimension, global_baseline.get(dimension, 0.0))
            delta = round(score - baseline, 4)
            if abs(delta) >= threshold:
                outliers.append({"dimension": dimension, "score": score, "baseline": round(baseline, 4), "delta": delta, "direction": "high" if delta > 0 else "low"})
        mismatch = _mismatch(row["recommendation"], row["average_score"], high_score_threshold, low_score_threshold)
        status = "mismatch" if mismatch else ("outlier" if outliers else "normal")
        output.append({**row, "outliers": sorted(outliers, key=lambda item: (item["dimension"], item["direction"])), "recommendation_mismatch": mismatch, "status": status})
    output.sort(key=lambda row: ({"mismatch": 0, "outlier": 1, "normal": 2}[row["status"]], row["profile"].casefold(), row["unit_id"].casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"row_count": len(output), "outlier_count": sum(1 for row in output if row["outliers"]), "mismatch_count": sum(1 for row in output if row["recommendation_mismatch"]), "outlier_delta": threshold}, "baselines": baselines, "rows": output}


def _row(raw: dict[str, Any], index: int) -> dict[str, Any]:
    scores = _scores(raw)
    average = round(sum(scores.values()) / len(scores), 4) if scores else 0.0
    return {"unit_id": _text(raw.get("unit_id") or raw.get("buildable_unit_id") or raw.get("id")) or f"unit-{index}", "profile": _text(raw.get("profile") or raw.get("domain_profile")) or "default", "recommendation": _text(raw.get("recommendation") or raw.get("decision") or raw.get("verdict")).lower(), "scores": scores, "average_score": average}


def _scores(raw: dict[str, Any]) -> dict[str, float]:
    value = raw.get("scores") or raw.get("dimension_scores")
    if isinstance(value, dict):
        return {str(key): round(_float(score), 4) for key, score in value.items()}
    return {str(key.removesuffix("_score")): round(_float(value), 4) for key, value in raw.items() if str(key).endswith("_score")}


def _baselines(rows: list[dict[str, Any]]) -> dict[str, Any]:
    global_scores: dict[str, list[float]] = {}
    profile_scores: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        profile = profile_scores.setdefault(row["profile"], {})
        for dimension, score in row["scores"].items():
            global_scores.setdefault(dimension, []).append(score)
            profile.setdefault(dimension, []).append(score)
    return {"global": {key: round(sum(values) / len(values), 4) for key, values in sorted(global_scores.items())}, "profiles": {profile: {key: round(sum(values) / len(values), 4) for key, values in sorted(scores.items())} for profile, scores in sorted(profile_scores.items())}}


def _mismatch(recommendation: str, average: float, high: float, low: float) -> bool:
    return (average >= high and recommendation in _REJECT) or (average <= low and recommendation in _APPROVE)


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
