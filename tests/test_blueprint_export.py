"""Tests for Blueprint source-brief export helpers."""

from __future__ import annotations

import json

import yaml

from max.analysis.blueprint_export import (
    SCHEMA_VERSION,
    blueprint_filename,
    build_blueprint_source_brief,
    render_blueprint_packet,
)


def _brief() -> dict:
    return {
        "id": "dbf-test001",
        "title": "AgentAdversarialBench",
        "domain": "developer-tools",
        "theme": "agent-security-evaluation",
        "readiness_score": 86.0,
        "buyer": "engineering manager",
        "specific_user": "platform engineer",
        "workflow_context": "CI gate before deployment",
        "why_this_now": "Agent tool use is growing.",
        "merged_product_concept": "Run adversarial workflow fixtures.",
        "synthesis_rationale": "Strong lead idea.",
        "mvp_scope": ["CLI runner"],
        "first_milestones": ["Prototype CLI"],
        "validation_plan": "Run with three teams.",
        "risks": ["Framework churn"],
        "source_idea_ids": ["bu-test001"],
        "design_status": "candidate",
        "created_at": "2026-04-22T00:00:00+00:00",
        "updated_at": "2026-04-22T00:00:00+00:00",
        "sources": [{"idea_id": "bu-test001", "role": "lead", "rank": 0}],
    }


def test_build_blueprint_source_brief_maps_design_brief(store, sample_unit, sample_evaluation):
    store.insert_buildable_unit(sample_unit)
    store.insert_evaluation(sample_evaluation)

    packet = build_blueprint_source_brief(store, _brief(), exported_at="2026-04-23T00:00:00+00:00")

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["source"] == {
        "project": "max",
        "entity_type": "design_brief",
        "id": "dbf-test001",
        "exported_at": "2026-04-23T00:00:00+00:00",
    }
    assert packet["design_brief"]["title"] == "AgentAdversarialBench"
    assert packet["source_ideas"][0]["id"] == "bu-test001"
    assert packet["source_ideas"][0]["evaluation_score"] == 78.0


def test_build_blueprint_source_brief_marks_missing_source_ideas(store):
    packet = build_blueprint_source_brief(store, _brief())

    assert packet["source_ideas"] == [
        {
            "id": "bu-test001",
            "role": "lead",
            "rank": 0,
            "missing": True,
        }
    ]


def test_render_blueprint_packet_json_and_yaml() -> None:
    packet = {"schema_version": SCHEMA_VERSION, "source": {"id": "dbf-test001"}}

    assert json.loads(render_blueprint_packet(packet, fmt="json")) == packet
    assert yaml.safe_load(render_blueprint_packet(packet, fmt="yaml")) == packet


def test_blueprint_filename_uses_brief_id_and_format() -> None:
    brief = _brief()

    assert blueprint_filename(brief, fmt="json") == "dbf-test001.json"
    assert blueprint_filename(brief, fmt="yaml") == "dbf-test001.yaml"
