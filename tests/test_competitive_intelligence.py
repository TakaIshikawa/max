"""Tests for competitive intelligence export module."""

from __future__ import annotations

from datetime import datetime, timezone

from max.exports.competitive_intelligence import (
    SCHEMA_VERSION,
    KIND,
    build_competitive_intelligence_report,
    render_competitive_intelligence_markdown,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.signal import Signal, SignalSourceType


def test_build_competitive_intelligence_report_with_multiple_segments(tmp_path) -> None:
    """Test building competitive intelligence report with multiple market segments."""
    store = Store(str(tmp_path / "max.db"))
    try:
        # Seed data with multiple categories
        _seed_buildable_units_with_categories(store)
        _seed_signals(store)

        report = build_competitive_intelligence_report(store)

        assert report is not None
        assert report["schema_version"] == SCHEMA_VERSION
        assert report["kind"] == KIND
        assert report["source"]["project"] == "max"
        assert report["source"]["entity_type"] == "competitive_intelligence"

        # Market overview assertions
        overview = report["market_overview"]
        assert overview["total_segments"] > 0
        assert overview["total_opportunities"] > 0
        assert len(overview["segments"]) > 0
        assert "density_scores" in overview

        # Feature matrix assertions
        assert "competitor_feature_matrix" in report
        assert isinstance(report["competitor_feature_matrix"], list)

        # Gap analysis assertions
        assert "gap_analysis" in report
        assert isinstance(report["gap_analysis"], list)

        # Differentiation opportunities assertions
        assert "differentiation_opportunities" in report
        assert isinstance(report["differentiation_opportunities"], list)

        # Positioning recommendations assertions
        assert "positioning_recommendations" in report
        assert isinstance(report["positioning_recommendations"], list)

        # Competitive density assertions
        assert "competitive_density" in report
        assert isinstance(report["competitive_density"], dict)

    finally:
        store.close()


def test_build_competitive_intelligence_report_with_domain_filter(tmp_path) -> None:
    """Test building competitive intelligence report with domain filter."""
    store = Store(str(tmp_path / "max.db"))
    try:
        _seed_buildable_units_with_domains(store)

        report = build_competitive_intelligence_report(store, domain="developer-tools")

        assert report is not None
        assert report["source"]["domain_filter"] == "developer-tools"

        # Should only include units from the filtered domain
        overview = report["market_overview"]
        assert overview["total_opportunities"] > 0

    finally:
        store.close()


def test_competitive_density_calculation(tmp_path) -> None:
    """Test competitive density score calculation."""
    store = Store(str(tmp_path / "max.db"))
    try:
        _seed_buildable_units_with_categories(store)

        report = build_competitive_intelligence_report(store)

        density = report["competitive_density"]
        assert len(density) > 0

        for segment, metrics in density.items():
            assert "opportunity_count" in metrics
            assert "density_score" in metrics
            assert "saturation_level" in metrics
            assert "market_share_percentage" in metrics

            # Validate density score range
            assert 0.0 <= metrics["density_score"] <= 1.0

            # Validate saturation level
            assert metrics["saturation_level"] in ["low", "medium", "high"]

            # Validate market share percentage
            assert 0.0 <= metrics["market_share_percentage"] <= 100.0

    finally:
        store.close()


def test_feature_matrix_generation(tmp_path) -> None:
    """Test competitor feature matrix generation."""
    store = Store(str(tmp_path / "max.db"))
    try:
        _seed_buildable_units_with_prior_art(store)

        report = build_competitive_intelligence_report(store)

        matrix = report["competitor_feature_matrix"]
        assert len(matrix) > 0

        for entry in matrix:
            assert "segment" in entry
            assert "competitors" in entry
            assert "common_features" in entry
            assert "feature_count" in entry
            assert "data_sources" in entry
            assert "unit_count" in entry

            assert isinstance(entry["competitors"], list)
            assert isinstance(entry["common_features"], list)
            assert isinstance(entry["data_sources"], list)
            assert entry["feature_count"] >= 0
            assert entry["unit_count"] > 0

    finally:
        store.close()


def test_gap_analysis_identification(tmp_path) -> None:
    """Test gap analysis and whitespace opportunity identification."""
    store = Store(str(tmp_path / "max.db"))
    try:
        _seed_buildable_units_with_categories(store)

        report = build_competitive_intelligence_report(store)

        gaps = report["gap_analysis"]
        assert isinstance(gaps, list)

        if gaps:
            for gap in gaps:
                assert "segment" in gap
                assert "whitespace_description" in gap
                assert "gap_size" in gap
                assert "opportunity_potential" in gap
                assert "unmet_needs" in gap
                assert "competitor_count" in gap
                assert "feature_coverage" in gap

                # Validate gap_size
                assert gap["gap_size"] in ["small", "medium", "large"]

                # Validate opportunity_potential
                assert gap["opportunity_potential"] in ["low", "medium", "high"]

                # Validate unmet_needs is a list
                assert isinstance(gap["unmet_needs"], list)

    finally:
        store.close()


def test_differentiation_opportunities(tmp_path) -> None:
    """Test differentiation opportunity identification."""
    store = Store(str(tmp_path / "max.db"))
    try:
        _seed_buildable_units_with_categories(store)

        report = build_competitive_intelligence_report(store)

        opportunities = report["differentiation_opportunities"]
        assert isinstance(opportunities, list)

        for opp in opportunities:
            assert "opportunity" in opp
            assert "segment" in opp
            assert "strategy" in opp
            assert "impact_potential" in opp
            assert "evidence_strength" in opp

            # Validate impact_potential
            assert opp["impact_potential"] in ["low", "medium", "high"]

            # Validate evidence_strength
            assert opp["evidence_strength"] in ["low", "medium", "high"]

    finally:
        store.close()


def test_positioning_recommendations(tmp_path) -> None:
    """Test positioning recommendations generation."""
    store = Store(str(tmp_path / "max.db"))
    try:
        _seed_buildable_units_with_categories(store)

        report = build_competitive_intelligence_report(store)

        positioning = report["positioning_recommendations"]
        assert isinstance(positioning, list)

        for rec in positioning:
            assert "segment" in rec
            assert "positioning_statement" in rec
            assert "key_differentiators" in rec
            assert "target_audience" in rec
            assert "competitive_advantage" in rec

            # Validate types
            assert isinstance(rec["positioning_statement"], str)
            assert isinstance(rec["key_differentiators"], list)
            assert isinstance(rec["target_audience"], str)
            assert isinstance(rec["competitive_advantage"], str)

            # Validate content
            assert len(rec["positioning_statement"]) > 0
            assert len(rec["target_audience"]) > 0

    finally:
        store.close()


def test_render_competitive_intelligence_markdown(tmp_path) -> None:
    """Test rendering competitive intelligence report as markdown."""
    store = Store(str(tmp_path / "max.db"))
    try:
        _seed_buildable_units_with_categories(store)

        report = build_competitive_intelligence_report(store)
        markdown = render_competitive_intelligence_markdown(report)

        assert markdown is not None
        assert isinstance(markdown, str)
        assert len(markdown) > 0

        # Check for required sections
        assert "# Competitive Intelligence Report" in markdown
        assert "## Market Overview" in markdown
        assert "### Competitive Density by Segment" in markdown
        assert "## Competitor Feature Matrix" in markdown
        assert "## Gap Analysis" in markdown
        assert "## Differentiation Opportunities" in markdown
        assert "## Recommended Positioning" in markdown

        # Check schema metadata
        assert SCHEMA_VERSION in markdown
        assert KIND in markdown

        # Verify markdown ends with newline
        assert markdown.endswith("\n")

    finally:
        store.close()


def test_empty_store_returns_valid_report(tmp_path) -> None:
    """Test that an empty store returns a valid but empty report."""
    store = Store(str(tmp_path / "max.db"))
    try:
        report = build_competitive_intelligence_report(store)

        assert report is not None
        assert report["schema_version"] == SCHEMA_VERSION
        assert report["kind"] == KIND

        # Should have empty collections
        assert report["market_overview"]["total_segments"] == 0
        assert report["market_overview"]["total_opportunities"] == 0
        assert len(report["competitor_feature_matrix"]) == 0
        assert len(report["gap_analysis"]) == 0
        assert len(report["differentiation_opportunities"]) == 0
        assert len(report["positioning_recommendations"]) == 0
        assert len(report["competitive_density"]) == 0

    finally:
        store.close()


def test_markdown_rendering_with_empty_report(tmp_path) -> None:
    """Test rendering markdown with empty report data."""
    store = Store(str(tmp_path / "max.db"))
    try:
        report = build_competitive_intelligence_report(store)
        markdown = render_competitive_intelligence_markdown(report)

        assert markdown is not None
        assert "# Competitive Intelligence Report" in markdown
        assert "- No competitor feature data available" in markdown
        assert "- No gaps identified" in markdown
        assert "- No differentiation opportunities identified" in markdown
        assert "- No positioning recommendations available" in markdown

    finally:
        store.close()


def test_competitive_intelligence_with_prior_art(tmp_path) -> None:
    """Test competitive intelligence with prior art data for competitor tracking."""
    store = Store(str(tmp_path / "max.db"))
    try:
        _seed_buildable_units_with_prior_art(store)

        report = build_competitive_intelligence_report(store)

        # Should extract competitor information from prior art
        matrix = report["competitor_feature_matrix"]
        assert len(matrix) > 0

        # Check that competitors are extracted
        has_competitors = any(len(entry["competitors"]) > 0 for entry in matrix)
        assert has_competitors

        # Check that data sources are tracked
        has_sources = any(len(entry["data_sources"]) > 0 for entry in matrix)
        assert has_sources

    finally:
        store.close()


def test_feature_extraction_from_solutions(tmp_path) -> None:
    """Test that features are extracted from unit solutions."""
    store = Store(str(tmp_path / "max.db"))
    try:
        # Create unit with feature-rich solution
        unit = BuildableUnit(
            id="unit-test001",
            title="API Monitoring Platform",
            one_liner="Monitor API performance",
            category="monitoring",
            problem="Need to track API health",
            solution="Real-time monitoring with analytics dashboard, automated alerts, API integration, and export capabilities",
            value_proposition="Comprehensive API health monitoring and analytics",
            domain="developer-tools",
        )
        store.insert_buildable_unit(unit)

        report = build_competitive_intelligence_report(store, domain="developer-tools")

        matrix = report["competitor_feature_matrix"]
        assert len(matrix) > 0

        # Should extract features from solution text
        monitoring_segment = next(
            (entry for entry in matrix if entry["segment"] == "monitoring"),
            None
        )
        assert monitoring_segment is not None
        assert monitoring_segment["feature_count"] > 0

        # Check for specific features mentioned in solution
        features = set(monitoring_segment["common_features"])
        expected_features = {"analytics", "dashboard", "api", "export"}
        assert len(expected_features.intersection(features)) > 0

    finally:
        store.close()


# Helper functions for seeding test data

def _seed_buildable_units_with_categories(store: Store) -> None:
    """Seed buildable units with different categories."""
    units = [
        BuildableUnit(
            id=f"unit-cat{i:03d}",
            title=f"Test Unit {i}",
            one_liner=f"Test one-liner {i}",
            category=category,
            problem=f"Test problem {i}",
            solution=f"Test solution {i} with automation and API features",
            value_proposition=f"Improve workflow efficiency for {category}",
            domain="test-domain",
            specific_user="developer" if i % 2 == 0 else "product manager",
        )
        for i, category in enumerate([
            "automation",
            "automation",
            "automation",
            "analytics",
            "analytics",
            "monitoring",
            "testing",
        ], 1)
    ]

    for unit in units:
        store.insert_buildable_unit(unit)


def _seed_buildable_units_with_domains(store: Store) -> None:
    """Seed buildable units with different domains."""
    units = [
        BuildableUnit(
            id=f"unit-dom{i:03d}",
            title=f"Test Unit {i}",
            one_liner=f"Test one-liner {i}",
            category="automation",
            problem=f"Test problem {i}",
            solution=f"Test solution {i}",
            value_proposition="Streamline automation workflows",
            domain=domain,
        )
        for i, domain in enumerate([
            "developer-tools",
            "developer-tools",
            "analytics",
            "marketing",
        ], 1)
    ]

    for unit in units:
        store.insert_buildable_unit(unit)


def _seed_buildable_units_with_prior_art(store: Store) -> None:
    """Seed buildable units with prior art for competitor tracking."""
    units = [
        BuildableUnit(
            id=f"unit-pa{i:03d}",
            title=f"Test Unit {i}",
            one_liner=f"Test one-liner {i}",
            category="automation",
            problem=f"Test problem {i}",
            solution="Automation solution with workflow, API, and integration features",
            value_proposition="Automate complex workflows with ease",
            domain="test-domain",
        )
        for i in range(1, 4)
    ]

    for unit in units:
        store.insert_buildable_unit(unit)

    # Add prior art matches
    for i, unit in enumerate(units, 1):
        store.insert_prior_art_match(
            unit_id=unit.id,
            match={
                "source": "product_hunt" if i % 2 == 0 else "crunchbase",
                "title": f"Competitor Product {i}",
                "url": f"https://example.com/competitor{i}",
                "description": "Automation platform with dashboard, analytics, and real-time monitoring capabilities",
                "relevance_score": 0.85,
                "match_signals": {},
                "search_query": "automation",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )


def _seed_signals(store: Store) -> None:
    """Seed signals for context."""
    signals = [
        Signal(
            source_type=SignalSourceType.TRENDING,
            source_adapter="github_trending",
            title=f"Test Signal {i}",
            content=f"Test content {i}",
            url=f"https://github.com/test{i}",
            tags=["automation", "testing"],
        )
        for i in range(1, 4)
    ]

    for signal in signals:
        store.insert_signal(signal)
