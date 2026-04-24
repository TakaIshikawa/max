"""Tests for MCP quality certification analysis."""

from __future__ import annotations

from max.analysis.mcp_quality_certification import (
    MCPQualityCertificationNotFound,
    build_mcp_quality_certification_report,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.signal import Signal, SignalSourceType


def _signal(
    signal_id: str,
    *,
    title: str,
    content: str,
    source_adapter: str = "mcp_registry",
    source_type: SignalSourceType = SignalSourceType.REGISTRY,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    credibility: float = 0.8,
) -> Signal:
    return Signal(
        id=signal_id,
        source_type=source_type,
        source_adapter=source_adapter,
        title=title,
        content=content,
        url=f"https://example.com/{signal_id}",
        tags=["mcp"] if tags is None else tags,
        metadata=metadata or {},
        credibility=credibility,
    )


def _unit(unit_id: str, evidence_signals: list[str]) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title="Filesystem MCP Server",
        one_liner="MCP server for filesystem automation",
        category=BuildableCategory.MCP_SERVER,
        ideation_mode=IdeationMode.DIRECT,
        problem="Agents need reliable file access.",
        solution="Expose audited filesystem tools through MCP.",
        target_users="agents",
        value_proposition="Safer local automation",
        evidence_signals=evidence_signals,
        quality_score=8.0,
        tech_approach="Python MCP server with permission gates",
        domain="devtools",
    )


def _evaluation(unit_id: str, score: float = 88.0) -> UtilityEvaluation:
    def dimension(value: float) -> DimensionScore:
        return DimensionScore(value=value, confidence=0.8, reasoning="seeded")

    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=dimension(8.0),
        addressable_scale=dimension(7.0),
        build_effort=dimension(8.0),
        composability=dimension(9.0),
        competitive_density=dimension(7.0),
        timing_fit=dimension(8.0),
        compounding_value=dimension(8.0),
        overall_score=score,
        recommendation="yes",
    )


def test_global_certification_passes_with_capability_reliability_and_idea_evidence(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "quality-pass.db"))
    try:
        store.insert_signal(
            _signal(
                "sig-files",
                title="Filesystem MCP server",
                content="Read files and directories with audit logging",
                tags=["mcp", "filesystem"],
            )
        )
        store.insert_signal(
            _signal(
                "sig-browser",
                title="Browser automation MCP",
                content="Playwright browser tools",
                source_adapter="npm_registry",
                tags=["mcp", "browser"],
            )
        )
        store.insert_buildable_unit(_unit("bu-mcp-pass", ["sig-files", "sig-browser"]))
        store.insert_evaluation(_evaluation("bu-mcp-pass", 90.0))

        report = build_mcp_quality_certification_report(store)
    finally:
        store.close()

    assert report.blocked is False
    assert report.grade in {"A", "B", "C"}
    assert report.score >= 70.0
    assert report.blockers == []
    assert any(component.name == "capability" for component in report.score_components)
    assert any("known capability categories" in component.explanation for component in report.score_components)
    assert any(ref.id == "sig-files" and ref.reason == "capability:filesystem" for ref in report.evidence_references)
    assert any(ref.kind == "idea" and ref.id == "bu-mcp-pass" for ref in report.evidence_references)


def test_certification_warns_when_security_findings_lower_grade(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "quality-warning.db"))
    try:
        store.insert_signal(
            _signal(
                "sig-data",
                title="Data MCP server",
                content="Postgres database analytics",
                tags=["mcp", "data"],
            )
        )
        store.insert_signal(
            _signal(
                "sig-security-medium",
                title="MCP server missing sandbox",
                content="Scanner found broad file permissions",
                source_adapter="mcp_security_import",
                source_type=SignalSourceType.SECURITY,
                tags=["mcp", "security", "severity:medium"],
                metadata={"severity": "medium", "server_name": "data-mcp"},
            )
        )
        store.insert_buildable_unit(_unit("bu-mcp-warning", ["sig-data", "sig-security-medium"]))
        store.insert_evaluation(_evaluation("bu-mcp-warning", 82.0))

        report = build_mcp_quality_certification_report(store, idea_id="bu-mcp-warning")
    finally:
        store.close()

    assert report.blocked is False
    assert report.score < 82.0
    assert "Medium severity MCP security findings require remediation tracking." in report.warnings
    assert any(ref.id == "sig-security-medium" and ref.reason == "security:medium" for ref in report.evidence_references)


def test_certification_blocks_on_critical_security_finding(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "quality-blocked.db"))
    try:
        store.insert_signal(
            _signal(
                "sig-critical",
                title="Critical MCP command injection",
                content="MCP server executes unsanitized arguments",
                source_adapter="mcp_security_import",
                source_type=SignalSourceType.SECURITY,
                tags=["mcp", "security", "severity:critical"],
                metadata={"severity": "critical", "server_name": "shell-mcp"},
            )
        )
        store.insert_buildable_unit(_unit("bu-mcp-blocked", ["sig-critical"]))
        store.insert_evaluation(_evaluation("bu-mcp-blocked", 95.0))

        report = build_mcp_quality_certification_report(store, idea_id="bu-mcp-blocked")
    finally:
        store.close()

    assert report.blocked is True
    assert report.grade == "blocked"
    assert report.score <= 59.0
    assert "Critical MCP security findings block certification." in report.blockers


def test_idea_certification_raises_for_unknown_idea(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "quality-missing.db"))
    try:
        try:
            build_mcp_quality_certification_report(store, idea_id="bu-missing")
        except MCPQualityCertificationNotFound as exc:
            assert str(exc) == "Idea not found: bu-missing"
        else:
            raise AssertionError("Expected MCPQualityCertificationNotFound")
    finally:
        store.close()
