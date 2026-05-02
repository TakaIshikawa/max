from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis import (
    build_design_brief_kill_criteria,
    kill_criteria_filename,
    render_design_brief_kill_criteria,
)
from max.analysis.design_brief_kill_criteria import KIND, SCHEMA_VERSION
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation


CSV_COLUMNS = [
    "design_brief_id",
    "design_brief_title",
    "criterion_type",
    "criterion_id",
    "category",
    "label",
    "status",
    "threshold",
    "evidence_backed_reason",
    "action",
    "source_reference_ids",
]


def test_empty_evidence_creates_stop_criteria() -> None:
    report = build_design_brief_kill_criteria(_sparse_unit())

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"]["decision"] == "stop"
    assert report["summary"]["evidence_count"] == 0
    assert report["summary"]["evidence_source_diversity"] == 0
    assert [item["id"] for item in report["stop_triggers"]] == [
        "DBKC-S1",
        "DBKC-S3",
        "DBKC-S4",
    ]
    assert report["pivot_triggers"] == []
    assert report["next_validation_action"]["owner"] == "product owner"


def test_strong_evidence_creates_continue_signals() -> None:
    unit = _strong_unit()
    evaluation = _evaluation(unit.id, recommendation="yes", pain=8.5, overall=86.0)
    report = build_design_brief_kill_criteria(unit, evaluation=evaluation)

    assert report["summary"]["decision"] == "continue"
    assert report["summary"]["problem_severity"] == "high"
    assert report["summary"]["evaluation_recommendation"] == "yes"
    assert report["summary"]["evidence_count"] == 5
    assert report["summary"]["evidence_source_diversity"] == 4
    assert report["stop_triggers"] == []
    assert report["pivot_triggers"] == []
    assert [item["id"] for item in report["continue_signals"]] == [
        "DBKC-C1",
        "DBKC-C2",
        "DBKC-C3",
        "DBKC-C4",
        "DBKC-C5",
    ]
    assert json.loads(json.dumps(report))["summary"]["decision"] == "continue"


def test_weak_contradictory_evidence_creates_pivot_criteria() -> None:
    unit = _strong_unit(
        evidence_signals=[],
        inspiring_insights=[],
        source_idea_ids=[],
        evidence_rationale="",
        tech_approach="OAuth API integration with vendor webhook dependency and platform permission review.",
        domain_risks=["Security review needed for OAuth credentials and regulated PII processing."],
    )
    evidence = [
        {
            "id": "sig-negative",
            "source_type": "signal",
            "summary": "Pilot users reported weak demand and rejected the workflow.",
            "polarity": "negative",
        }
    ]
    report = build_design_brief_kill_criteria(
        unit,
        evaluation={"recommendation": "maybe", "overall_score": 54.0, "pain_severity": {"value": 6.5}},
        evidence=evidence,
    )

    assert report["summary"]["decision"] == "pivot"
    assert report["summary"]["contradictory_evidence_count"] == 1
    assert report["summary"]["dependency_risk"] == "high"
    assert report["summary"]["compliance_security_risk"] == "high"
    assert [item["id"] for item in report["pivot_triggers"]] == [
        "DBKC-P1",
        "DBKC-P2",
        "DBKC-P3",
        "DBKC-P4",
        "DBKC-P5",
    ]
    assert report["pivot_triggers"][0]["source_reference_ids"] == ["sig-negative"]
    assert all(item["evidence_backed_reason"] for item in report["pivot_triggers"])


def test_markdown_json_invalid_format_and_filename() -> None:
    unit = _strong_unit()
    report = build_design_brief_kill_criteria(
        unit,
        evaluation=_evaluation(unit.id, recommendation="strong_yes", pain=8.0, overall=91.0),
    )

    rendered_json = render_design_brief_kill_criteria(report, fmt="json")
    assert json.loads(rendered_json) == report
    assert rendered_json == render_design_brief_kill_criteria(report, fmt="json")

    markdown = render_design_brief_kill_criteria(report)
    assert markdown.startswith("# Kill Criteria: Agent Evidence Gate")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "Kind: `max.design_brief.kill_criteria`" in markdown
    assert "## Stop Triggers" in markdown
    assert "## Pivot Triggers" in markdown
    assert "## Continue Signals" in markdown
    assert "## Next Validation Action" in markdown
    assert "DBKC-C2 Diverse evidence base" in markdown
    assert "{'" not in markdown
    assert "[{" not in markdown

    with pytest.raises(ValueError, match="Unsupported kill criteria format: yaml"):
        render_design_brief_kill_criteria(report, fmt="yaml")

    assert (
        kill_criteria_filename({"id": "dbf-123", "title": "Kill Criteria: Alpha / Beta"})
        == "dbf-123-Kill-Criteria-Alpha-Beta-kill-criteria.md"
    )
    assert (
        kill_criteria_filename(unit, fmt="json")
        == "bu-kill-strong-Agent-Evidence-Gate-kill-criteria.json"
    )
    assert (
        kill_criteria_filename(unit, fmt="csv")
        == "bu-kill-strong-Agent-Evidence-Gate-kill-criteria.csv"
    )


def test_csv_renderer_has_stable_headers_and_rows_across_criterion_groups() -> None:
    unit = _strong_unit()
    continue_report = build_design_brief_kill_criteria(
        unit,
        evaluation=_evaluation(unit.id, recommendation="yes", pain=8.5, overall=86.0),
    )
    stop_report = build_design_brief_kill_criteria(_sparse_unit())
    pivot_report = build_design_brief_kill_criteria(
        _strong_unit(
            evidence_signals=[],
            inspiring_insights=[],
            source_idea_ids=[],
            evidence_rationale="",
            tech_approach=(
                "OAuth API integration with vendor webhook dependency and platform permission review."
            ),
            domain_risks=["Security review needed for OAuth credentials and regulated PII processing."],
        ),
        evaluation={"recommendation": "maybe", "overall_score": 54.0, "pain_severity": {"value": 6.5}},
        evidence=[
            {
                "id": "sig-negative",
                "source_type": "signal",
                "summary": "Pilot users reported weak demand and rejected the workflow.",
                "polarity": "negative",
            }
        ],
    )
    report = json.loads(json.dumps(continue_report))
    report["stop_triggers"] = stop_report["stop_triggers"]
    report["pivot_triggers"] = pivot_report["pivot_triggers"]

    csv_text = render_design_brief_kill_criteria(report, fmt="csv")
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)

    assert reader.fieldnames == CSV_COLUMNS
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert csv_text == render_design_brief_kill_criteria(report, fmt="csv")
    assert len(rows) == (
        len(report["stop_triggers"])
        + len(report["pivot_triggers"])
        + len(report["continue_signals"])
    )
    assert [row["criterion_type"] for row in rows] == (
        ["stop"] * len(report["stop_triggers"])
        + ["pivot"] * len(report["pivot_triggers"])
        + ["continue"] * len(report["continue_signals"])
    )
    assert [row["criterion_id"] for row in rows[:3]] == ["DBKC-S1", "DBKC-S3", "DBKC-S4"]
    pivot_row = next(row for row in rows if row["criterion_id"] == "DBKC-P1")
    continue_row = next(row for row in rows if row["criterion_id"] == "DBKC-C2")
    assert pivot_row["design_brief_id"] == "bu-kill-strong"
    assert pivot_row["design_brief_title"] == "Agent Evidence Gate"
    assert pivot_row["category"] == "pivot"
    assert pivot_row["label"] == "Contradictory demand evidence"
    assert pivot_row["status"] == "active"
    assert pivot_row["threshold"]
    assert pivot_row["evidence_backed_reason"]
    assert pivot_row["action"]
    assert pivot_row["source_reference_ids"] == '["sig-negative"]'
    assert json.loads(pivot_row["source_reference_ids"]) == ["sig-negative"]
    assert json.loads(continue_row["source_reference_ids"]) == [
        "ins-kill-1",
        "sig-kill-1",
        "sig-kill-2",
        "bu-source-kill",
        "evidence-rationale",
    ]


def test_csv_renderer_returns_header_for_empty_criterion_groups() -> None:
    report = build_design_brief_kill_criteria(
        _strong_unit(),
        evaluation=_evaluation("bu-kill-strong", recommendation="yes", pain=8.5, overall=86.0),
    )
    empty_report = json.loads(json.dumps(report))
    empty_report["stop_triggers"] = []
    empty_report["pivot_triggers"] = []
    empty_report["continue_signals"] = []

    csv_text = render_design_brief_kill_criteria(empty_report, fmt="csv")

    assert list(csv.DictReader(io.StringIO(csv_text))) == []
    assert csv_text == ",".join(CSV_COLUMNS) + "\n"


def test_helpers_are_importable_from_max_analysis() -> None:
    from max.analysis import (  # noqa: PLC0415
        build_design_brief_kill_criteria as imported_build,
        kill_criteria_filename as imported_filename,
        render_design_brief_kill_criteria as imported_render,
    )

    assert imported_build is build_design_brief_kill_criteria
    assert imported_filename is kill_criteria_filename
    assert imported_render is render_design_brief_kill_criteria


def _sparse_unit() -> BuildableUnit:
    return BuildableUnit(
        id="bu-kill-sparse",
        title="Thin Idea",
        one_liner="Thin concept",
        category="application",
        problem="Minor annoyance",
        solution="A helper",
        value_proposition="Some value",
    )


def _strong_unit(**overrides) -> BuildableUnit:
    values = {
        "id": "bu-kill-strong",
        "title": "Agent Evidence Gate",
        "one_liner": "Stop agent expansion when concept evidence is too weak.",
        "category": "application",
        "problem": "Product teams waste costly review cycles because low-evidence agent ideas keep expanding into implementation plans.",
        "solution": "Generate explicit stop, pivot, and continue criteria from evidence and risk signals.",
        "value_proposition": "Keep idea generation focused on concepts with validated demand and manageable launch risk.",
        "specific_user": "product operations lead",
        "buyer": "VP of Product",
        "workflow_context": "design brief validation review before autonomous implementation",
        "current_workaround": "manual spreadsheet review with missed blockers",
        "why_now": "Agents now create larger idea portfolios that need deterministic disqualification gates.",
        "validation_plan": "Compare decisions against seeded strong, weak, contradictory, and empty evidence fixtures.",
        "domain_risks": ["Overzealous stop gates can reject novel ideas too early."],
        "evidence_rationale": "Three research artifacts show repeated expansion of weak concepts.",
        "inspiring_insights": ["ins-kill-1"],
        "evidence_signals": ["sig-kill-1", "sig-kill-2"],
        "source_idea_ids": ["bu-source-kill"],
        "tech_approach": "Deterministic Python artifact over BuildableUnit fields.",
        "suggested_stack": {"language": "python", "tests": "pytest"},
        "domain": "developer-tools",
        "status": "approved",
    }
    values.update(overrides)
    return BuildableUnit(**values)


def _evaluation(
    buildable_unit_id: str,
    *,
    recommendation: str,
    pain: float,
    overall: float,
) -> UtilityEvaluation:
    neutral = DimensionScore(value=7.0, confidence=0.8, reasoning="fixture")
    return UtilityEvaluation(
        buildable_unit_id=buildable_unit_id,
        pain_severity=DimensionScore(value=pain, confidence=0.9, reasoning="fixture"),
        addressable_scale=neutral,
        build_effort=neutral,
        composability=neutral,
        competitive_density=neutral,
        timing_fit=neutral,
        compounding_value=neutral,
        overall_score=overall,
        recommendation=recommendation,
    )
