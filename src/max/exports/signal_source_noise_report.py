"""Signal source noise export report."""

from __future__ import annotations

import json
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.signal_source_noise_report.v1"
KIND = "max.signal_source_noise_report"


class SignalSourceNoiseInput(TypedDict, total=False):
    source: str
    fetched_count: int | float | str
    discarded_count: int | float | str
    duplicate_count: int | float | str
    low_confidence_count: int | float | str
    low_relevance_count: int | float | str


def build_signal_source_noise_report(records: Iterable[SignalSourceNoiseInput | dict[str, Any]], *, title: str = "Signal Source Noise Report") -> dict[str, Any]:
    rows = [_row(raw, index) for index, raw in enumerate(records)]
    rows.sort(key=lambda row: (-row["noise_rate"], -row["duplicate_rate"], row["source"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(title) or "Signal Source Noise Report",
        "summary": {"source_count": len(rows), "fetched_count": sum(row["fetched_count"] for row in rows), "retained_count": sum(row["retained_count"] for row in rows)},
        "sources": rows,
        "noisy_sources": [row for row in rows if row["noise_rate"] >= 0.25],
        "remediation_hints": [{"source": row["source"], "hint": _hint(row)} for row in rows if row["noise_rate"] >= 0.25],
    }


def render_signal_source_noise_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report.get('title') or 'Signal Source Noise Report'}", "", "## Noisy Sources", ""]
    noisy = report.get("noisy_sources") or []
    if not noisy:
        lines.append("- No noisy sources detected.")
    else:
        for row in noisy:
            lines.append(f"- {row['source']}: {row['noise_rate']:.1%} noise, {row['retained_count']} retained")
    lines.extend(["", "## Remediation Hints", ""])
    lines.extend([f"- {row['source']}: {row['hint']}" for row in report.get("remediation_hints") or []] or ["- No remediation hints required."])
    return "\n".join(lines).rstrip() + "\n"


def render_signal_source_noise_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _row(raw: dict[str, Any], index: int) -> dict[str, Any]:
    fetched = _int(raw.get("fetched_count") or raw.get("fetched"))
    discarded = _int(raw.get("discarded_count") or raw.get("discarded"))
    duplicate = _int(raw.get("duplicate_count") or raw.get("duplicates"))
    low_confidence = _int(raw.get("low_confidence_count") or raw.get("low_confidence"))
    low_relevance = _int(raw.get("low_relevance_count") or raw.get("low_relevance"))
    noisy = discarded + duplicate + low_confidence + low_relevance
    return {"source": _text(raw.get("source")) or f"source-{index + 1}", "fetched_count": fetched, "discarded_count": discarded, "duplicate_count": duplicate, "low_confidence_count": low_confidence, "low_relevance_count": low_relevance, "retained_count": max(fetched - noisy, 0), "noise_rate": _rate(noisy, fetched), "duplicate_rate": _rate(duplicate, fetched), "low_confidence_rate": _rate(low_confidence, fetched), "low_relevance_rate": _rate(low_relevance, fetched)}


def _hint(row: dict[str, Any]) -> str:
    if row["duplicate_rate"] >= 0.15:
        return "Tighten deduplication keys before ingestion."
    if row["low_confidence_rate"] >= 0.15:
        return "Raise source confidence filters."
    return "Review discard and relevance thresholds."


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
