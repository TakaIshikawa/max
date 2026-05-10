"""Tests for pricing model analysis export."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.pricing_model import (
    SCHEMA_VERSION,
    KIND,
    build_pricing_model,
    render_pricing_model_json,
    render_pricing_model_markdown,
    _extract_feature_set,
    _define_tiers,
    _build_feature_gate_matrix,
    _analyze_value_metrics,
    _project_revenue,
)
from max.types.signal import Signal, SignalSourceType


# ── Helpers ──────────────────────────────────────────────────────────


def _make_unit(
    *,
    unit_id: str = "bu-001",
    solution: str = "Automated testing",
    value_proposition: str = "Save time",
    one_liner: str = "Test tool",
    target_users: str = "both",
    domain: str = "devtools",
) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.solution = solution
    unit.value_proposition = value_proposition
    unit.one_liner = one_liner
    unit.target_users = target_users
    unit.domain = domain
    return unit


def _make_signal(
    *,
    signal_id: str = "sig-001",
    title: str = "Signal",
    content: str = "Content",
    source_adapter: str = "test_adapter",
    tags: list[str] | None = None,
) -> Signal:
    return Signal(
        id=signal_id,
        title=title,
        content=content,
        source_type=SignalSourceType.MARKET,
        source_adapter=source_adapter,
        url="https://example.com",
        tags=tags or [],
    )


def _mock_store(
    units: list | None = None,
    signals: list | None = None,
    prior_art: list | None = None,
) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units or []
    store.get_signals.return_value = signals or []
    store.get_prior_art_matches.return_value = prior_art or []
    return store


# ── Schema and structure tests ───────────────────────────────────────


def test_build_pricing_model_schema() -> None:
    store = _mock_store()
    result = build_pricing_model(store)
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == KIND
    assert "generated_at" in result
    assert "tiers" in result
    assert "feature_matrix" in result
    assert "competitor_pricing" in result
    assert "value_metrics" in result
    assert "revenue_projections" in result


def test_build_pricing_model_domain_filter() -> None:
    store = _mock_store()
    build_pricing_model(store, domain="ai")
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="ai")


# ── Tier definition tests ───────────────────────────────────────────


def test_define_tiers_has_four_tiers() -> None:
    features = ["Feature A", "Feature B", "Feature C", "Feature D"]
    tiers = _define_tiers(features)
    assert len(tiers) == 4
    names = [t["name"] for t in tiers]
    assert names == ["Free", "Starter", "Pro", "Enterprise"]


def test_define_tiers_price_ordering() -> None:
    tiers = _define_tiers(["A", "B", "C", "D"])
    prices = [t["price"] for t in tiers]
    assert prices[0] == 0  # Free
    assert prices[1] < prices[2] < prices[3]


def test_define_tiers_enterprise_includes_all() -> None:
    features = ["A", "B", "C", "D", "E"]
    tiers = _define_tiers(features)
    enterprise = tiers[-1]
    assert set(features).issubset(set(enterprise["features"]))


def test_define_tiers_empty_features() -> None:
    tiers = _define_tiers([])
    assert len(tiers) == 4
    # Should have defaults
    assert len(tiers[0]["features"]) >= 1


def test_tier_has_required_fields() -> None:
    tiers = _define_tiers(["F1"])
    for tier in tiers:
        assert "name" in tier
        assert "price" in tier
        assert "description" in tier
        assert "features" in tier
        assert "target_segment" in tier


# ── Feature extraction tests ────────────────────────────────────────


def test_extract_feature_set() -> None:
    units = [
        _make_unit(solution="Auto deploy", value_proposition="Fast deploys", one_liner="Deploy tool"),
        _make_unit(solution="Auto test", value_proposition="Fast deploys", one_liner="Test tool"),
    ]
    features = _extract_feature_set(units)
    assert "Auto deploy" in features
    assert "Auto test" in features
    # "Fast deploys" appears twice but should be deduped
    assert features.count("Fast deploys") == 1


# ── Feature gate matrix tests ───────────────────────────────────────


def test_feature_gate_matrix_structure() -> None:
    tiers = _define_tiers(["A", "B", "C", "D"])
    matrix = _build_feature_gate_matrix(tiers)
    assert "tier_names" in matrix
    assert "features" in matrix
    assert len(matrix["tier_names"]) == 4


def test_feature_gate_matrix_availability() -> None:
    tiers = _define_tiers(["A", "B", "C", "D"])
    matrix = _build_feature_gate_matrix(tiers)
    # Each feature row should have availability for each tier
    for row in matrix["features"]:
        assert len(row["availability"]) == 4
        assert all(a in ("Yes", "—") for a in row["availability"])


# ── Value metrics tests ─────────────────────────────────────────────


def test_value_metrics_agents() -> None:
    units = [_make_unit(target_users="agents")]
    metrics = _analyze_value_metrics(units, [])
    metric_names = [m["metric"] for m in metrics]
    assert "API calls" in metric_names


def test_value_metrics_humans() -> None:
    units = [_make_unit(target_users="humans")]
    metrics = _analyze_value_metrics(units, [])
    metric_names = [m["metric"] for m in metrics]
    assert "Seats" in metric_names


def test_value_metrics_high_volume() -> None:
    signals = [_make_signal(signal_id=f"sig-{i}") for i in range(60)]
    metrics = _analyze_value_metrics([], signals)
    metric_names = [m["metric"] for m in metrics]
    assert "Data volume" in metric_names


def test_value_metrics_empty_fallback() -> None:
    metrics = _analyze_value_metrics([], [])
    assert len(metrics) >= 1
    assert metrics[0]["metric"] == "Flat rate"


# ── Revenue projection tests ────────────────────────────────────────


def test_project_revenue_structure() -> None:
    tiers = _define_tiers(["A"])
    signals = [_make_signal()]
    rev = _project_revenue(tiers, signals)
    assert "estimated_users" in rev
    assert "tier_revenue" in rev
    assert "total_mrr" in rev
    assert "total_arr" in rev
    assert len(rev["tier_revenue"]) == 4


def test_project_revenue_arr_is_12x_mrr() -> None:
    tiers = _define_tiers(["A"])
    rev = _project_revenue(tiers, [_make_signal()])
    assert rev["total_arr"] == rev["total_mrr"] * 12


def test_project_revenue_free_tier_zero_mrr() -> None:
    tiers = _define_tiers(["A"])
    rev = _project_revenue(tiers, [_make_signal()])
    free_tier = next(t for t in rev["tier_revenue"] if t["tier"] == "Free")
    assert free_tier["mrr"] == 0.0


# ── Competitor pricing tests ────────────────────────────────────────


def test_competitor_pricing_from_prior_art() -> None:
    units = [_make_unit()]
    store = _mock_store(
        units=units,
        prior_art=[
            {"title": "Competitor A", "source": "github", "description": "A tool"},
            {"title": "Competitor B", "source": "npm", "description": "Another tool"},
        ],
    )
    result = build_pricing_model(store)
    assert len(result["competitor_pricing"]) == 2


def test_competitor_pricing_empty() -> None:
    store = _mock_store()
    result = build_pricing_model(store)
    assert result["competitor_pricing"] == []


# ── Rendering tests ─────────────────────────────────────────────────


def test_render_markdown_contains_sections() -> None:
    units = [_make_unit()]
    store = _mock_store(units=units, signals=[_make_signal()])
    report = build_pricing_model(store)
    md = render_pricing_model_markdown(report)

    assert "# Pricing Model Analysis" in md
    assert "## Pricing Tiers" in md
    assert "## Feature Gating Matrix" in md
    assert "## Value Metrics" in md
    assert "## Revenue Projections" in md
    assert "Total MRR" in md
    assert "Total ARR" in md


def test_render_markdown_empty() -> None:
    store = _mock_store()
    report = build_pricing_model(store)
    md = render_pricing_model_markdown(report)
    assert "# Pricing Model Analysis" in md


def test_render_json_valid() -> None:
    store = _mock_store(signals=[_make_signal()])
    report = build_pricing_model(store)
    parsed = json.loads(render_pricing_model_json(report))
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert len(parsed["tiers"]) == 4


def test_render_json_roundtrip() -> None:
    units = [_make_unit()]
    store = _mock_store(units=units, signals=[_make_signal()])
    report = build_pricing_model(store)
    parsed = json.loads(render_pricing_model_json(report))
    assert parsed["revenue_projections"]["total_arr"] > 0
