"""Tests for decision log export."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.decision_log import (
    SCHEMA_VERSION,
    KIND,
    STATUS_PROPOSED,
    STATUS_ACCEPTED,
    STATUS_DEPRECATED,
    STATUS_SUPERSEDED,
    VALID_STATUSES,
    build_decision_log,
    render_decision_log_json,
    render_decision_log_markdown,
    _extract_decisions,
    _build_options,
    _infer_consequences,
    _build_summary,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_unit(
    *,
    unit_id: str = "bu-001",
    solution: str = "New API gateway",
    problem: str = "Existing gateway is slow",
    domain: str = "infrastructure",
    quality_score: float = 0.8,
    value_proposition: str = "3x throughput improvement",
    current_workaround: str = "Manual load balancing",
    target_users: str = "developers",
    evidence_signals: list[str] | None = None,
) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.solution = solution
    unit.problem = problem
    unit.domain = domain
    unit.quality_score = quality_score
    unit.value_proposition = value_proposition
    unit.current_workaround = current_workaround
    unit.target_users = target_users
    unit.evidence_signals = evidence_signals or []
    return unit




def _mock_store(
    units: list | None = None,
    signals: list | None = None,
) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units or []
    store.get_signals.return_value = signals or []
    return store


# ── Schema and structure tests ───────────────────────────────────────


def test_build_decision_log_schema() -> None:
    store = _mock_store()
    result = build_decision_log(store)
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == KIND
    assert "generated_at" in result
    assert "decision_count" in result
    assert "decisions" in result
    assert "summary" in result


def test_build_decision_log_domain_filter() -> None:
    store = _mock_store()
    build_decision_log(store, domain="security")
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="security")


def test_build_decision_log_count() -> None:
    units = [_make_unit(), _make_unit(unit_id="bu-002", solution="Solution B")]
    store = _mock_store(units=units)
    result = build_decision_log(store)
    assert result["decision_count"] == 2


# ── Decision extraction tests ───────────────────────────────────────


def test_extract_decisions_from_units() -> None:
    units = [_make_unit()]
    decisions = _extract_decisions(units)
    assert len(decisions) == 1
    assert decisions[0]["title"] == "New API gateway"
    assert decisions[0]["context"] == "Existing gateway is slow"


def test_extract_decisions_status_accepted() -> None:
    units = [_make_unit(quality_score=0.9)]
    decisions = _extract_decisions(units)
    assert decisions[0]["status"] == STATUS_ACCEPTED


def test_extract_decisions_status_proposed() -> None:
    units = [_make_unit(quality_score=0.5)]
    decisions = _extract_decisions(units)
    assert decisions[0]["status"] == STATUS_PROPOSED


def test_extract_decisions_ids_sequential() -> None:
    units = [
        _make_unit(unit_id="bu-1", solution="A"),
        _make_unit(unit_id="bu-2", solution="B"),
    ]
    decisions = _extract_decisions(units)
    assert decisions[0]["id"] == "DEC-001"
    assert decisions[1]["id"] == "DEC-002"


def test_extract_decisions_skips_empty_solution() -> None:
    units = [_make_unit(solution="")]
    decisions = _extract_decisions(units)
    assert len(decisions) == 0


def test_extract_decisions_includes_evidence() -> None:
    units = [_make_unit(evidence_signals=["sig-001", "sig-002"])]
    decisions = _extract_decisions(units)
    assert decisions[0]["evidence_signals"] == ["sig-001", "sig-002"]


# ── Options tests ────────────────────────────────────────────────────


def test_build_options_includes_chosen() -> None:
    unit = _make_unit()
    options = _build_options(unit)
    selected = [o for o in options if o["selected"]]
    assert len(selected) == 1
    assert selected[0]["name"] == "New API gateway"


def test_build_options_includes_workaround() -> None:
    unit = _make_unit(current_workaround="Manual load balancing")
    options = _build_options(unit)
    workaround_opts = [o for o in options if "Manual load balancing" in o["name"]]
    assert len(workaround_opts) == 1
    assert not workaround_opts[0]["selected"]


def test_build_options_includes_do_nothing() -> None:
    unit = _make_unit()
    options = _build_options(unit)
    do_nothing = [o for o in options if o["name"] == "Do nothing"]
    assert len(do_nothing) == 1
    assert not do_nothing[0]["selected"]


def test_build_options_pros_and_cons() -> None:
    unit = _make_unit()
    options = _build_options(unit)
    for opt in options:
        assert "pros" in opt
        assert "cons" in opt
        assert len(opt["pros"]) > 0
        assert len(opt["cons"]) > 0


# ── Consequences tests ──────────────────────────────────────────────


def test_infer_consequences_with_data() -> None:
    unit = _make_unit()
    consequences = _infer_consequences(unit)
    assert any("3x throughput" in c for c in consequences)
    assert any("infrastructure" in c for c in consequences)


def test_infer_consequences_minimal() -> None:
    unit = MagicMock()
    unit.value_proposition = ""
    unit.domain = ""
    unit.target_users = ""
    consequences = _infer_consequences(unit)
    assert len(consequences) >= 1


# ── Summary tests ────────────────────────────────────────────────────


def test_build_summary() -> None:
    decisions = [
        {"status": STATUS_ACCEPTED, "domain": "infra"},
        {"status": STATUS_ACCEPTED, "domain": "devtools"},
        {"status": STATUS_PROPOSED, "domain": "infra"},
    ]
    summary = _build_summary(decisions)
    assert summary["total"] == 3
    assert summary["status_counts"][STATUS_ACCEPTED] == 2
    assert summary["status_counts"][STATUS_PROPOSED] == 1
    assert "infra" in summary["domains"]
    assert "devtools" in summary["domains"]


def test_build_summary_empty() -> None:
    summary = _build_summary([])
    assert summary["total"] == 0
    assert summary["status_counts"] == {}
    assert summary["domains"] == []


# ── Status validation tests ─────────────────────────────────────────


def test_valid_statuses() -> None:
    assert STATUS_PROPOSED in VALID_STATUSES
    assert STATUS_ACCEPTED in VALID_STATUSES
    assert STATUS_DEPRECATED in VALID_STATUSES
    assert STATUS_SUPERSEDED in VALID_STATUSES


# ── Rendering tests ─────────────────────────────────────────────────


def test_render_markdown_contains_sections() -> None:
    store = _mock_store(units=[_make_unit()])
    report = build_decision_log(store)
    md = render_decision_log_markdown(report)

    assert "# Decision Log" in md
    assert "## Summary" in md
    assert "## Decisions" in md
    assert "DEC-001" in md


def test_render_markdown_decision_details() -> None:
    store = _mock_store(units=[_make_unit()])
    report = build_decision_log(store)
    md = render_decision_log_markdown(report)

    assert "**Status**:" in md
    assert "**Context**:" in md
    assert "**Options Considered**:" in md
    assert "**Rationale**:" in md
    assert "**Consequences**:" in md


def test_render_markdown_empty() -> None:
    store = _mock_store()
    report = build_decision_log(store)
    md = render_decision_log_markdown(report)
    assert "# Decision Log" in md
    assert "No decisions recorded" in md


def test_render_json_valid() -> None:
    store = _mock_store()
    report = build_decision_log(store)
    parsed = json.loads(render_decision_log_json(report))
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND


def test_render_json_roundtrip() -> None:
    store = _mock_store(units=[_make_unit()])
    report = build_decision_log(store)
    parsed = json.loads(render_decision_log_json(report))
    assert len(parsed["decisions"]) == 1
    assert parsed["decisions"][0]["title"] == "New API gateway"


# ── Integration-style tests ──────────────────────────────────────────


def test_full_decision_log() -> None:
    units = [
        _make_unit(
            unit_id="bu-1",
            solution="Microservice migration",
            problem="Monolith scaling issues",
            quality_score=0.9,
            domain="architecture",
        ),
        _make_unit(
            unit_id="bu-2",
            solution="GraphQL API layer",
            problem="REST API complexity",
            quality_score=0.5,
            domain="api",
        ),
    ]
    store = _mock_store(units=units)

    report = build_decision_log(store)
    assert report["decision_count"] == 2

    # First decision should be accepted (quality > 0.7)
    assert report["decisions"][0]["status"] == STATUS_ACCEPTED
    # Second decision should be proposed (quality 0.5)
    assert report["decisions"][1]["status"] == STATUS_PROPOSED

    # Summary should have both domains
    assert "architecture" in report["summary"]["domains"]
    assert "api" in report["summary"]["domains"]

    # Both formats render
    md = render_decision_log_markdown(report)
    assert len(md) > 100
    assert "DEC-001" in md
    assert "DEC-002" in md

    js = render_decision_log_json(report)
    parsed = json.loads(js)
    assert parsed["kind"] == KIND
