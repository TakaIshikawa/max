"""Tests for OKR document export — hierarchical objectives and key results."""

from __future__ import annotations

import json

from max.exports.okr_export import (
    KIND,
    LEVEL_COMPANY,
    LEVEL_INDIVIDUAL,
    LEVEL_TEAM,
    SCHEMA_VERSION,
    _calculate_average_progress,
    _render_progress_bar,
    _validate_key_result,
    _validate_objective,
    build_okr_document,
    render_okr_json,
    render_okr_markdown,
)


# ── Test Data ────────────────────────────────────────────────────────

SAMPLE_OBJECTIVES = [
    {
        "title": "Increase platform adoption",
        "level": "company",
        "description": "Drive user growth across all product lines",
        "owner": "CEO",
        "key_results": [
            {
                "title": "Reach 10,000 monthly active users",
                "baseline": 5000,
                "target": 10000,
                "current": 7500,
                "unit": "users",
            },
            {
                "title": "Achieve 95% customer satisfaction",
                "baseline": 80,
                "target": 95,
                "current": 88,
                "unit": "percent",
            },
        ],
    },
    {
        "title": "Improve engineering velocity",
        "level": "team",
        "description": "Ship features faster with fewer bugs",
        "owner": "Engineering Lead",
        "key_results": [
            {
                "title": "Reduce deployment time to under 10 minutes",
                "baseline": 30,
                "target": 10,
                "current": 15,
                "unit": "minutes",
            },
            {
                "title": "Increase test coverage to 90%",
                "baseline": 60,
                "target": 90,
                "current": 75,
                "unit": "percent",
            },
        ],
    },
    {
        "title": "Master Kubernetes operations",
        "level": "individual",
        "description": "Develop expertise in container orchestration",
        "owner": "Junior DevOps Engineer",
        "key_results": [
            {
                "title": "Complete CKA certification",
                "baseline": 0,
                "target": 1,
                "current": 0,
                "progress": 30,
                "unit": "certification",
            },
            {
                "title": "Deploy 5 production services to k8s",
                "baseline": 0,
                "target": 5,
                "current": 3,
                "unit": "services",
            },
        ],
    },
]


# ── build_okr_document tests ─────────────────────────────────────────


def test_build_okr_document_schema() -> None:
    doc = build_okr_document(SAMPLE_OBJECTIVES)
    assert doc["schema_version"] == SCHEMA_VERSION
    assert doc["kind"] == KIND
    assert "generated_at" in doc


def test_build_okr_document_title_and_metadata() -> None:
    doc = build_okr_document(
        SAMPLE_OBJECTIVES, title="Q1 OKRs", period="Q1 2026", owner="VP Product"
    )
    assert doc["title"] == "Q1 OKRs"
    assert doc["period"] == "Q1 2026"
    assert doc["owner"] == "VP Product"


def test_build_okr_document_groups_by_level() -> None:
    doc = build_okr_document(SAMPLE_OBJECTIVES)
    objectives = doc["objectives"]
    assert len(objectives[LEVEL_COMPANY]) == 1
    assert len(objectives[LEVEL_TEAM]) == 1
    assert len(objectives[LEVEL_INDIVIDUAL]) == 1


def test_build_okr_document_summary_totals() -> None:
    doc = build_okr_document(SAMPLE_OBJECTIVES)
    summary = doc["summary"]
    assert summary["total_objectives"] == 3
    assert summary["total_key_results"] == 6
    assert summary["by_level"]["company"] == 1
    assert summary["by_level"]["team"] == 1
    assert summary["by_level"]["individual"] == 1


def test_build_okr_document_average_progress() -> None:
    doc = build_okr_document(SAMPLE_OBJECTIVES)
    # Progress is calculated from baseline/target/current
    assert 0 <= doc["summary"]["average_progress"] <= 100


def test_build_okr_document_empty_objectives() -> None:
    doc = build_okr_document([])
    assert doc["summary"]["total_objectives"] == 0
    assert doc["summary"]["total_key_results"] == 0
    assert doc["summary"]["average_progress"] == 0.0


# ── Key result validation and measurability ──────────────────────────


def test_validate_key_result_calculates_progress() -> None:
    kr = _validate_key_result({
        "title": "Increase users",
        "baseline": 100,
        "target": 200,
        "current": 150,
    })
    assert kr["progress"] == 50.0


def test_validate_key_result_caps_progress_at_100() -> None:
    kr = _validate_key_result({
        "title": "Over-achieved",
        "baseline": 0,
        "target": 10,
        "current": 15,
    })
    assert kr["progress"] == 100.0


def test_validate_key_result_floors_progress_at_0() -> None:
    kr = _validate_key_result({
        "title": "Regression",
        "baseline": 100,
        "target": 200,
        "current": 50,
    })
    assert kr["progress"] == 0.0


def test_validate_key_result_uses_explicit_progress_when_no_numbers() -> None:
    kr = _validate_key_result({
        "title": "Complete certification",
        "progress": 30,
    })
    assert kr["progress"] == 30


def test_validate_key_result_preserves_unit() -> None:
    kr = _validate_key_result({
        "title": "Metric",
        "baseline": 0,
        "target": 100,
        "current": 50,
        "unit": "percent",
    })
    assert kr["unit"] == "percent"


def test_validate_key_result_handles_reverse_target() -> None:
    """When target < baseline (e.g. reducing time), progress still works."""
    kr = _validate_key_result({
        "title": "Reduce deploy time",
        "baseline": 30,
        "target": 10,
        "current": 20,
    })
    assert kr["progress"] == 50.0


def test_validate_key_result_zero_division_safe() -> None:
    kr = _validate_key_result({
        "title": "Same baseline and target",
        "baseline": 10,
        "target": 10,
        "current": 10,
    })
    # Should not crash; uses fallback progress
    assert kr["progress"] == 0


# ── Objective validation ─────────────────────────────────────────────


def test_validate_objective_defaults() -> None:
    obj = _validate_objective({})
    assert obj["title"] == "Untitled Objective"
    assert obj["level"] == LEVEL_TEAM
    assert obj["key_results"] == []


def test_validate_objective_invalid_level_defaults_to_team() -> None:
    obj = _validate_objective({"title": "Test", "level": "invalid"})
    assert obj["level"] == LEVEL_TEAM


def test_validate_objective_preserves_valid_level() -> None:
    obj = _validate_objective({"title": "Test", "level": "company"})
    assert obj["level"] == LEVEL_COMPANY


# ── Markdown rendering ───────────────────────────────────────────────


def test_render_okr_markdown_contains_title() -> None:
    doc = build_okr_document(SAMPLE_OBJECTIVES, title="Q1 2026 OKRs")
    md = render_okr_markdown(doc)
    assert "# Q1 2026 OKRs" in md


def test_render_okr_markdown_contains_all_levels() -> None:
    doc = build_okr_document(SAMPLE_OBJECTIVES)
    md = render_okr_markdown(doc)
    assert "## Company Objectives" in md
    assert "## Team Objectives" in md
    assert "## Individual Objectives" in md


def test_render_okr_markdown_contains_key_results() -> None:
    doc = build_okr_document(SAMPLE_OBJECTIVES)
    md = render_okr_markdown(doc)
    assert "Reach 10,000 monthly active users" in md
    assert "Reduce deployment time to under 10 minutes" in md


def test_render_okr_markdown_contains_progress() -> None:
    doc = build_okr_document(SAMPLE_OBJECTIVES)
    md = render_okr_markdown(doc)
    # Should contain progress percentage
    assert "%" in md


def test_render_okr_markdown_contains_baseline_target() -> None:
    doc = build_okr_document(SAMPLE_OBJECTIVES)
    md = render_okr_markdown(doc)
    assert "Baseline:" in md
    assert "Target:" in md
    assert "Current:" in md


def test_render_okr_markdown_contains_owners() -> None:
    doc = build_okr_document(SAMPLE_OBJECTIVES)
    md = render_okr_markdown(doc)
    assert "CEO" in md
    assert "Engineering Lead" in md


def test_render_okr_markdown_skips_empty_levels() -> None:
    doc = build_okr_document([SAMPLE_OBJECTIVES[0]])  # Only company level
    md = render_okr_markdown(doc)
    assert "## Company Objectives" in md
    assert "## Team Objectives" not in md
    assert "## Individual Objectives" not in md


def test_render_okr_markdown_summary_section() -> None:
    doc = build_okr_document(SAMPLE_OBJECTIVES)
    md = render_okr_markdown(doc)
    assert "## Summary" in md
    assert "Total objectives: 3" in md
    assert "Total key results: 6" in md


def test_render_okr_markdown_period() -> None:
    doc = build_okr_document(SAMPLE_OBJECTIVES, period="Q1 2026")
    md = render_okr_markdown(doc)
    assert "Period: Q1 2026" in md


# ── JSON rendering ───────────────────────────────────────────────────


def test_render_okr_json_valid() -> None:
    doc = build_okr_document(SAMPLE_OBJECTIVES)
    output = render_okr_json(doc)
    parsed = json.loads(output)
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND


def test_render_okr_json_roundtrip() -> None:
    doc = build_okr_document(SAMPLE_OBJECTIVES)
    output = render_okr_json(doc)
    parsed = json.loads(output)
    assert parsed["summary"]["total_objectives"] == 3
    assert len(parsed["objectives"]["company"]) == 1


# ── Progress bar rendering ───────────────────────────────────────────


def test_render_progress_bar_empty() -> None:
    bar = _render_progress_bar(0)
    assert bar == "[░░░░░░░░░░]"


def test_render_progress_bar_full() -> None:
    bar = _render_progress_bar(100)
    assert bar == "[██████████]"


def test_render_progress_bar_half() -> None:
    bar = _render_progress_bar(50)
    assert bar == "[█████░░░░░]"


# ── Average progress calculation ─────────────────────────────────────


def test_calculate_average_progress_empty() -> None:
    assert _calculate_average_progress([]) == 0.0


def test_calculate_average_progress_mixed() -> None:
    objs = [
        {"key_results": [{"progress": 50}, {"progress": 100}]},
        {"key_results": [{"progress": 0}]},
    ]
    assert _calculate_average_progress(objs) == 50.0
