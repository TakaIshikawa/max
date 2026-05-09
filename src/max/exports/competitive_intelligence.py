"""Competitive intelligence report for market landscape analysis.

Aggregates signals by market segment to generate competitive landscape analysis,
including feature matrices, gap analysis, and positioning recommendations.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.competitive_intelligence.v1"
KIND = "max.competitive_intelligence"


def build_competitive_intelligence_report(
    store: Store,
    domain: str | None = None,
) -> dict[str, Any]:
    """Build competitive intelligence report aggregating signals by market segment.

    Args:
        store: Database store containing buildable units and signals
        domain: Optional domain filter for market segmentation

    Returns:
        Competitive intelligence report with market overview, feature matrices,
        gap analysis, and positioning recommendations
    """
    # Get all buildable units, optionally filtered by domain
    units = store.get_buildable_units(limit=1000, domain=domain)

    # Get signals for context
    signals = store.get_signals(limit=1000)

    # Segment market by categories
    market_segments = _segment_by_market(units)

    # Build competitor feature matrix
    feature_matrix = _build_feature_matrix(market_segments, signals, store)

    # Identify gaps and whitespace opportunities
    gap_analysis = _identify_gaps(market_segments, feature_matrix)

    # Calculate competitive density scores
    density_scores = _calculate_competitive_density(market_segments)

    # Generate differentiation opportunities
    differentiation_opportunities = _identify_differentiation_opportunities(
        gap_analysis, feature_matrix
    )

    # Generate positioning recommendations
    positioning_recommendations = _generate_positioning_recommendations(
        market_segments, gap_analysis, differentiation_opportunities
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {
            "project": "max",
            "entity_type": "competitive_intelligence",
            "domain_filter": domain,
        },
        "market_overview": {
            "total_segments": len(market_segments),
            "total_opportunities": sum(len(units) for units in market_segments.values()),
            "segments": list(market_segments.keys()),
            "density_scores": density_scores,
        },
        "competitor_feature_matrix": feature_matrix,
        "gap_analysis": gap_analysis,
        "differentiation_opportunities": differentiation_opportunities,
        "positioning_recommendations": positioning_recommendations,
        "competitive_density": density_scores,
    }


def render_competitive_intelligence_markdown(report: dict[str, Any]) -> str:
    """Render competitive intelligence report as Markdown.

    Args:
        report: Competitive intelligence report from build_competitive_intelligence_report

    Returns:
        Markdown formatted report with sections for market overview, competitor
        feature matrix, gap analysis, differentiation opportunities, and positioning
    """
    lines = [
        "# Competitive Intelligence Report",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Kind: `{report['kind']}`",
        "",
    ]

    # Market Overview
    overview = report["market_overview"]
    lines.extend([
        "## Market Overview",
        "",
        f"- Total market segments: {overview['total_segments']}",
        f"- Total opportunities analyzed: {overview['total_opportunities']}",
        f"- Market segments: {', '.join(overview['segments'])}",
        "",
    ])

    # Competitive Density Scores
    lines.extend([
        "### Competitive Density by Segment",
        "",
    ])

    for segment, metrics in overview["density_scores"].items():
        lines.append(
            f"- **{segment}**: {metrics['opportunity_count']} opportunities, "
            f"density score {metrics['density_score']:.2f}, "
            f"saturation level: {metrics['saturation_level']}"
        )

    lines.append("")

    # Competitor Feature Matrix
    lines.extend([
        "## Competitor Feature Matrix",
        "",
    ])

    feature_matrix = report["competitor_feature_matrix"]
    if feature_matrix:
        # Create markdown table header
        lines.extend([
            "| Market Segment | Competitors | Key Features | Feature Count | Source Data |",
            "|---------------|-------------|--------------|---------------|-------------|",
        ])

        for entry in feature_matrix:
            segment = entry["segment"]
            competitors = ", ".join(entry["competitors"][:3])
            if len(entry["competitors"]) > 3:
                competitors += f" (+{len(entry['competitors']) - 3} more)"

            features = ", ".join(entry["common_features"][:3])
            if len(entry["common_features"]) > 3:
                features += "..."

            feature_count = entry["feature_count"]
            sources = ", ".join(entry["data_sources"][:2])

            lines.append(f"| {segment} | {competitors} | {features} | {feature_count} | {sources} |")

        lines.append("")
    else:
        lines.extend(["- No competitor feature data available", ""])

    # Gap Analysis
    lines.extend([
        "## Gap Analysis",
        "",
    ])

    gap_analysis = report["gap_analysis"]
    if gap_analysis:
        for gap in gap_analysis:
            lines.extend([
                f"### {gap['segment']}",
                "",
                f"- **Whitespace opportunity**: {gap['whitespace_description']}",
                f"- **Gap size**: {gap['gap_size']}",
                f"- **Potential**: {gap['opportunity_potential']}",
                f"- **Unmet needs**: {', '.join(gap['unmet_needs'][:5])}",
                "",
            ])
    else:
        lines.extend(["- No gaps identified", ""])

    # Differentiation Opportunities
    lines.extend([
        "## Differentiation Opportunities",
        "",
    ])

    diff_opportunities = report["differentiation_opportunities"]
    if diff_opportunities:
        for i, opp in enumerate(diff_opportunities, 1):
            lines.extend([
                f"### {i}. {opp['opportunity']}",
                "",
                f"- **Market segment**: {opp['segment']}",
                f"- **Strategy**: {opp['strategy']}",
                f"- **Impact potential**: {opp['impact_potential']}",
                f"- **Evidence strength**: {opp['evidence_strength']}",
                "",
            ])
    else:
        lines.extend(["- No differentiation opportunities identified", ""])

    # Recommended Positioning
    lines.extend([
        "## Recommended Positioning",
        "",
    ])

    positioning = report["positioning_recommendations"]
    if positioning:
        for rec in positioning:
            lines.extend([
                f"### {rec['segment']}",
                "",
                f"**Positioning statement**: {rec['positioning_statement']}",
                "",
                f"**Key differentiators**:",
            ])
            for diff in rec["key_differentiators"]:
                lines.append(f"- {diff}")

            lines.extend([
                "",
                f"**Target audience**: {rec['target_audience']}",
                f"**Competitive advantage**: {rec['competitive_advantage']}",
                "",
            ])
    else:
        lines.extend(["- No positioning recommendations available", ""])

    return "\n".join(lines).rstrip() + "\n"


def _segment_by_market(units: list[Any]) -> dict[str, list[Any]]:
    """Segment buildable units by market category.

    Groups units by their category field to create market segments.
    """
    segments: dict[str, list[Any]] = defaultdict(list)

    for unit in units:
        category = getattr(unit, "category", "uncategorized")
        if category:
            segments[str(category)].append(unit)
        else:
            segments["uncategorized"].append(unit)

    return dict(segments)


def _build_feature_matrix(
    market_segments: dict[str, list[Any]],
    signals: list[Any],
    store: Store,
) -> list[dict[str, Any]]:
    """Build competitor feature matrix from market segments and signals.

    Analyzes signals and prior art to extract competitor features and
    capabilities for each market segment.
    """
    matrix: list[dict[str, Any]] = []

    for segment, units in market_segments.items():
        competitors: set[str] = set()
        features: set[str] = set()
        data_sources: set[str] = set()

        # Extract competitor info from prior art
        for unit in units:
            prior_art = store.get_prior_art_matches(unit.id)
            for match in prior_art:
                competitors.add(match.get("title", "Unknown"))
                data_sources.add(match.get("source", "unknown"))

                # Extract features from description/metadata
                description = match.get("description", "")
                if description:
                    # Simple feature extraction from keywords
                    feature_keywords = _extract_features(description)
                    features.update(feature_keywords)

        # Extract features from unit solutions
        for unit in units:
            solution = getattr(unit, "solution", "")
            if solution:
                feature_keywords = _extract_features(solution)
                features.update(feature_keywords)

        matrix.append({
            "segment": segment,
            "competitors": sorted(list(competitors)),
            "common_features": sorted(list(features)),
            "feature_count": len(features),
            "data_sources": sorted(list(data_sources)),
            "unit_count": len(units),
        })

    return matrix


def _extract_features(text: str) -> set[str]:
    """Extract feature keywords from text description.

    Simple keyword-based feature extraction looking for common
    capability indicators.
    """
    features: set[str] = set()

    # Common feature indicators
    indicators = [
        "api", "automation", "analytics", "dashboard", "integration",
        "monitoring", "reporting", "notification", "search", "export",
        "import", "collaboration", "security", "authentication", "authorization",
        "workflow", "pipeline", "deployment", "testing", "ci/cd",
        "machine learning", "ai", "data", "visualization", "mobile",
        "real-time", "sync", "backup", "recovery", "scalability"
    ]

    text_lower = text.lower()
    for indicator in indicators:
        if indicator in text_lower:
            features.add(indicator)

    return features


def _identify_gaps(
    market_segments: dict[str, list[Any]],
    feature_matrix: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Identify gaps and whitespace opportunities in the market.

    Analyzes market segments and feature coverage to find underserved
    areas and opportunities.
    """
    gaps: list[dict[str, Any]] = []

    # Calculate average features per segment
    if not feature_matrix:
        return gaps

    avg_features = sum(entry["feature_count"] for entry in feature_matrix) / len(feature_matrix)

    for entry in feature_matrix:
        segment = entry["segment"]
        feature_count = entry["feature_count"]
        competitor_count = len(entry["competitors"])

        # Identify whitespace based on feature coverage and competition
        gap_size = "large" if feature_count < avg_features * 0.5 else "medium" if feature_count < avg_features * 0.8 else "small"

        opportunity_potential = _assess_opportunity_potential(
            competitor_count, feature_count, avg_features
        )

        # Identify unmet needs (features missing compared to average)
        unmet_needs = _identify_unmet_needs(entry, feature_matrix)

        whitespace = _describe_whitespace(segment, gap_size, competitor_count)

        gaps.append({
            "segment": segment,
            "whitespace_description": whitespace,
            "gap_size": gap_size,
            "opportunity_potential": opportunity_potential,
            "unmet_needs": unmet_needs,
            "competitor_count": competitor_count,
            "feature_coverage": feature_count,
        })

    # Sort by opportunity potential
    gaps.sort(key=lambda x: (
        {"high": 3, "medium": 2, "low": 1}.get(x["opportunity_potential"], 0)
    ), reverse=True)

    return gaps


def _assess_opportunity_potential(
    competitor_count: int,
    feature_count: int,
    avg_features: float,
) -> str:
    """Assess opportunity potential based on competition and feature coverage."""
    if competitor_count < 3 and feature_count < avg_features * 0.7:
        return "high"
    elif competitor_count < 5 or feature_count < avg_features * 0.8:
        return "medium"
    else:
        return "low"


def _identify_unmet_needs(
    segment_entry: dict[str, Any],
    feature_matrix: list[dict[str, Any]],
) -> list[str]:
    """Identify unmet needs by comparing features across segments."""
    current_features = set(segment_entry["common_features"])

    # Collect all features from other segments
    all_features: set[str] = set()
    for entry in feature_matrix:
        all_features.update(entry["common_features"])

    # Find features present in other segments but not this one
    unmet = sorted(list(all_features - current_features))

    return unmet[:10]  # Return top 10


def _describe_whitespace(segment: str, gap_size: str, competitor_count: int) -> str:
    """Generate whitespace opportunity description."""
    if gap_size == "large" and competitor_count < 3:
        return f"Significant whitespace in {segment} with minimal competition and low feature coverage"
    elif gap_size == "large":
        return f"Underserved market in {segment} with low feature coverage despite some competition"
    elif gap_size == "medium" and competitor_count < 3:
        return f"Emerging opportunity in {segment} with moderate feature coverage and low competition"
    else:
        return f"Incremental opportunity in {segment} to add missing features"


def _calculate_competitive_density(
    market_segments: dict[str, list[Any]],
) -> dict[str, dict[str, Any]]:
    """Calculate competitive density scores per market segment.

    Density score represents the level of competition and saturation
    in each market segment.
    """
    density_scores: dict[str, dict[str, Any]] = {}

    # Calculate total opportunities across all segments
    total_opportunities = sum(len(units) for units in market_segments.values())

    if total_opportunities == 0:
        return density_scores

    for segment, units in market_segments.items():
        opportunity_count = len(units)

        # Calculate density score (0-1 scale)
        # Higher score = more saturated market
        density_score = min(1.0, opportunity_count / max(total_opportunities * 0.2, 1))

        # Determine saturation level
        if density_score >= 0.7:
            saturation = "high"
        elif density_score >= 0.4:
            saturation = "medium"
        else:
            saturation = "low"

        density_scores[segment] = {
            "opportunity_count": opportunity_count,
            "density_score": density_score,
            "saturation_level": saturation,
            "market_share_percentage": round((opportunity_count / total_opportunities) * 100, 1),
        }

    return density_scores


def _identify_differentiation_opportunities(
    gap_analysis: list[dict[str, Any]],
    feature_matrix: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Identify differentiation opportunities based on gaps and features.

    Generates strategic differentiation opportunities by analyzing
    market gaps and underserved segments.
    """
    opportunities: list[dict[str, Any]] = []

    for gap in gap_analysis:
        if gap["opportunity_potential"] in ["high", "medium"]:
            # Create differentiation opportunity
            opportunity = {
                "opportunity": f"Differentiate in {gap['segment']} market",
                "segment": gap["segment"],
                "strategy": _generate_differentiation_strategy(gap),
                "impact_potential": gap["opportunity_potential"],
                "evidence_strength": "medium" if gap["competitor_count"] < 5 else "low",
            }
            opportunities.append(opportunity)

    return opportunities


def _generate_differentiation_strategy(gap: dict[str, Any]) -> str:
    """Generate differentiation strategy based on gap analysis."""
    if gap["gap_size"] == "large":
        return (
            f"Pioneer {gap['segment']} segment by addressing unmet needs: "
            f"{', '.join(gap['unmet_needs'][:3])}"
        )
    elif gap["competitor_count"] < 3:
        return (
            f"Establish early leadership in {gap['segment']} with comprehensive feature set"
        )
    else:
        return (
            f"Differentiate through specialized features: {', '.join(gap['unmet_needs'][:3])}"
        )


def _generate_positioning_recommendations(
    market_segments: dict[str, list[Any]],
    gap_analysis: list[dict[str, Any]],
    differentiation_opportunities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate positioning recommendations for each market segment.

    Creates positioning statements and recommendations based on
    competitive landscape analysis.
    """
    recommendations: list[dict[str, Any]] = []

    # Create gap lookup by segment
    gaps_by_segment = {gap["segment"]: gap for gap in gap_analysis}

    for segment, units in market_segments.items():
        gap = gaps_by_segment.get(segment)
        if not gap:
            continue

        # Find relevant differentiation opportunity
        diff_opp = next(
            (opp for opp in differentiation_opportunities if opp["segment"] == segment),
            None
        )

        # Generate positioning statement
        positioning_statement = _create_positioning_statement(segment, gap, diff_opp)

        # Identify key differentiators
        key_differentiators = _extract_key_differentiators(gap, diff_opp)

        # Identify target audience
        target_audience = _identify_target_audience(units)

        # Generate competitive advantage
        competitive_advantage = _describe_competitive_advantage(gap)

        recommendations.append({
            "segment": segment,
            "positioning_statement": positioning_statement,
            "key_differentiators": key_differentiators,
            "target_audience": target_audience,
            "competitive_advantage": competitive_advantage,
        })

    return recommendations


def _create_positioning_statement(
    segment: str,
    gap: dict[str, Any],
    diff_opp: dict[str, Any] | None,
) -> str:
    """Create positioning statement for a market segment."""
    if diff_opp and gap["opportunity_potential"] == "high":
        return (
            f"Position as the leading solution for {segment}, "
            f"addressing underserved needs with {gap['gap_size']} market whitespace"
        )
    elif gap["competitor_count"] < 3:
        return (
            f"Establish early market presence in {segment} "
            f"with comprehensive feature coverage"
        )
    else:
        return (
            f"Differentiate in {segment} by addressing specific gaps "
            f"in existing solutions"
        )


def _extract_key_differentiators(
    gap: dict[str, Any],
    diff_opp: dict[str, Any] | None,
) -> list[str]:
    """Extract key differentiators from gap analysis."""
    differentiators: list[str] = []

    if gap["gap_size"] in ["large", "medium"]:
        differentiators.append(f"First-mover advantage in underserved {gap['segment']} market")

    if gap["competitor_count"] < 3:
        differentiators.append("Minimal competitive pressure allows feature innovation")

    if gap["unmet_needs"]:
        differentiators.append(
            f"Addresses unmet needs: {', '.join(gap['unmet_needs'][:3])}"
        )

    if diff_opp:
        differentiators.append(diff_opp["strategy"])

    return differentiators[:5]


def _identify_target_audience(units: list[Any]) -> str:
    """Identify target audience from buildable units."""
    # Extract target users from units
    target_users: set[str] = set()

    for unit in units[:10]:  # Sample first 10
        specific_user = getattr(unit, "specific_user", None)
        if specific_user:
            target_users.add(str(specific_user))

    if target_users:
        return ", ".join(sorted(list(target_users))[:3])

    return "developers and product teams"


def _describe_competitive_advantage(gap: dict[str, Any]) -> str:
    """Describe competitive advantage based on gap analysis."""
    if gap["opportunity_potential"] == "high":
        return (
            f"Strong competitive advantage with {gap['gap_size']} whitespace "
            f"and only {gap['competitor_count']} competitors"
        )
    elif gap["opportunity_potential"] == "medium":
        return (
            f"Moderate competitive advantage with opportunity to differentiate "
            f"through specialized features"
        )
    else:
        return "Incremental advantage through feature completeness and execution"
