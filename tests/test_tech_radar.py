"""Tests for technology radar export."""

from __future__ import annotations

import json

from max.exports.tech_radar import (
    KIND,
    SCHEMA_VERSION,
    RadarQuadrant,
    RadarRing,
    build_tech_radar,
    classify_radar_ring,
    render_tech_radar_json,
    render_tech_radar_markdown,
)


def test_radar_ring_classification_from_scores_and_risk_signals() -> None:
    assert classify_radar_ring(88) == RadarRing.ADOPT
    assert classify_radar_ring(70) == RadarRing.TRIAL
    assert classify_radar_ring(45) == RadarRing.ASSESS
    assert classify_radar_ring(30) == RadarRing.HOLD
    assert classify_radar_ring(
        82,
        [
            {"title": "OldAuth is deprecated"},
            {"content": "critical security risk and end of life"},
        ],
    ) == RadarRing.HOLD


def test_build_tech_radar_from_units_and_evaluations() -> None:
    units = [
        {
            "id": "bu-1",
            "title": "Support Console",
            "tech_stack": ["React", "FastAPI", "Postgres"],
            "metadata": {"quadrant": RadarQuadrant.TOOLS.value},
        },
        {
            "id": "bu-2",
            "title": "Legacy Auth Migration",
            "suggested_stack": {"backend": "OldAuth"},
            "evaluation": {"overall_score": 31},
        },
    ]
    evaluations = [{"idea_id": "bu-1", "overall_score": 86}]
    signals = [
        {"technology": "React", "title": "React production adoption"},
        {"technology": "OldAuth", "title": "OldAuth deprecated", "content": "critical security risk"},
    ]

    report = build_tech_radar(units, evaluations=evaluations, signals=signals)
    by_name = {entry["name"]: entry for entry in report["entries"]}

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert by_name["React"]["ring"] == RadarRing.ADOPT.value
    assert by_name["FastAPI"]["ring"] == RadarRing.ADOPT.value
    assert by_name["OldAuth"]["ring"] == RadarRing.HOLD.value
    assert by_name["React"]["quadrant"] == RadarQuadrant.TOOLS.value


def test_renderers_produce_stable_output() -> None:
    report = build_tech_radar(
        [{"id": "bu-1", "title": "Agent Workflow", "tech_stack": ["Python"], "evaluation": {"overall_score": 65}}],
    )

    markdown = render_tech_radar_markdown(report)
    payload = json.loads(render_tech_radar_json(report))

    assert markdown.startswith("# Technology Radar")
    assert "| Technology | Quadrant | Ring | Score | Evidence |" in markdown
    assert payload["summary"]["technology_count"] == 1
    assert payload["entries"][0]["name"] == "Python"


def test_empty_radar_is_stable() -> None:
    report = build_tech_radar([])

    assert report["entries"] == []
    assert report["summary"]["technology_count"] == 0
    assert "No technologies identified" in render_tech_radar_markdown(report)
