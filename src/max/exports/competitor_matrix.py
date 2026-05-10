"""Competitor feature matrix export — side-by-side comparison tables.

Compiles feature availability, pricing tiers, and platform support across
competitors into comparison grids. Exports to markdown tables and structured
JSON for product planning dashboards.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.competitor_matrix.v1"
KIND = "max.competitor_matrix"

# Feature indicator constants
_HAS = "Yes"
_NO = "—"
_PARTIAL = "Partial"

# Common feature categories
_FEATURE_CATEGORIES = [
    "core", "integration", "analytics", "security",
    "collaboration", "automation", "api",
]


def build_competitor_matrix(
    store: Store,
    domain: str | None = None,
) -> dict[str, Any]:
    """Build competitor feature comparison matrix.

    Args:
        store: Database store with signals and buildable units.
        domain: Optional domain filter.

    Returns:
        Dict with competitor grid, gap analysis, and category breakdowns.
    """
    units = store.get_buildable_units(limit=1000, domain=domain)
    signals = store.get_signals(limit=1000)

    competitors = _collect_competitors(units, store)
    features = _collect_features(units, signals)
    matrix = _build_matrix(competitors, features)
    categories = _categorize_features(features)
    gaps = _analyze_gaps(matrix, competitors)
    strengths = _identify_strengths(matrix, competitors)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "competitor_matrix",
            "domain_filter": domain,
        },
        "competitors": competitors,
        "features": features,
        "matrix": matrix,
        "feature_categories": categories,
        "gap_analysis": gaps,
        "unique_strengths": strengths,
    }


def render_competitor_matrix_markdown(report: dict[str, Any]) -> str:
    """Render competitor matrix as Markdown tables."""
    lines = [
        "# Competitor Feature Matrix",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
    ]

    competitors = report["competitors"]
    matrix = report["matrix"]

    # Main comparison table
    lines.extend(["## Feature Comparison", ""])
    if competitors and matrix:
        comp_names = [c["name"] for c in competitors]
        header = "| Feature | " + " | ".join(comp_names) + " |"
        sep = "|---------|" + "|".join(["---"] * len(comp_names)) + "|"
        lines.extend([header, sep])

        for row in matrix:
            cells = " | ".join(row["availability"])
            lines.append(f"| {row['feature']} | {cells} |")
        lines.append("")
    else:
        lines.extend(["- No competitor data available", ""])

    # Feature categories
    lines.extend(["## Feature Categories", ""])
    for cat in report["feature_categories"]:
        lines.extend([
            f"### {cat['category'].title()}",
            "",
        ])
        if cat["features"]:
            for f in cat["features"]:
                lines.append(f"- {f}")
        else:
            lines.append("- No features in this category")
        lines.append("")

    # Gap analysis
    lines.extend(["## Competitive Gaps", ""])
    if report["gap_analysis"]:
        for gap in report["gap_analysis"]:
            lines.append(f"- **{gap['feature']}**: {gap['description']}")
        lines.append("")
    else:
        lines.extend(["- No competitive gaps identified", ""])

    # Unique strengths
    lines.extend(["## Unique Strengths", ""])
    if report["unique_strengths"]:
        for s in report["unique_strengths"]:
            lines.append(f"- **{s['competitor']}**: {s['strength']}")
        lines.append("")
    else:
        lines.extend(["- No unique strengths identified", ""])

    return "\n".join(lines).rstrip() + "\n"


def render_competitor_matrix_json(report: dict[str, Any]) -> str:
    """Render competitor matrix report as formatted JSON."""
    return json.dumps(report, indent=2, default=str)


# ── Internal helpers ─────────────────────────────────────────────────


def _collect_competitors(
    units: list[Any],
    store: Store,
) -> list[dict[str, Any]]:
    """Collect competitor information from prior art matches."""
    competitors: dict[str, dict[str, Any]] = {}

    for unit in units:
        prior_art = store.get_prior_art_matches(unit.id)
        for match in prior_art:
            name = match.get("title", "Unknown")
            if name not in competitors:
                competitors[name] = {
                    "name": name,
                    "source": match.get("source", "unknown"),
                    "description": match.get("description", ""),
                    "mentions": 0,
                    "features": set(),
                }
            competitors[name]["mentions"] += 1

            # Extract features from description
            desc = match.get("description", "")
            if desc:
                for kw in _extract_feature_keywords(desc):
                    competitors[name]["features"].add(kw)

    # Convert sets to lists and sort by mentions
    result = []
    for comp in sorted(competitors.values(), key=lambda c: c["mentions"], reverse=True)[:10]:
        comp["features"] = sorted(comp["features"])
        result.append(comp)

    return result


def _extract_feature_keywords(text: str) -> list[str]:
    """Extract feature keywords from text."""
    indicators = [
        "api", "automation", "analytics", "dashboard", "integration",
        "monitoring", "reporting", "notification", "search", "export",
        "import", "collaboration", "security", "authentication",
        "workflow", "pipeline", "deployment", "testing",
        "machine learning", "ai", "visualization", "mobile",
        "real-time", "sync", "backup", "scalability",
    ]
    text_lower = text.lower()
    return [ind for ind in indicators if ind in text_lower]


def _collect_features(units: list[Any], signals: list[Any]) -> list[str]:
    """Collect feature list from units and signals."""
    features: list[str] = []
    seen: set[str] = set()

    for unit in units:
        solution = getattr(unit, "solution", "")
        if solution and solution not in seen:
            seen.add(solution)
            features.append(solution)

    # Add features inferred from signal tags
    tag_counts: dict[str, int] = defaultdict(int)
    for signal in signals:
        for tag in signal.tags:
            tag_counts[tag] += 1

    for tag, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        if tag not in seen:
            seen.add(tag)
            features.append(tag)

    return features


def _build_matrix(
    competitors: list[dict[str, Any]],
    features: list[str],
) -> list[dict[str, Any]]:
    """Build the feature availability matrix."""
    matrix: list[dict[str, Any]] = []

    for feature in features:
        feature_lower = feature.lower()
        availability: list[str] = []

        for comp in competitors:
            # Check if any of the competitor's features overlap
            comp_features_lower = [f.lower() for f in comp.get("features", [])]
            if any(kw in feature_lower or feature_lower in kw for kw in comp_features_lower):
                availability.append(_HAS)
            elif any(kw in feature_lower for kw in comp.get("features", [])):
                availability.append(_PARTIAL)
            else:
                availability.append(_NO)

        matrix.append({
            "feature": feature,
            "availability": availability,
        })

    return matrix


def _categorize_features(features: list[str]) -> list[dict[str, Any]]:
    """Categorize features into predefined categories."""
    categorized: dict[str, list[str]] = {cat: [] for cat in _FEATURE_CATEGORIES}

    category_keywords = {
        "core": ["core", "basic", "essential", "main"],
        "integration": ["integration", "connect", "plugin", "api", "webhook"],
        "analytics": ["analytics", "report", "metric", "dashboard", "insight"],
        "security": ["security", "auth", "encrypt", "permission", "access"],
        "collaboration": ["collaborat", "team", "share", "comment", "review"],
        "automation": ["automat", "workflow", "pipeline", "schedule", "trigger"],
        "api": ["api", "endpoint", "rest", "graphql", "grpc", "sdk"],
    }

    for feat in features:
        feat_lower = feat.lower()
        matched = False
        for cat, keywords in category_keywords.items():
            if any(kw in feat_lower for kw in keywords):
                categorized[cat].append(feat)
                matched = True
                break
        if not matched:
            categorized["core"].append(feat)

    return [{"category": cat, "features": feats} for cat, feats in categorized.items()]


def _analyze_gaps(
    matrix: list[dict[str, Any]],
    competitors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Identify features where competitors have gaps."""
    gaps: list[dict[str, Any]] = []

    for row in matrix:
        no_count = row["availability"].count(_NO)
        total = len(row["availability"])

        if total > 0 and no_count > total / 2:
            gaps.append({
                "feature": row["feature"],
                "description": (
                    f"{no_count} of {total} competitors lack this feature — "
                    f"potential differentiation opportunity"
                ),
                "gap_ratio": no_count / total if total else 0,
            })

    # Sort by gap ratio descending
    gaps.sort(key=lambda g: g["gap_ratio"], reverse=True)
    return gaps


def _identify_strengths(
    matrix: list[dict[str, Any]],
    competitors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Identify unique strengths per competitor."""
    if not competitors or not matrix:
        return []

    strengths: list[dict[str, Any]] = []

    for i, comp in enumerate(competitors):
        # Count features this competitor has
        has_count = sum(
            1 for row in matrix
            if i < len(row["availability"]) and row["availability"][i] == _HAS
        )
        total_features = len(matrix)

        if total_features > 0 and has_count > 0:
            coverage = has_count / total_features
            strengths.append({
                "competitor": comp["name"],
                "strength": (
                    f"Covers {has_count}/{total_features} features "
                    f"({coverage:.0%} coverage)"
                ),
                "feature_count": has_count,
                "coverage": coverage,
            })

    strengths.sort(key=lambda s: s["coverage"], reverse=True)
    return strengths
