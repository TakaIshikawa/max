"""Tests for portfolio theme saturation reporting."""

from __future__ import annotations

import csv
import json
from io import StringIO

import pytest
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.analysis.portfolio_theme_saturation import (
    SCHEMA_VERSION,
    build_portfolio_theme_saturation_report,
    render_portfolio_theme_saturation,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit


GENERATED_AT = "2026-04-30T00:00:00+00:00"


def test_theme_saturation_ranks_crowded_theme_and_flags_validation_gap(store: Store) -> None:
    for unit in [
        _unit("bu-sec-1", "Protocol test runner", theme=BuildableCategory.CLI_TOOL, quality=8.1),
        _unit("bu-sec-2", "Protocol fuzz harness", theme=BuildableCategory.CLI_TOOL, quality=7.9),
        _unit("bu-sec-3", "Protocol release gate", theme=BuildableCategory.CLI_TOOL, quality=7.5),
        _unit("bu-observe-1", "Usage dashboard", theme=BuildableCategory.APPLICATION, quality=5.5),
    ]:
        store.insert_buildable_unit(unit)
    store.insert_design_brief(
        _brief(
            "Security Validation Suite",
            "agent-security",
            _stored_unit(store, "bu-sec-1"),
            [_stored_unit(store, "bu-sec-2")],
            readiness=88.0,
        )
    )

    report = build_portfolio_theme_saturation_report(
        store,
        crowded_count=3,
        generated_at=GENERATED_AT,
    )

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == "max.portfolio_theme_saturation"
    assert report["generated_at"] == GENERATED_AT
    assert report["summary"]["total_items"] == 5
    assert report["summary"]["theme_bucket_count"] == 3

    top = report["theme_buckets"][0]
    assert top["domain"] == "devtools"
    assert top["theme"] == "cli_tool"
    assert top["item_count"] == 3
    assert top["source_idea_count"] == 3
    assert top["buildable_unit_count"] == 3
    assert top["design_brief_count"] == 0
    assert top["saturation_score"] > report["theme_buckets"][1]["saturation_score"]
    assert "crowded" in top["flags"]
    assert "missing_recent_validation" in top["flags"]
    assert report["saturation_flags"]["crowded"][0]["theme"] == "cli_tool"
    assert any("Pause new ideas" in item["action"] for item in report["recommendations"])
    assert json.loads(json.dumps(report))["summary"]["total_items"] == 5


def test_theme_saturation_csv_renderer_includes_bucket_rows_and_clean_ids(
    store: Store,
) -> None:
    for unit in [
        _unit("bu-sec-1", "Protocol test runner", theme=BuildableCategory.CLI_TOOL, quality=8.1),
        _unit("bu-sec-2", "Protocol fuzz harness", theme=BuildableCategory.CLI_TOOL, quality=7.9),
        _unit("bu-sec-3", "Protocol release gate", theme=BuildableCategory.CLI_TOOL, quality=7.5),
    ]:
        store.insert_buildable_unit(unit)
    store.insert_design_brief(
        _brief(
            "Security Validation Suite",
            "agent-security",
            _stored_unit(store, "bu-sec-1"),
            [_stored_unit(store, "bu-sec-2")],
            readiness=88.0,
        )
    )

    report = build_portfolio_theme_saturation_report(
        store,
        crowded_count=3,
        generated_at=GENERATED_AT,
    )

    csv_text = render_portfolio_theme_saturation(report, fmt="csv")
    assert csv_text.startswith(
        "theme_bucket_id,domain_coverage,theme,item_count,source_idea_count,"
    )
    rows = list(csv.DictReader(StringIO(csv_text)))

    cli_row = next(row for row in rows if row["theme"] == "cli_tool")
    assert cli_row["theme_bucket_id"] == "devtools:cli_tool"
    assert cli_row["domain_coverage"] == "devtools"
    assert cli_row["item_count"] == "3"
    assert cli_row["source_idea_count"] == "3"
    assert cli_row["buildable_unit_count"] == "3"
    assert cli_row["design_brief_count"] == "0"
    assert cli_row["evidence_count"] == "3"
    assert cli_row["recent_validation_count"] == "0"
    assert cli_row["flags"] == "crowded;missing_recent_validation"
    assert cli_row["representative_idea_ids"] == "bu-sec-1;bu-sec-2;bu-sec-3"
    assert cli_row["representative_design_brief_ids"] == ""
    assert cli_row["source_idea_ids"] == "bu-sec-1;bu-sec-2;bu-sec-3"
    assert "Pause new ideas in devtools / cli_tool" in cli_row["recommendations"]
    assert "[" not in cli_row["representative_idea_ids"]
    assert "'" not in cli_row["representative_idea_ids"]

    brief_row = next(row for row in rows if row["theme"] == "agent-security")
    assert brief_row["design_brief_count"] == "1"
    assert brief_row["representative_idea_ids"] == ""
    assert brief_row["representative_design_brief_ids"]
    assert "[" not in brief_row["representative_design_brief_ids"]
    assert "'" not in brief_row["representative_design_brief_ids"]


def test_theme_saturation_filters_domain_and_recommends_underrepresented_theme(
    store: Store,
) -> None:
    underrepresented = _unit(
        "bu-finops-1",
        "Invoice anomaly detector",
        domain="finops",
        theme=BuildableCategory.AUTOMATION,
        quality=6.5,
        evidence=["sig-finops-1", "sig-finops-2", "sig-finops-3"],
    )
    store.insert_buildable_unit(underrepresented)
    store.insert_buildable_unit(
        _unit("bu-devtools-1", "SDK release notes", theme=BuildableCategory.FEATURE)
    )
    store.create_validation_experiment(
        idea_id="bu-finops-1",
        hypothesis="Finance teams will review anomaly alerts weekly.",
        method="Concierge validation",
        target_sample_size=5,
        success_metric="Four qualified reviews",
        status="completed",
        completed_at="2026-04-20T00:00:00+00:00",
        result_summary=json.dumps({"outcome": "validated"}),
        evidence_urls=["https://example.test/evidence"],
        confidence_delta=0.4,
    )

    report = build_portfolio_theme_saturation_report(
        store,
        domain="finops",
        min_count=1,
        generated_at=GENERATED_AT,
    )

    assert report["filters"] == {"domain": ["finops"], "min_count": 1}
    assert report["summary"]["total_items"] == 1
    assert len(report["theme_buckets"]) == 1
    bucket = report["theme_buckets"][0]
    assert bucket["theme"] == "automation"
    assert bucket["recent_validation_count"] == 1
    assert bucket["flags"] == []
    assert any("underrepresented theme" in item["action"] for item in report["recommendations"])


def test_theme_saturation_sparse_portfolio_returns_actionable_recommendations(
    store: Store,
) -> None:
    store.insert_buildable_unit(
        _unit("bu-sparse-1", "One sparse idea", evidence=[], theme=BuildableCategory.LIBRARY)
    )

    report = build_portfolio_theme_saturation_report(
        store,
        min_count=2,
        generated_at=GENERATED_AT,
    )

    assert report["summary"]["total_items"] == 1
    assert report["theme_buckets"] == []
    assert report["saturation_flags"] == {
        "crowded": [],
        "thinly_evidenced": [],
        "missing_recent_validation": [],
    }
    assert "Lower min_count below 2" in report["recommendations"][0]["action"]


def test_theme_saturation_csv_renderer_returns_header_for_empty_bucket_report(
    store: Store,
) -> None:
    store.insert_buildable_unit(
        _unit("bu-sparse-1", "One sparse idea", evidence=[], theme=BuildableCategory.LIBRARY)
    )

    report = build_portfolio_theme_saturation_report(
        store,
        min_count=2,
        generated_at=GENERATED_AT,
    )

    csv_text = render_portfolio_theme_saturation(report, fmt="csv")

    assert list(csv.DictReader(StringIO(csv_text))) == []
    assert csv_text == (
        "theme_bucket_id,domain_coverage,theme,item_count,source_idea_count,"
        "buildable_unit_count,design_brief_count,evidence_count,evidence_concentration,"
        "recent_validation_count,saturation_score,flags,representative_idea_ids,"
        "representative_design_brief_ids,source_idea_ids,recent_validation_idea_ids,"
        "recommendations\n"
    )


def test_theme_saturation_renderer_rejects_unsupported_format(store: Store) -> None:
    report = build_portfolio_theme_saturation_report(store, generated_at=GENERATED_AT)

    with pytest.raises(ValueError, match="Unsupported portfolio theme saturation format"):
        render_portfolio_theme_saturation(report, fmt="xml")


def _unit(
    unit_id: str,
    title: str,
    *,
    domain: str = "devtools",
    theme: BuildableCategory = BuildableCategory.CLI_TOOL,
    quality: float = 7.0,
    evidence: list[str] | None = None,
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=title,
        one_liner=f"{title} for portfolio operators",
        category=theme,
        problem="Teams cannot tell whether a portfolio theme is saturated.",
        solution="Provide a deterministic saturation report.",
        target_users="product operators",
        value_proposition="Focus idea generation where it is needed.",
        specific_user="portfolio lead",
        buyer="product leadership",
        workflow_context="portfolio review",
        validation_plan="Review saturation decisions with three operators.",
        evidence_signals=evidence or [f"sig-{unit_id}"],
        inspiring_insights=[f"ins-{unit_id}"] if evidence is not None else [],
        quality_score=quality,
        usefulness_score=quality,
        status="approved",
        domain=domain,
    )


def _brief(
    title: str,
    theme: str,
    lead: BuildableUnit,
    supporting: list[BuildableUnit],
    *,
    readiness: float,
) -> ProjectBrief:
    candidates = [Candidate(unit=unit, readiness_score=readiness) for unit in supporting]
    return ProjectBrief(
        title=title,
        domain=lead.domain,
        theme=theme,
        lead=Candidate(unit=lead, readiness_score=readiness),
        supporting=candidates,
        readiness_score=readiness,
        why_this_now="Portfolio operators are generating adjacent ideas.",
        merged_product_concept="A saturation report for design brief planning.",
        synthesis_rationale="The source ideas share a domain and validation workflow.",
        mvp_scope=["Theme bucket ranking"],
        first_milestones=["Ship deterministic report"],
        validation_plan="Run against a persisted portfolio.",
        risks=["Theme labels may be noisy."],
        source_idea_ids=[lead.id, *[unit.id for unit in supporting]],
    )


def _stored_unit(store: Store, unit_id: str) -> BuildableUnit:
    unit = store.get_buildable_unit(unit_id)
    assert unit is not None
    return unit
