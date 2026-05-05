"""Tests for design brief technical risks markdown renderer."""

from __future__ import annotations

import json

from max.analysis.design_brief_technical_risks import (
    KIND,
    SCHEMA_VERSION,
    build_design_brief_technical_risks,
    render_design_brief_technical_risks,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit


def _create_test_brief(store: Store) -> str:
    """Create a test design brief with risks."""
    # Create a buildable unit with domain risks
    unit = BuildableUnit(
        id="test-idea-001",
        title="Test Idea",
        one_liner="A test idea",
        category=BuildableCategory.FEATURE,
        problem="Test problem",
        solution="Test solution",
        target_users="test users",
        value_proposition="Test value",
        domain="healthcare",
        domain_risks=[
            "HIPAA compliance may block launch",
            "Critical data loss risk during migration",
            "High likelihood of integration failures",
        ],
        status="approved",
    )
    store.insert_buildable_unit(unit)

    # Create design brief with ProjectBrief
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Healthcare Data Migration",
            domain="healthcare",
            theme="compliance",
            lead=Candidate(unit=unit),
            supporting=[],
            readiness_score=75.0,
            why_this_now="Migration needed for compliance",
            merged_product_concept="Secure data migration with HIPAA compliance",
            synthesis_rationale="Critical for regulatory approval",
            mvp_scope=["Data validation", "Migration scripts", "Compliance reporting"],
            first_milestones=["Phase 1: Data audit"],
            validation_plan="Test with de-identified data",
            design_status="in_progress",
            risks=[
                "Regulatory approval required before deployment",
                "Severe performance degradation under load",
            ],
        )
    )

    return brief_id


def test_build_design_brief_technical_risks_structure(tmp_path) -> None:
    """Verify technical risks report has expected structure."""
    store = Store(db_path=tmp_path / "test.db", wal_mode=True)
    try:
        brief_id = _create_test_brief(store)

        report = build_design_brief_technical_risks(store, brief_id)

        assert report is not None
        assert report["schema_version"] == SCHEMA_VERSION
        assert report["kind"] == KIND
        assert "source" in report
        assert "design_brief" in report
        assert "summary" in report
        assert "technical_risks" in report
        assert "source_ideas" in report

        assert report["design_brief"]["id"] == brief_id
        assert report["design_brief"]["title"] == "Healthcare Data Migration"
    finally:
        store.close()


def test_build_design_brief_technical_risks_extracts_risks(tmp_path) -> None:
    """Verify risks are extracted from design brief and source ideas."""
    store = Store(db_path=tmp_path / "test.db", wal_mode=True)
    try:
        brief_id = _create_test_brief(store)

        report = build_design_brief_technical_risks(store, brief_id)

        assert report is not None
        risks = report["technical_risks"]

        # Should have risks from both design brief and idea
        assert len(risks) >= 5

        # Verify risk structure
        for risk in risks:
            assert "id" in risk
            assert risk["id"].startswith("RISK-")
            assert "category" in risk
            assert "severity" in risk
            assert risk["severity"] in ["critical", "high", "medium", "low"]
            assert "likelihood" in risk
            assert "description" in risk
            assert "mitigation_strategy" in risk
            assert "owner" in risk
            assert "source" in risk
    finally:
        store.close()


def test_build_design_brief_technical_risks_infers_severity(tmp_path) -> None:
    """Verify severity levels are inferred from risk descriptions."""
    store = Store(db_path=tmp_path / "test.db", wal_mode=True)
    try:
        brief_id = _create_test_brief(store)

        report = build_design_brief_technical_risks(store, brief_id)

        assert report is not None
        risks_by_desc = {r["description"]: r for r in report["technical_risks"]}

        # "Critical" keyword should result in critical severity
        critical_risk = risks_by_desc.get("Critical data loss risk during migration")
        if critical_risk:
            assert critical_risk["severity"] == "critical"

        # "Severe" keyword should result in critical severity
        severe_risk = risks_by_desc.get("Severe performance degradation under load")
        if severe_risk:
            assert severe_risk["severity"] == "critical"

        # "High" keyword should result in high severity
        high_risk = risks_by_desc.get("High likelihood of integration failures")
        if high_risk:
            assert high_risk["severity"] == "high"
    finally:
        store.close()


def test_build_design_brief_technical_risks_summary_counts(tmp_path) -> None:
    """Verify summary contains correct risk counts by severity."""
    store = Store(db_path=tmp_path / "test.db", wal_mode=True)
    try:
        brief_id = _create_test_brief(store)

        report = build_design_brief_technical_risks(store, brief_id)

        assert report is not None
        summary = report["summary"]

        assert summary["risk_count"] == len(report["technical_risks"])
        assert summary["critical_risk_count"] >= 0
        assert summary["high_risk_count"] >= 0
        assert summary["medium_risk_count"] >= 0
        assert summary["low_risk_count"] >= 0

        # Total should match
        total = (
            summary["critical_risk_count"]
            + summary["high_risk_count"]
            + summary["medium_risk_count"]
            + summary["low_risk_count"]
        )
        assert total == summary["risk_count"]
    finally:
        store.close()


def test_render_design_brief_technical_risks_json_valid(tmp_path) -> None:
    """Verify JSON rendering produces valid JSON."""
    store = Store(db_path=tmp_path / "test.db", wal_mode=True)
    try:
        brief_id = _create_test_brief(store)
        report = build_design_brief_technical_risks(store, brief_id)

        assert report is not None
        json_output = render_design_brief_technical_risks(report, fmt="json")

        # Should be valid JSON
        parsed = json.loads(json_output)
        assert parsed["schema_version"] == SCHEMA_VERSION
        assert parsed["kind"] == KIND
    finally:
        store.close()


def test_render_design_brief_technical_risks_markdown_structure(tmp_path) -> None:
    """Verify markdown rendering has expected sections and structure."""
    store = Store(db_path=tmp_path / "test.db", wal_mode=True)
    try:
        brief_id = _create_test_brief(store)
        report = build_design_brief_technical_risks(store, brief_id)

        assert report is not None
        markdown = render_design_brief_technical_risks(report, fmt="markdown")

        # Check for expected headings
        assert "# Technical Risks:" in markdown
        assert "## Risk Summary" in markdown
        assert "## Technical Risks" in markdown

        # Check for risk metadata
        assert "Schema:" in markdown
        assert "Design brief:" in markdown
        assert "Status:" in markdown
        assert "Readiness:" in markdown

        # Check for summary counts
        assert "Total risks:" in markdown
        assert "Critical:" in markdown
        assert "High:" in markdown
        assert "Medium:" in markdown
        assert "Low:" in markdown
    finally:
        store.close()


def test_render_design_brief_technical_risks_markdown_risk_sections(tmp_path) -> None:
    """Verify each risk is rendered with complete information."""
    store = Store(db_path=tmp_path / "test.db", wal_mode=True)
    try:
        brief_id = _create_test_brief(store)
        report = build_design_brief_technical_risks(store, brief_id)

        assert report is not None
        markdown = render_design_brief_technical_risks(report, fmt="markdown")

        # Each risk should have these fields
        assert "**Severity**:" in markdown
        assert "**Likelihood**:" in markdown
        assert "**Description**:" in markdown
        assert "**Mitigation strategy**:" in markdown
        assert "**Owner**:" in markdown

        # Verify some actual risk content appears
        assert "HIPAA" in markdown or "Regulatory" in markdown
    finally:
        store.close()


def test_render_design_brief_technical_risks_markdown_severity_formatting(tmp_path) -> None:
    """Verify severity levels render consistently."""
    store = Store(db_path=tmp_path / "test.db", wal_mode=True)
    try:
        brief_id = _create_test_brief(store)
        report = build_design_brief_technical_risks(store, brief_id)

        assert report is not None
        markdown = render_design_brief_technical_risks(report, fmt="markdown")

        # Severity values should appear formatted
        lines = markdown.split("\n")
        severity_lines = [line for line in lines if "**Severity**:" in line]

        assert len(severity_lines) > 0

        for line in severity_lines:
            # Extract severity value
            parts = line.split("**Severity**:")
            if len(parts) > 1:
                severity_value = parts[1].strip()
                assert severity_value in ["critical", "high", "medium", "low"]
    finally:
        store.close()


def test_build_design_brief_technical_risks_fallback_when_no_risks(tmp_path) -> None:
    """Verify fallback risk is created when no risks exist."""
    store = Store(db_path=tmp_path / "test.db", wal_mode=True)
    try:
        # Create unit without domain risks
        unit = BuildableUnit(
            id="test-idea-002",
            title="Simple Idea",
            one_liner="A simple idea",
            category=BuildableCategory.FEATURE,
            problem="Simple problem",
            solution="Simple solution",
            target_users="users",
            value_proposition="value",
            status="approved",
        )
        store.insert_buildable_unit(unit)

        # Create brief without domain risks
        brief_id = store.insert_design_brief(
            ProjectBrief(
                title="Simple Project",
                domain="general",
                theme="simple",
                lead=Candidate(unit=unit),
                supporting=[],
                readiness_score=50.0,
                why_this_now="Simple project",
                merged_product_concept="Simple concept",
                synthesis_rationale="Simple rationale",
                mvp_scope=[],
                first_milestones=[],
                validation_plan="Simple validation",
                design_status="draft",
                risks=[],
            )
        )

        report = build_design_brief_technical_risks(store, brief_id)

        assert report is not None
        risks = report["technical_risks"]

        # Should have at least the fallback risk
        assert len(risks) == 1
        assert risks[0]["category"] == "general"
        assert risks[0]["source"] == "fallback"
        assert "No explicit technical risks" in risks[0]["description"]
    finally:
        store.close()


def test_build_design_brief_technical_risks_returns_none_for_missing_brief(
    tmp_path,
) -> None:
    """Verify None is returned when design brief doesn't exist."""
    store = Store(db_path=tmp_path / "test.db", wal_mode=True)
    try:
        report = build_design_brief_technical_risks(store, "nonexistent-brief")
        assert report is None
    finally:
        store.close()
