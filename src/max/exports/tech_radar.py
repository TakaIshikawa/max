"""Technology radar export for technology positioning decisions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

SCHEMA_VERSION = 1
KIND = "tech-radar"


class RadarRing(StrEnum):
    """ThoughtWorks-style radar adoption rings."""

    ADOPT = "adopt"
    TRIAL = "trial"
    ASSESS = "assess"
    HOLD = "hold"


class RadarQuadrant(StrEnum):
    """Technology radar quadrants."""

    LANGUAGES_FRAMEWORKS = "languages-frameworks"
    PLATFORMS = "platforms"
    TOOLS = "tools"
    TECHNIQUES = "techniques"


@dataclass(frozen=True)
class RadarEntry:
    """One technology placement in the radar."""

    name: str
    ring: RadarRing
    quadrant: RadarQuadrant
    score: float
    evidence_count: int
    description: str


def classify_radar_ring(score: float, signals: list[dict[str, Any]] | None = None) -> RadarRing:
    """Classify a technology into a radar ring from score and risk signals."""
    risk_text = " ".join(_signal_text(signal) for signal in signals or [])
    risk_hits = sum(
        1
        for term in ("deprecated", "security risk", "critical", "end of life", "unmaintained")
        if term in risk_text
    )
    normalized = max(0.0, min(float(score), 100.0))
    if risk_hits >= 2 or normalized < 35:
        return RadarRing.HOLD
    if normalized >= 80:
        return RadarRing.ADOPT
    if normalized >= 60:
        return RadarRing.TRIAL
    return RadarRing.ASSESS


def build_tech_radar(
    units: list[Any],
    evaluations: list[dict[str, Any]] | None = None,
    signals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a tech radar from buildable units, evaluations, and technology signals."""
    evaluation_scores = _evaluation_scores(evaluations or [])
    signals_by_tech = _signals_by_tech(signals or [])
    aggregate: dict[str, dict[str, Any]] = {}

    for unit in units:
        unit_score = _unit_score(unit, evaluation_scores)
        for technology in _technologies(unit):
            bucket = aggregate.setdefault(
                technology,
                {"scores": [], "quadrants": [], "descriptions": []},
            )
            bucket["scores"].append(unit_score)
            bucket["quadrants"].append(_quadrant(technology, unit))
            bucket["descriptions"].append(_unit_title(unit))

    entries: list[dict[str, Any]] = []
    for name, bucket in aggregate.items():
        score = round(sum(bucket["scores"]) / len(bucket["scores"]), 1)
        tech_signals = signals_by_tech.get(_normalize(name), [])
        ring = classify_radar_ring(score, tech_signals)
        quadrant = _most_common_quadrant(bucket["quadrants"])
        entries.append(
            {
                "name": name,
                "ring": ring.value,
                "quadrant": quadrant.value,
                "score": score,
                "evidence_count": len(bucket["scores"]) + len(tech_signals),
                "description": _description(name, bucket["descriptions"], tech_signals),
            }
        )

    entries.sort(key=lambda row: (row["quadrant"], _ring_order(row["ring"]), row["name"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "technology_count": len(entries),
            "adopt_count": sum(1 for entry in entries if entry["ring"] == RadarRing.ADOPT.value),
            "hold_count": sum(1 for entry in entries if entry["ring"] == RadarRing.HOLD.value),
        },
        "entries": entries,
    }


def build_tech_radar_export(
    units: list[Any],
    evaluations: list[dict[str, Any]] | None = None,
    signals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Alias for export-style callers."""
    return build_tech_radar(units, evaluations=evaluations, signals=signals)


def render_tech_radar_markdown(report: dict[str, Any]) -> str:
    """Render a technology radar report as Markdown."""
    lines = [
        "# Technology Radar",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "| Technology | Quadrant | Ring | Score | Evidence |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for entry in report.get("entries", []):
        lines.append(
            "| "
            f"{entry['name']} | {entry['quadrant']} | {entry['ring']} | "
            f"{entry['score']:.1f} | {entry['evidence_count']} |"
        )
    if not report.get("entries"):
        lines.append("| No technologies identified |  |  | 0.0 | 0 |")
    return "\n".join(lines).rstrip() + "\n"


def render_tech_radar_json(report: dict[str, Any]) -> str:
    """Render a technology radar report as stable JSON."""
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def _technologies(unit: Any) -> list[str]:
    values: list[str] = []
    for key in ("tech_stack", "technology_stack", "dependencies", "suggested_stack"):
        values.extend(_technology_values(_value(unit, key)))
    solution = _value(unit, "solution")
    if isinstance(solution, dict):
        values.extend(_technology_values(solution.get("suggested_stack")))
        values.extend(_technology_values(solution.get("tech_stack")))
    return sorted(dict.fromkeys(value for value in values if value))


def _technology_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, dict):
        if "name" in value:
            return _technology_values(value["name"])
        values: list[str] = []
        for item in value.values():
            values.extend(_technology_values(item))
        return values
    if isinstance(value, list | tuple | set):
        values: list[str] = []
        for item in value:
            values.extend(_technology_values(item))
        return values
    return [str(value).strip()]


def _unit_score(unit: Any, evaluation_scores: dict[str, float]) -> float:
    unit_id = _text(_value(unit, "id"), _value(unit, "idea_id"))
    if unit_id in evaluation_scores:
        return evaluation_scores[unit_id]
    evaluation = _value(unit, "evaluation")
    if isinstance(evaluation, dict):
        return _number(evaluation, "overall_score", 50.0)
    return _number(_metadata(unit), "overall_score", _number(_metadata(unit), "quality_score", 50.0))


def _evaluation_scores(evaluations: list[dict[str, Any]]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for evaluation in evaluations:
        idea_id = _text(evaluation.get("idea_id"), evaluation.get("id"), evaluation.get("unit_id"))
        if idea_id:
            scores[idea_id] = _number(evaluation, "overall_score", _number(evaluation, "score", 50.0))
    return scores


def _signals_by_tech(signals: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for signal in signals:
        name = _text(
            signal.get("technology"),
            signal.get("dependency_name"),
            signal.get("package_name"),
            signal.get("name"),
        )
        if name:
            grouped.setdefault(_normalize(name), []).append(signal)
    return grouped


def _quadrant(technology: str, unit: Any) -> RadarQuadrant:
    metadata = _metadata(unit)
    explicit = _text(metadata.get("quadrant"), metadata.get("radar_quadrant")).lower()
    for quadrant in RadarQuadrant:
        if explicit in {quadrant.value, quadrant.name.lower()}:
            return quadrant

    text = f"{technology} {_unit_title(unit)}".lower()
    if any(term in text for term in ("postgres", "aws", "gcp", "azure", "slack", "platform")):
        return RadarQuadrant.PLATFORMS
    if any(term in text for term in ("fastapi", "react", "django", "framework", "python", "typescript")):
        return RadarQuadrant.LANGUAGES_FRAMEWORKS
    if any(term in text for term in ("test", "ci", "cli", "monitor", "tool")):
        return RadarQuadrant.TOOLS
    return RadarQuadrant.TECHNIQUES


def _most_common_quadrant(quadrants: list[RadarQuadrant]) -> RadarQuadrant:
    if not quadrants:
        return RadarQuadrant.TOOLS
    return max(sorted(set(quadrants), key=lambda q: q.value), key=quadrants.count)


def _description(name: str, titles: list[str], signals: list[dict[str, Any]]) -> str:
    if signals:
        return f"{name} appears in {len(titles)} buildable unit(s) and {len(signals)} signal(s)."
    return f"{name} appears in {len(titles)} buildable unit(s): {', '.join(titles[:3])}."


def _value(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = _value(unit, "metadata")
    return metadata if isinstance(metadata, dict) else {}


def _unit_title(unit: Any) -> str:
    return _text(_value(unit, "title"), _value(unit, "name"), "Untitled")


def _number(mapping: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(mapping.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _signal_text(signal: dict[str, Any]) -> str:
    return " ".join(
        str(signal.get(key, "")).lower()
        for key in ("title", "content", "summary", "description")
    )


def _normalize(value: str) -> str:
    return "".join(char.lower() for char in value if char.isalnum())


def _text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _ring_order(ring: str) -> int:
    return {
        RadarRing.ADOPT.value: 0,
        RadarRing.TRIAL.value: 1,
        RadarRing.ASSESS.value: 2,
        RadarRing.HOLD.value: 3,
    }.get(ring, 4)
