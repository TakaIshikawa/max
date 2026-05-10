"""Tests for team charter document export."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.team_charter import (
    SCHEMA_VERSION,
    KIND,
    RESPONSIBLE,
    ACCOUNTABLE,
    CONSULTED,
    INFORMED,
    build_team_charter,
    render_team_charter_json,
    render_team_charter_markdown,
    _derive_mission,
    _define_scope,
    _define_roles,
    _build_raci_matrix,
    _define_communication_norms,
    _define_escalation_paths,
    _define_decision_process,
)
from max.types.signal import Signal, SignalSourceType


# ── Helpers ──────────────────────────────────────────────────────────


def _make_unit(
    *,
    unit_id: str = "bu-001",
    solution: str = "Platform feature",
    domain: str = "devtools",
) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.solution = solution
    unit.domain = domain
    return unit


def _make_signal(
    *,
    signal_id: str = "sig-001",
    title: str = "Signal",
    content: str = "Content",
    tags: list[str] | None = None,
    source_type: SignalSourceType = SignalSourceType.MARKET,
) -> Signal:
    return Signal(
        id=signal_id,
        title=title,
        content=content,
        source_type=source_type,
        source_adapter="test_adapter",
        url="https://example.com",
        tags=tags or [],
    )


def _mock_store(
    units: list | None = None,
    signals: list | None = None,
) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units or []
    store.get_signals.return_value = signals or []
    return store


# ── Schema and structure tests ───────────────────────────────────────


def test_build_team_charter_schema() -> None:
    store = _mock_store()
    result = build_team_charter(store)
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == KIND
    assert "generated_at" in result
    assert "team_name" in result
    assert "mission" in result
    assert "scope" in result
    assert "roles" in result
    assert "raci_matrix" in result
    assert "communication" in result
    assert "escalation_paths" in result
    assert "decision_making" in result


def test_build_team_charter_domain_filter() -> None:
    store = _mock_store()
    build_team_charter(store, domain="security")
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="security")


def test_build_team_charter_custom_team_name() -> None:
    store = _mock_store()
    result = build_team_charter(store, team_name="Platform Team")
    assert result["team_name"] == "Platform Team"


# ── Mission tests ────────────────────────────────────────────────────


def test_derive_mission_with_domains() -> None:
    units = [_make_unit(domain="devtools"), _make_unit(unit_id="bu-2", domain="security")]
    signals = [_make_signal()]
    mission = _derive_mission(units, signals, "Core Team")
    assert "Core Team" in mission
    assert "devtools" in mission or "security" in mission


def test_derive_mission_no_domains() -> None:
    mission = _derive_mission([], [], "Test Team")
    assert "Test Team" in mission
    assert "innovation" in mission.lower()


# ── Scope tests ──────────────────────────────────────────────────────


def test_define_scope_structure() -> None:
    scope = _define_scope([], [])
    assert "in_scope" in scope
    assert "out_of_scope" in scope
    assert len(scope["in_scope"]) > 0
    assert len(scope["out_of_scope"]) > 0


def test_define_scope_includes_domains() -> None:
    units = [_make_unit(domain="analytics")]
    scope = _define_scope(units, [])
    assert any("analytics" in item for item in scope["in_scope"])


def test_define_scope_includes_intelligence() -> None:
    signals = [_make_signal()]
    scope = _define_scope([], signals)
    assert any("intelligence" in item.lower() for item in scope["in_scope"])


# ── Roles tests ──────────────────────────────────────────────────────


def test_define_roles_base() -> None:
    roles = _define_roles([])
    titles = {r["title"] for r in roles}
    assert "Product Lead" in titles
    assert "Tech Lead" in titles
    assert "Signal Analyst" in titles


def test_define_roles_with_domains() -> None:
    units = [_make_unit(domain="security")]
    roles = _define_roles(units)
    titles = {r["title"] for r in roles}
    assert "Domain Specialist" in titles


def test_define_roles_have_responsibilities() -> None:
    roles = _define_roles([])
    for role in roles:
        assert "title" in role
        assert "responsibilities" in role
        assert len(role["responsibilities"]) > 0


# ── RACI matrix tests ───────────────────────────────────────────────


def test_build_raci_matrix_structure() -> None:
    raci = _build_raci_matrix([])
    assert "roles" in raci
    assert "activities" in raci
    assert len(raci["roles"]) >= 3
    assert len(raci["activities"]) >= 3


def test_build_raci_matrix_valid_assignments() -> None:
    raci = _build_raci_matrix([])
    valid_values = {RESPONSIBLE, ACCOUNTABLE, CONSULTED, INFORMED}
    for activity in raci["activities"]:
        assert "activity" in activity
        assert "assignments" in activity
        assert len(activity["assignments"]) == len(raci["roles"])
        for assignment in activity["assignments"]:
            assert assignment in valid_values


def test_build_raci_matrix_with_domain_specialist() -> None:
    units = [_make_unit(domain="security")]
    raci = _build_raci_matrix(units)
    assert "Domain Specialist" in raci["roles"]
    for activity in raci["activities"]:
        assert len(activity["assignments"]) == len(raci["roles"])


def test_build_raci_matrix_activities() -> None:
    raci = _build_raci_matrix([])
    activity_names = {a["activity"] for a in raci["activities"]}
    assert "Signal Collection" in activity_names
    assert "Unit Prioritization" in activity_names
    assert "Architecture Design" in activity_names


# ── Communication norms tests ────────────────────────────────────────


def test_define_communication_norms_structure() -> None:
    comm = _define_communication_norms([])
    assert "channels" in comm
    assert "meetings" in comm
    assert len(comm["channels"]) > 0
    assert len(comm["meetings"]) > 0


def test_define_communication_norms_with_signals() -> None:
    signals = [_make_signal()]
    comm = _define_communication_norms(signals)
    meeting_names = {m["name"] for m in comm["meetings"]}
    assert "Signal Review" in meeting_names


def test_define_communication_channels_have_purpose() -> None:
    comm = _define_communication_norms([])
    for ch in comm["channels"]:
        assert "name" in ch
        assert "purpose" in ch


def test_define_communication_meetings_have_frequency() -> None:
    comm = _define_communication_norms([])
    for mtg in comm["meetings"]:
        assert "name" in mtg
        assert "frequency" in mtg
        assert "purpose" in mtg


# ── Escalation and decision tests ────────────────────────────────────


def test_define_escalation_paths() -> None:
    paths = _define_escalation_paths()
    assert len(paths) >= 3
    for path in paths:
        assert "level" in path
        assert "action" in path


def test_define_decision_process() -> None:
    dm = _define_decision_process()
    assert "model" in dm
    assert "steps" in dm
    assert len(dm["steps"]) >= 3


# ── Rendering tests ─────────────────────────────────────────────────


def test_render_markdown_contains_sections() -> None:
    store = _mock_store(
        units=[_make_unit()],
        signals=[_make_signal()],
    )
    report = build_team_charter(store)
    md = render_team_charter_markdown(report)

    assert "# Team Charter" in md
    assert "## Mission Statement" in md
    assert "## Scope" in md
    assert "## Roles & Responsibilities" in md
    assert "## RACI Matrix" in md
    assert "## Communication Norms" in md
    assert "## Escalation Paths" in md
    assert "## Decision-Making Process" in md


def test_render_markdown_raci_table() -> None:
    store = _mock_store(units=[_make_unit()])
    report = build_team_charter(store)
    md = render_team_charter_markdown(report)
    assert "| Activity |" in md
    assert "Product Lead" in md


def test_render_markdown_empty() -> None:
    store = _mock_store()
    report = build_team_charter(store)
    md = render_team_charter_markdown(report)
    assert "# Team Charter" in md


def test_render_json_valid() -> None:
    store = _mock_store()
    report = build_team_charter(store)
    parsed = json.loads(render_team_charter_json(report))
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND


def test_render_json_roundtrip() -> None:
    store = _mock_store(
        units=[_make_unit()],
        signals=[_make_signal()],
    )
    report = build_team_charter(store)
    parsed = json.loads(render_team_charter_json(report))
    assert len(parsed["raci_matrix"]["activities"]) >= 3
    assert len(parsed["roles"]) >= 3


# ── Integration-style tests ──────────────────────────────────────────


def test_full_charter_completeness() -> None:
    units = [
        _make_unit(unit_id="bu-1", domain="devtools"),
        _make_unit(unit_id="bu-2", domain="security"),
    ]
    signals = [_make_signal()]
    store = _mock_store(units=units, signals=signals)

    report = build_team_charter(store, team_name="Alpha Team")

    # Mission mentions team name
    assert "Alpha Team" in report["mission"]

    # Scope covers domains
    assert any("devtools" in s or "security" in s for s in report["scope"]["in_scope"])

    # RACI has Domain Specialist
    assert "Domain Specialist" in report["raci_matrix"]["roles"]

    # Communication includes signal review
    meeting_names = {m["name"] for m in report["communication"]["meetings"]}
    assert "Signal Review" in meeting_names

    # Both formats render
    md = render_team_charter_markdown(report)
    assert len(md) > 100
    js = render_team_charter_json(report)
    parsed = json.loads(js)
    assert parsed["kind"] == KIND
