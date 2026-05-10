"""Tests for market sizing analysis export."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.market_sizing import (
    SCHEMA_VERSION,
    KIND,
    build_market_sizing,
    render_market_sizing_json,
    render_market_sizing_markdown,
    _segment_market,
    _estimate_top_down,
    _estimate_bottom_up,
    _calculate_confidence,
    _infer_growth_rate,
    _collect_data_sources,
)
from max.types.signal import Signal, SignalSourceType


# ── Helpers ──────────────────────────────────────────────────────────


def _make_unit(
    *,
    unit_id: str = "bu-001",
    domain: str = "devtools",
    solution: str = "Automated testing",
    evidence_signals: list[str] | None = None,
) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.domain = domain
    unit.category = "application"
    unit.solution = solution
    unit.target_users = "both"
    unit.evidence_signals = evidence_signals or []
    return unit


def _make_signal(
    *,
    signal_id: str = "sig-001",
    title: str = "Test Signal",
    content: str = "Signal content",
    source_type: SignalSourceType = SignalSourceType.MARKET,
    tags: list[str] | None = None,
    source_adapter: str = "test_adapter",
) -> Signal:
    return Signal(
        id=signal_id,
        title=title,
        content=content,
        source_type=source_type,
        source_adapter=source_adapter,
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


def test_build_market_sizing_schema() -> None:
    store = _mock_store()
    result = build_market_sizing(store)
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == KIND
    assert "generated_at" in result
    assert "sizing" in result
    assert "growth_projections" in result
    assert "confidence" in result


def test_build_market_sizing_has_tam_sam_som() -> None:
    signals = [_make_signal(signal_id=f"sig-{i}") for i in range(10)]
    store = _mock_store(signals=signals)
    result = build_market_sizing(store)
    sizing = result["sizing"]
    assert "tam" in sizing
    assert "sam" in sizing
    assert "som" in sizing
    assert sizing["tam"] > sizing["sam"] > sizing["som"]


def test_build_market_sizing_top_down_approach() -> None:
    signals = [_make_signal(signal_id=f"sig-{i}") for i in range(5)]
    store = _mock_store(signals=signals)
    result = build_market_sizing(store, approach="top-down")
    assert result["approach"] == "top-down"
    assert result["sizing"]["tam"] > 0


def test_build_market_sizing_bottom_up_approach() -> None:
    units = [_make_unit(unit_id=f"bu-{i}") for i in range(3)]
    signals = [_make_signal(signal_id=f"sig-{i}") for i in range(5)]
    store = _mock_store(units=units, signals=signals)
    result = build_market_sizing(store, approach="bottom-up")
    assert result["approach"] == "bottom-up"
    assert result["sizing"]["tam"] > 0


def test_build_market_sizing_domain_filter() -> None:
    store = _mock_store()
    build_market_sizing(store, domain="ai")
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="ai")


# ── Segment tests ────────────────────────────────────────────────────


def test_segment_market_by_domain() -> None:
    units = [
        _make_unit(unit_id="bu-1", domain="devtools"),
        _make_unit(unit_id="bu-2", domain="devtools"),
        _make_unit(unit_id="bu-3", domain="security"),
    ]
    signals = [_make_signal()]
    segments = _segment_market(units, signals)
    domain_names = {s["name"] for s in segments}
    assert "devtools" in domain_names
    assert "security" in domain_names


def test_segment_market_empty() -> None:
    segments = _segment_market([], [])
    assert len(segments) >= 1
    assert segments[0]["name"] == "general"


# ── Estimation tests ────────────────────────────────────────────────


def test_estimate_top_down_proportional() -> None:
    segments = [
        {"name": "a", "unit_count": 2, "signal_count": 10},
        {"name": "b", "unit_count": 1, "signal_count": 5},
    ]
    signals = [_make_signal(signal_id=f"sig-{i}") for i in range(15)]
    sizing = _estimate_top_down(segments, signals)
    assert sizing["tam"] > 0
    # Segment a should have larger TAM than segment b
    assert segments[0]["segment_tam"] > segments[1]["segment_tam"]


def test_estimate_bottom_up_includes_units() -> None:
    segments = [
        {"name": "a", "unit_count": 5, "signal_count": 3},
    ]
    sizing = _estimate_bottom_up(segments, [])
    assert sizing["tam"] > 0
    assert "segment_tam" in segments[0]


def test_sam_som_ratios() -> None:
    segments = [{"name": "a", "unit_count": 0, "signal_count": 10}]
    signals = [_make_signal(signal_id=f"sig-{i}") for i in range(10)]
    sizing = _estimate_top_down(segments, signals)
    assert sizing["sam"] < sizing["tam"]
    assert sizing["som"] < sizing["sam"]


# ── Growth projection tests ─────────────────────────────────────────


def test_infer_growth_rate_default() -> None:
    rate = _infer_growth_rate([])
    assert rate == 0.12


def test_infer_growth_rate_high_volume() -> None:
    signals = [_make_signal(signal_id=f"sig-{i}") for i in range(200)]
    rate = _infer_growth_rate(signals)
    assert rate > 0.12


def test_growth_projections_5_years() -> None:
    store = _mock_store(signals=[_make_signal()])
    result = build_market_sizing(store)
    projections = result["growth_projections"]["yearly_projections"]
    assert len(projections) == 5
    # Each year should be larger than the previous
    for i in range(1, len(projections)):
        assert projections[i]["tam"] > projections[i - 1]["tam"]


# ── Confidence tests ────────────────────────────────────────────────


def test_confidence_high() -> None:
    signals = [_make_signal(signal_id=f"sig-{i}") for i in range(100)]
    segments = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
    conf = _calculate_confidence(segments, signals)
    assert conf["level"] == "high"
    assert conf["score"] == 0.85


def test_confidence_very_low() -> None:
    conf = _calculate_confidence([{"name": "a"}], [_make_signal()])
    assert conf["level"] == "very low"
    assert conf["score"] == 0.15


def test_confidence_medium() -> None:
    signals = [_make_signal(signal_id=f"sig-{i}") for i in range(50)]
    conf = _calculate_confidence([{"name": "a"}], signals)
    assert conf["level"] == "medium"


# ── Data sources test ────────────────────────────────────────────────


def test_collect_data_sources() -> None:
    signals = [
        _make_signal(signal_id="s1", source_adapter="github_adapter"),
        _make_signal(signal_id="s2", source_adapter="github_adapter"),
        _make_signal(signal_id="s3", source_adapter="stackoverflow_adapter"),
    ]
    sources = _collect_data_sources(signals)
    assert len(sources) == 2
    assert "github_adapter (2 signals)" in sources


# ── Methodology test ────────────────────────────────────────────────


def test_methodology_describes_approach() -> None:
    store = _mock_store(signals=[_make_signal()])
    result = build_market_sizing(store, approach="top-down")
    assert "Top-down" in result["methodology"]

    result_bu = build_market_sizing(store, approach="bottom-up")
    assert "Bottom-up" in result_bu["methodology"]


# ── Rendering tests ─────────────────────────────────────────────────


def test_render_markdown_contains_sections() -> None:
    signals = [_make_signal(signal_id=f"sig-{i}") for i in range(10)]
    store = _mock_store(signals=signals)
    report = build_market_sizing(store)
    md = render_market_sizing_markdown(report)

    assert "# Market Sizing Analysis" in md
    assert "## Market Size Estimates" in md
    assert "TAM" in md
    assert "SAM" in md
    assert "SOM" in md
    assert "## Growth Projections" in md
    assert "## Confidence Assessment" in md
    assert "## Methodology" in md
    assert "## Data Sources" in md


def test_render_markdown_empty() -> None:
    store = _mock_store()
    report = build_market_sizing(store)
    md = render_market_sizing_markdown(report)
    assert "# Market Sizing Analysis" in md


def test_render_json_valid() -> None:
    store = _mock_store(signals=[_make_signal()])
    report = build_market_sizing(store)
    parsed = json.loads(render_market_sizing_json(report))
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert "sizing" in parsed


def test_render_json_roundtrip() -> None:
    units = [_make_unit()]
    signals = [_make_signal()]
    store = _mock_store(units=units, signals=signals)
    report = build_market_sizing(store)
    parsed = json.loads(render_market_sizing_json(report))
    assert parsed["sizing"]["tam"] > 0
    assert len(parsed["growth_projections"]["yearly_projections"]) == 5
