"""Tests for stakeholder mapping export module."""

import pytest

from max.exports.stakeholder_map import (
    build_stakeholder_map,
    render_stakeholder_map_markdown,
    _classify_stakeholders,
    _determine_quadrant,
    _group_by_quadrant,
    _recommend_engagement_strategies,
    QUADRANT_HIGH_POWER_HIGH_INTEREST,
    QUADRANT_HIGH_POWER_LOW_INTEREST,
    QUADRANT_LOW_POWER_HIGH_INTEREST,
    QUADRANT_LOW_POWER_LOW_INTEREST,
)


@pytest.fixture
def stakeholders():
    return [
        {
            "name": "CEO",
            "role": "Executive Sponsor",
            "interest": 5,
            "influence": 5,
            "sentiment": "supportive",
        },
        {
            "name": "CTO",
            "role": "Technical Lead",
            "interest": 5,
            "influence": 4,
            "sentiment": "supportive",
        },
        {
            "name": "CFO",
            "role": "Budget Approver",
            "interest": 2,
            "influence": 5,
            "sentiment": "neutral",
        },
        {
            "name": "Dev Team",
            "role": "Implementers",
            "interest": 5,
            "influence": 2,
            "sentiment": "supportive",
        },
        {
            "name": "Legal",
            "role": "Compliance",
            "interest": 2,
            "influence": 2,
            "sentiment": "resistant",
        },
    ]


class TestDetermineQuadrant:
    def test_high_power_high_interest(self):
        assert _determine_quadrant(5, 5) == QUADRANT_HIGH_POWER_HIGH_INTEREST
        assert _determine_quadrant(4, 4) == QUADRANT_HIGH_POWER_HIGH_INTEREST

    def test_high_power_low_interest(self):
        assert _determine_quadrant(2, 5) == QUADRANT_HIGH_POWER_LOW_INTEREST
        assert _determine_quadrant(3, 4) == QUADRANT_HIGH_POWER_LOW_INTEREST

    def test_low_power_high_interest(self):
        assert _determine_quadrant(5, 2) == QUADRANT_LOW_POWER_HIGH_INTEREST
        assert _determine_quadrant(4, 3) == QUADRANT_LOW_POWER_HIGH_INTEREST

    def test_low_power_low_interest(self):
        assert _determine_quadrant(2, 2) == QUADRANT_LOW_POWER_LOW_INTEREST
        assert _determine_quadrant(3, 3) == QUADRANT_LOW_POWER_LOW_INTEREST


class TestClassifyStakeholders:
    def test_assigns_quadrants(self, stakeholders):
        classified = _classify_stakeholders(stakeholders)
        ceo = next(s for s in classified if s["name"] == "CEO")
        assert ceo["quadrant"] == QUADRANT_HIGH_POWER_HIGH_INTEREST

        cfo = next(s for s in classified if s["name"] == "CFO")
        assert cfo["quadrant"] == QUADRANT_HIGH_POWER_LOW_INTEREST

        dev = next(s for s in classified if s["name"] == "Dev Team")
        assert dev["quadrant"] == QUADRANT_LOW_POWER_HIGH_INTEREST

        legal = next(s for s in classified if s["name"] == "Legal")
        assert legal["quadrant"] == QUADRANT_LOW_POWER_LOW_INTEREST

    def test_empty_list(self):
        assert _classify_stakeholders([]) == []


class TestGroupByQuadrant:
    def test_grouping(self, stakeholders):
        classified = _classify_stakeholders(stakeholders)
        quadrants = _group_by_quadrant(classified)
        assert len(quadrants[QUADRANT_HIGH_POWER_HIGH_INTEREST]) == 2  # CEO, CTO
        assert len(quadrants[QUADRANT_HIGH_POWER_LOW_INTEREST]) == 1  # CFO
        assert len(quadrants[QUADRANT_LOW_POWER_HIGH_INTEREST]) == 1  # Dev Team
        assert len(quadrants[QUADRANT_LOW_POWER_LOW_INTEREST]) == 1  # Legal


class TestRecommendEngagementStrategies:
    def test_strategy_per_stakeholder(self, stakeholders):
        classified = _classify_stakeholders(stakeholders)
        strategies = _recommend_engagement_strategies(classified)
        assert len(strategies) == 5

    def test_high_power_gets_active_engagement(self, stakeholders):
        classified = _classify_stakeholders(stakeholders)
        strategies = _recommend_engagement_strategies(classified)
        ceo_strategy = next(s for s in strategies if s["stakeholder"] == "CEO")
        assert "Engage actively" in ceo_strategy["strategy"]
        assert ceo_strategy["communication_frequency"] == "weekly"

    def test_resistant_gets_concern_addressing(self, stakeholders):
        classified = _classify_stakeholders(stakeholders)
        strategies = _recommend_engagement_strategies(classified)
        legal_strategy = next(s for s in strategies if s["stakeholder"] == "Legal")
        assert "address concerns" in legal_strategy["strategy"]

    def test_supportive_gets_leverage(self, stakeholders):
        classified = _classify_stakeholders(stakeholders)
        strategies = _recommend_engagement_strategies(classified)
        ceo_strategy = next(s for s in strategies if s["stakeholder"] == "CEO")
        assert "leverage support" in ceo_strategy["strategy"]


class TestBuildStakeholderMap:
    def test_report_structure(self, stakeholders):
        report = build_stakeholder_map(stakeholders)
        assert report["schema_version"] == "max.stakeholder_map.v1"
        assert report["kind"] == "max.stakeholder_map"
        assert "stakeholders" in report
        assert "quadrants" in report
        assert "engagement_strategies" in report
        assert "summary" in report

    def test_summary_counts(self, stakeholders):
        report = build_stakeholder_map(stakeholders)
        summary = report["summary"]
        assert summary["total_stakeholders"] == 5
        assert summary["manage_closely"] == 2
        assert summary["keep_satisfied"] == 1
        assert summary["keep_informed"] == 1
        assert summary["monitor"] == 1


class TestRenderMarkdown:
    def test_renders_without_error(self, stakeholders):
        report = build_stakeholder_map(stakeholders)
        md = render_stakeholder_map_markdown(report)
        assert "# Stakeholder Map" in md
        assert "## Summary" in md
        assert "## Stakeholder Matrix" in md
        assert "## Engagement Strategies" in md

    def test_contains_stakeholder_data(self, stakeholders):
        report = build_stakeholder_map(stakeholders)
        md = render_stakeholder_map_markdown(report)
        assert "CEO" in md
        assert "CTO" in md
        assert "weekly" in md
