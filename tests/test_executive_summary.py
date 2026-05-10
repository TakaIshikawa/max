"""Tests for executive summary report export."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.executive_summary import (
    SCHEMA_VERSION,
    KIND,
    DETAIL_LEVELS,
    build_executive_summary,
    render_executive_summary_json,
    render_executive_summary_markdown,
    _extract_key_findings,
    _extract_opportunities,
    _extract_risks,
    _extract_actions,
    _build_data_highlights,
    _detail_limit,
)
from max.types.signal import Signal, SignalSourceType


# ── Helpers ──────────────────────────────────────────────────────────


def _make_unit(
    *,
    unit_id: str = "bu-001",
    solution: str = "AI-powered analytics",
    problem: str = "Manual data analysis is slow",
    domain: str = "devtools",
    quality_score: float = 0.8,
    value_proposition: str = "10x faster insights",
    why_now: str = "Market demand for AI tools growing",
) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.solution = solution
    unit.problem = problem
    unit.domain = domain
    unit.quality_score = quality_score
    unit.value_proposition = value_proposition
    unit.why_now = why_now
    return unit


def _make_signal(
    *,
    signal_id: str = "sig-001",
    title: str = "Market Trend",
    content: str = "Growing demand for automation tools",
    tags: list[str] | None = None,
    credibility: float = 0.7,
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
        credibility=credibility,
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


def test_build_executive_summary_schema() -> None:
    store = _mock_store()
    result = build_executive_summary(store)
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == KIND
    assert "generated_at" in result
    assert "key_findings" in result
    assert "market_opportunities" in result
    assert "risk_highlights" in result
    assert "recommended_actions" in result
    assert "data_highlights" in result
    assert result["detail_level"] == "standard"


def test_build_executive_summary_domain_filter() -> None:
    store = _mock_store()
    build_executive_summary(store, domain="security")
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="security")


def test_build_executive_summary_detail_levels() -> None:
    store = _mock_store()
    for level in DETAIL_LEVELS:
        result = build_executive_summary(store, detail_level=level)
        assert result["detail_level"] == level


def test_build_executive_summary_invalid_detail_level() -> None:
    store = _mock_store()
    result = build_executive_summary(store, detail_level="invalid")
    assert result["detail_level"] == "standard"


# ── Detail limit tests ───────────────────────────────────────────────


def test_detail_limit_values() -> None:
    assert _detail_limit("brief") == 3
    assert _detail_limit("standard") == 5
    assert _detail_limit("detailed") == 10


# ── Key findings tests ──────────────────────────────────────────────


def test_extract_key_findings_from_units() -> None:
    units = [_make_unit(), _make_unit(unit_id="bu-002", solution="Real-time monitoring")]
    findings = _extract_key_findings(units, [], "standard")
    assert len(findings) == 2
    titles = {f["title"] for f in findings}
    assert "AI-powered analytics" in titles
    assert "Real-time monitoring" in titles


def test_extract_key_findings_from_signals() -> None:
    signals = [_make_signal(credibility=0.9, title="High cred signal")]
    findings = _extract_key_findings([], signals, "standard")
    assert len(findings) == 1
    assert findings[0]["title"] == "High cred signal"
    assert findings[0]["source"] == "signal"


def test_extract_key_findings_respects_detail_limit() -> None:
    units = [
        _make_unit(unit_id=f"bu-{i}", solution=f"Solution {i}")
        for i in range(20)
    ]
    brief = _extract_key_findings(units, [], "brief")
    standard = _extract_key_findings(units, [], "standard")
    detailed = _extract_key_findings(units, [], "detailed")
    assert len(brief) <= 3
    assert len(standard) <= 5
    assert len(detailed) <= 10


def test_extract_key_findings_sorted_by_quality() -> None:
    units = [
        _make_unit(unit_id="bu-low", solution="Low quality", quality_score=0.2),
        _make_unit(unit_id="bu-high", solution="High quality", quality_score=0.9),
    ]
    findings = _extract_key_findings(units, [], "standard")
    assert findings[0]["title"] == "High quality"


# ── Opportunity extraction tests ─────────────────────────────────────


def test_extract_opportunities_from_units() -> None:
    units = [_make_unit()]
    opps = _extract_opportunities(units, [], "standard")
    assert len(opps) == 1
    assert opps[0]["title"] == "10x faster insights"


def test_extract_opportunities_from_signals() -> None:
    signals = [_make_signal(content="Huge growth opportunity in emerging markets")]
    opps = _extract_opportunities([], signals, "standard")
    assert len(opps) == 1


def test_extract_opportunities_respects_limit() -> None:
    units = [
        _make_unit(unit_id=f"bu-{i}", value_proposition=f"VP {i}")
        for i in range(20)
    ]
    opps = _extract_opportunities(units, [], "brief")
    assert len(opps) <= 3


# ── Risk extraction tests ───────────────────────────────────────────


def test_extract_risks_from_signals() -> None:
    signals = [
        _make_signal(content="Major security risk and threat to compliance"),
    ]
    risks = _extract_risks(signals, "standard")
    assert len(risks) == 1
    assert risks[0]["severity"] in ("high", "medium", "low")


def test_extract_risks_severity_levels() -> None:
    # High: 3+ matching keywords
    high_signal = _make_signal(
        signal_id="high",
        content="Security risk with competitive threat and regulatory compliance issues",
    )
    # Low: 1 matching keyword
    low_signal = _make_signal(
        signal_id="low",
        title="Minor",
        content="There is a small risk involved",
    )
    risks = _extract_risks([high_signal, low_signal], "detailed")
    assert risks[0]["severity"] == "high"
    assert risks[-1]["severity"] == "low"


def test_extract_risks_empty() -> None:
    signals = [_make_signal(content="Everything is going great")]
    risks = _extract_risks(signals, "standard")
    assert risks == []


def test_extract_risks_respects_limit() -> None:
    signals = [
        _make_signal(signal_id=f"sig-{i}", content=f"Risk and threat number {i}")
        for i in range(20)
    ]
    risks = _extract_risks(signals, "brief")
    assert len(risks) <= 3


# ── Action extraction tests ─────────────────────────────────────────


def test_extract_actions_from_units() -> None:
    units = [_make_unit()]
    actions = _extract_actions(units, [], "standard")
    assert len(actions) == 1
    assert "AI-powered analytics" in actions[0]["action"]


def test_extract_actions_from_signals() -> None:
    signals = [_make_signal(content="We should prioritize and invest in automation")]
    actions = _extract_actions([], signals, "standard")
    assert len(actions) == 1


def test_extract_actions_priority_from_quality() -> None:
    units = [
        _make_unit(unit_id="bu-high", quality_score=0.9, solution="High priority"),
        _make_unit(unit_id="bu-low", quality_score=0.3, solution="Low priority"),
    ]
    actions = _extract_actions(units, [], "standard")
    high_action = next(a for a in actions if "High priority" in a["action"])
    low_action = next(a for a in actions if "Low priority" in a["action"])
    assert high_action["priority"] == "high"
    assert low_action["priority"] == "medium"


# ── Data highlights tests ────────────────────────────────────────────


def test_build_data_highlights() -> None:
    units = [
        _make_unit(domain="devtools"),
        _make_unit(unit_id="bu-002", domain="security"),
    ]
    signals = [
        _make_signal(),
        _make_signal(signal_id="sig-002", source_type=SignalSourceType.ARTICLE),
    ]
    highlights = _build_data_highlights(units, signals)
    assert highlights["signal_count"] == 2
    assert highlights["unit_count"] == 2
    assert "devtools" in highlights["top_domains"]
    assert len(highlights["top_sources"]) > 0


def test_build_data_highlights_empty() -> None:
    highlights = _build_data_highlights([], [])
    assert highlights["signal_count"] == 0
    assert highlights["unit_count"] == 0
    assert highlights["top_domains"] == []
    assert highlights["top_sources"] == []


# ── Rendering tests ─────────────────────────────────────────────────


def test_render_markdown_contains_sections() -> None:
    store = _mock_store(
        units=[_make_unit()],
        signals=[_make_signal()],
    )
    report = build_executive_summary(store)
    md = render_executive_summary_markdown(report)

    assert "# Executive Summary" in md
    assert "## Key Findings" in md
    assert "## Market Opportunities" in md
    assert "## Risk Highlights" in md
    assert "## Recommended Actions" in md
    assert "## Data Highlights" in md


def test_render_markdown_empty() -> None:
    store = _mock_store()
    report = build_executive_summary(store)
    md = render_executive_summary_markdown(report)
    assert "# Executive Summary" in md
    assert "No key findings identified" in md


def test_render_markdown_detail_level_shown() -> None:
    store = _mock_store()
    report = build_executive_summary(store, detail_level="brief")
    md = render_executive_summary_markdown(report)
    assert "Detail level: brief" in md


def test_render_json_valid() -> None:
    store = _mock_store()
    report = build_executive_summary(store)
    parsed = json.loads(render_executive_summary_json(report))
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND


def test_render_json_roundtrip() -> None:
    store = _mock_store(
        units=[_make_unit()],
        signals=[_make_signal()],
    )
    report = build_executive_summary(store)
    parsed = json.loads(render_executive_summary_json(report))
    assert len(parsed["key_findings"]) >= 1
    assert parsed["detail_level"] == "standard"


def test_render_markdown_with_risks() -> None:
    store = _mock_store(
        signals=[_make_signal(content="Major security risk and threat to compliance")],
    )
    report = build_executive_summary(store)
    md = render_executive_summary_markdown(report)
    assert "Risk Highlights" in md


def test_render_markdown_with_actions() -> None:
    store = _mock_store(
        units=[_make_unit()],
    )
    report = build_executive_summary(store)
    md = render_executive_summary_markdown(report)
    assert "Recommended Actions" in md
    assert "1." in md  # Numbered actions


# ── Integration-style tests ──────────────────────────────────────────


def test_full_summary_with_all_data() -> None:
    units = [
        _make_unit(unit_id="bu-001", solution="Platform A", quality_score=0.9),
        _make_unit(unit_id="bu-002", solution="Platform B", quality_score=0.5),
    ]
    signals = [
        _make_signal(
            signal_id="sig-001",
            title="Growth Signal",
            content="Strong growth opportunity in emerging market adoption trends",
            credibility=0.9,
        ),
        _make_signal(
            signal_id="sig-002",
            title="Risk Signal",
            content="Competitive threat from disruptive security risk and regulatory compliance",
            credibility=0.6,
        ),
        _make_signal(
            signal_id="sig-003",
            title="Action Signal",
            content="We should invest and prioritize building automation",
            credibility=0.8,
        ),
    ]
    store = _mock_store(units=units, signals=signals)

    report = build_executive_summary(store, detail_level="detailed")
    assert report["detail_level"] == "detailed"
    assert len(report["key_findings"]) > 0
    assert len(report["market_opportunities"]) > 0
    assert len(report["risk_highlights"]) > 0
    assert len(report["recommended_actions"]) > 0
    assert report["data_highlights"]["signal_count"] == 3
    assert report["data_highlights"]["unit_count"] == 2

    # Verify both formats render
    md = render_executive_summary_markdown(report)
    assert len(md) > 100

    js = render_executive_summary_json(report)
    parsed = json.loads(js)
    assert parsed["kind"] == KIND
