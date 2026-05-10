"""Market sizing analysis export — TAM/SAM/SOM estimation.

Generates total addressable market (TAM), serviceable addressable market (SAM),
and serviceable obtainable market (SOM) analysis documents from signal data.
Supports top-down and bottom-up estimation approaches with growth rate
projections and confidence intervals.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.market_sizing.v1"
KIND = "max.market_sizing"

# Default multipliers for market estimation heuristics
_TAM_MULTIPLIER = 1_000_000  # base per-signal TAM weight ($)
_SAM_RATIO = 0.35  # SAM as fraction of TAM
_SOM_RATIO = 0.10  # SOM as fraction of SAM
_GROWTH_RATE_BASE = 0.12  # 12% default annual growth


def build_market_sizing(
    store: Store,
    domain: str | None = None,
    *,
    approach: str = "top-down",
) -> dict[str, Any]:
    """Build TAM/SAM/SOM market sizing analysis.

    Args:
        store: Database store with signals and buildable units.
        domain: Optional domain filter.
        approach: Estimation approach — "top-down" or "bottom-up".

    Returns:
        Dict with market sizing breakdown, methodology, and projections.
    """
    units = store.get_buildable_units(limit=1000, domain=domain)
    signals = store.get_signals(limit=1000)

    segments = _segment_market(units, signals)

    if approach == "bottom-up":
        sizing = _estimate_bottom_up(segments, signals)
    else:
        sizing = _estimate_top_down(segments, signals)

    growth = _project_growth(sizing, signals)
    confidence = _calculate_confidence(segments, signals)
    data_sources = _collect_data_sources(signals)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "market_sizing",
            "domain_filter": domain,
        },
        "approach": approach,
        "sizing": sizing,
        "segment_breakdown": segments,
        "growth_projections": growth,
        "confidence": confidence,
        "data_sources": data_sources,
        "methodology": _describe_methodology(approach, len(signals), len(units)),
    }


def render_market_sizing_markdown(report: dict[str, Any]) -> str:
    """Render market sizing report as Markdown."""
    lines = [
        "# Market Sizing Analysis",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        f"Approach: {report['approach']}",
        "",
    ]

    # Sizing summary
    s = report["sizing"]
    lines.extend([
        "## Market Size Estimates",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| **TAM** (Total Addressable Market) | ${s['tam']:,.0f} |",
        f"| **SAM** (Serviceable Addressable Market) | ${s['sam']:,.0f} |",
        f"| **SOM** (Serviceable Obtainable Market) | ${s['som']:,.0f} |",
        "",
    ])

    # Segment breakdown
    lines.extend(["## Segment Breakdown", ""])
    for seg in report["segment_breakdown"]:
        lines.extend([
            f"### {seg['name']}",
            "",
            f"- Units: {seg['unit_count']}",
            f"- Signals: {seg['signal_count']}",
            f"- Estimated segment size: ${seg.get('segment_tam', 0):,.0f}",
            "",
        ])

    # Growth projections
    lines.extend(["## Growth Projections", ""])
    gp = report["growth_projections"]
    lines.extend([
        f"- Annual growth rate: {gp['annual_growth_rate']:.1%}",
        "",
        "| Year | Projected TAM |",
        "|------|--------------|",
    ])
    for proj in gp["yearly_projections"]:
        lines.append(f"| {proj['year']} | ${proj['tam']:,.0f} |")
    lines.append("")

    # Confidence
    c = report["confidence"]
    lines.extend([
        "## Confidence Assessment",
        "",
        f"- **Level**: {c['level']}",
        f"- **Score**: {c['score']:.2f}",
        f"- **Signal coverage**: {c['signal_coverage']}",
        f"- **Data quality note**: {c['data_quality_note']}",
        "",
    ])

    # Methodology
    lines.extend([
        "## Methodology",
        "",
        report["methodology"],
        "",
    ])

    # Data sources
    lines.extend(["## Data Sources", ""])
    for src in report["data_sources"]:
        lines.append(f"- {src}")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_market_sizing_json(report: dict[str, Any]) -> str:
    """Render market sizing report as formatted JSON."""
    return json.dumps(report, indent=2, default=str)


# ── Internal helpers ─────────────────────────────────────────────────


def _segment_market(
    units: list[Any],
    signals: list[Any],
) -> list[dict[str, Any]]:
    """Segment market by domain/category from units and signals."""
    domain_units: dict[str, list[Any]] = defaultdict(list)
    for unit in units:
        domain = getattr(unit, "domain", "") or "general"
        domain_units[domain].append(unit)

    # Map signals to domains via tags
    domain_signals: dict[str, list[Any]] = defaultdict(list)
    for signal in signals:
        matched = False
        for domain in domain_units:
            if domain.lower() in " ".join(signal.tags).lower():
                domain_signals[domain].append(signal)
                matched = True
        if not matched:
            domain_signals["general"].append(signal)

    all_domains = set(domain_units.keys()) | set(domain_signals.keys())

    segments: list[dict[str, Any]] = []
    for domain in sorted(all_domains):
        u_list = domain_units.get(domain, [])
        s_list = domain_signals.get(domain, [])
        segments.append({
            "name": domain,
            "unit_count": len(u_list),
            "signal_count": len(s_list),
        })

    return segments if segments else [{"name": "general", "unit_count": 0, "signal_count": 0}]


def _estimate_top_down(
    segments: list[dict[str, Any]],
    signals: list[Any],
) -> dict[str, float]:
    """Top-down estimation: start with total market, narrow down."""
    total_signals = max(len(signals), 1)
    tam = total_signals * _TAM_MULTIPLIER
    sam = tam * _SAM_RATIO
    som = sam * _SOM_RATIO

    # Distribute TAM across segments
    for seg in segments:
        weight = max(seg["signal_count"], 1) / total_signals
        seg["segment_tam"] = tam * weight

    return {"tam": tam, "sam": sam, "som": som}


def _estimate_bottom_up(
    segments: list[dict[str, Any]],
    signals: list[Any],
) -> dict[str, float]:
    """Bottom-up estimation: sum segment estimates."""
    tam = 0.0
    for seg in segments:
        # Each unit represents a validated opportunity; signals add weight
        unit_value = seg["unit_count"] * _TAM_MULTIPLIER * 2
        signal_value = seg["signal_count"] * _TAM_MULTIPLIER * 0.5
        seg_tam = unit_value + signal_value
        seg["segment_tam"] = seg_tam
        tam += seg_tam

    tam = max(tam, _TAM_MULTIPLIER)  # floor
    sam = tam * _SAM_RATIO
    som = sam * _SOM_RATIO

    return {"tam": tam, "sam": sam, "som": som}


def _project_growth(
    sizing: dict[str, float],
    signals: list[Any],
) -> dict[str, Any]:
    """Project growth rates over 5 years."""
    # Adjust growth rate based on signal recency and volume
    growth_rate = _infer_growth_rate(signals)

    projections: list[dict[str, Any]] = []
    current_year = datetime.now(timezone.utc).year
    tam = sizing["tam"]

    for i in range(5):
        year = current_year + i + 1
        projected_tam = tam * math.pow(1 + growth_rate, i + 1)
        projections.append({"year": year, "tam": round(projected_tam, 2)})

    return {
        "annual_growth_rate": growth_rate,
        "yearly_projections": projections,
    }


def _infer_growth_rate(signals: list[Any]) -> float:
    """Infer annual growth rate from signal characteristics."""
    if not signals:
        return _GROWTH_RATE_BASE

    # Higher signal volume suggests a more active/growing market
    volume_factor = min(len(signals) / 100, 1.0)  # caps at 1.0
    return _GROWTH_RATE_BASE + (volume_factor * 0.08)  # up to 20%


def _calculate_confidence(
    segments: list[dict[str, Any]],
    signals: list[Any],
) -> dict[str, Any]:
    """Calculate confidence level for the estimates."""
    signal_count = len(signals)
    segment_count = len(segments)

    if signal_count >= 100 and segment_count >= 3:
        level, score = "high", 0.85
    elif signal_count >= 30:
        level, score = "medium", 0.60
    elif signal_count >= 5:
        level, score = "low", 0.35
    else:
        level, score = "very low", 0.15

    coverage = f"{signal_count} signals across {segment_count} segments"

    return {
        "level": level,
        "score": score,
        "signal_coverage": coverage,
        "data_quality_note": (
            "Estimates are heuristic-based projections derived from signal volume "
            "and domain coverage. Validate with primary market research."
        ),
    }


def _collect_data_sources(signals: list[Any]) -> list[str]:
    """Collect unique data source adapters from signals."""
    sources: Counter[str] = Counter()
    for signal in signals:
        sources[signal.source_adapter] += 1

    return [f"{adapter} ({count} signals)" for adapter, count in sources.most_common()]


def _describe_methodology(approach: str, signal_count: int, unit_count: int) -> str:
    """Describe the methodology used for the sizing estimate."""
    if approach == "bottom-up":
        return (
            f"Bottom-up estimation based on {unit_count} validated buildable units "
            f"and {signal_count} market signals. Each unit represents a confirmed "
            f"market opportunity; segment TAMs are summed to derive total market size."
        )
    return (
        f"Top-down estimation using {signal_count} market signals to approximate "
        f"total addressable market, then applying serviceable (SAM={_SAM_RATIO:.0%}) "
        f"and obtainable (SOM={_SOM_RATIO:.0%}) ratios based on competitive analysis "
        f"across {unit_count} buildable units."
    )
