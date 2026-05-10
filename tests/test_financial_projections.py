"""Tests for financial projections export module."""

from __future__ import annotations

import json

import pytest

from max.exports.financial_projections import (
    build_financial_projections,
    render_financial_projections_json,
    render_financial_projections_markdown,
)


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def basic_report() -> dict:
    return build_financial_projections(
        starting_customers=100,
        monthly_growth_rate=0.10,
        monthly_churn_rate=0.05,
        arpu=50.0,
        cac=200.0,
        gross_margin=0.80,
        fixed_costs=10_000.0,
        months=12,
    )


# ── Schema / metadata ───────────────────────────────────────────────


def test_schema_metadata(basic_report: dict) -> None:
    assert basic_report["schema_version"] == "max.financial_projections.v1"
    assert basic_report["kind"] == "max.financial_projections"
    assert "generated_at" in basic_report
    assert basic_report["source"]["entity_type"] == "financial_projections"


def test_assumptions_stored(basic_report: dict) -> None:
    a = basic_report["assumptions"]
    assert a["starting_customers"] == 100
    assert a["monthly_growth_rate"] == 0.10
    assert a["monthly_churn_rate"] == 0.05
    assert a["arpu"] == 50.0
    assert a["cac"] == 200.0
    assert a["months"] == 12


# ── MRR / ARR calculations ──────────────────────────────────────────


def test_mrr_equals_customers_times_arpu(basic_report: dict) -> None:
    for m in basic_report["monthly_projections"]:
        expected_mrr = m["customers"] * 50.0
        assert m["mrr"] == pytest.approx(expected_mrr, abs=0.01)


def test_arr_equals_mrr_times_twelve(basic_report: dict) -> None:
    for m in basic_report["monthly_projections"]:
        assert m["arr"] == pytest.approx(m["mrr"] * 12, abs=0.01)


def test_mrr_grows_over_time(basic_report: dict) -> None:
    projections = basic_report["monthly_projections"]
    # With net positive growth (10% growth - 5% churn), MRR should increase
    assert projections[-1]["mrr"] > projections[0]["mrr"]


# ── Churn-adjusted growth ───────────────────────────────────────────


def test_churn_reduces_customers() -> None:
    report = build_financial_projections(
        starting_customers=100,
        monthly_growth_rate=0.0,
        monthly_churn_rate=0.10,
        arpu=50.0,
        months=6,
    )
    projections = report["monthly_projections"]
    # With no growth and 10% churn, customers decline
    assert projections[-1]["customers"] < 100


def test_zero_churn_only_growth() -> None:
    report = build_financial_projections(
        starting_customers=100,
        monthly_growth_rate=0.10,
        monthly_churn_rate=0.0,
        arpu=50.0,
        months=6,
    )
    projections = report["monthly_projections"]
    # No churn => churned_customers always 0
    for m in projections:
        assert m["churned_customers"] == 0
    assert projections[-1]["customers"] > 100


def test_new_and_churned_customers_counted(basic_report: dict) -> None:
    for m in basic_report["monthly_projections"]:
        assert m["new_customers"] >= 0
        assert m["churned_customers"] >= 0


# ── Unit economics ──────────────────────────────────────────────────


def test_ltv_calculation(basic_report: dict) -> None:
    ue = basic_report["unit_economics"]
    # LTV = gross_profit_per_user * avg_lifetime
    # gross_profit_per_user = 50 * 0.80 = 40
    # avg_lifetime = 1 / 0.05 = 20 months
    # LTV = 40 * 20 = 800
    assert ue["ltv"] == pytest.approx(800.0, abs=0.01)


def test_ltv_cac_ratio(basic_report: dict) -> None:
    ue = basic_report["unit_economics"]
    # LTV = 800, CAC = 200 => ratio = 4.0
    assert ue["ltv_cac_ratio"] == pytest.approx(4.0, abs=0.01)


def test_payback_period(basic_report: dict) -> None:
    ue = basic_report["unit_economics"]
    # payback = CAC / gross_profit_per_user = 200 / 40 = 5 months
    assert ue["payback_months"] == pytest.approx(5.0, abs=0.01)


def test_gross_profit_per_user(basic_report: dict) -> None:
    ue = basic_report["unit_economics"]
    assert ue["gross_profit_per_user"] == pytest.approx(40.0, abs=0.01)


def test_unit_economics_zero_churn() -> None:
    report = build_financial_projections(
        starting_customers=100,
        monthly_churn_rate=0.0,
        arpu=50.0,
        cac=200.0,
        gross_margin=0.80,
        months=6,
    )
    ue = report["unit_economics"]
    # Infinite lifetime => LTV and LTV/CAC should be None (infinity)
    assert ue["avg_lifetime_months"] is None
    assert ue["ltv"] is None
    assert ue["ltv_cac_ratio"] is None


def test_unit_economics_zero_cac() -> None:
    report = build_financial_projections(
        starting_customers=100,
        monthly_churn_rate=0.05,
        arpu=50.0,
        cac=0.0,
        gross_margin=0.80,
        months=6,
    )
    ue = report["unit_economics"]
    assert ue["ltv_cac_ratio"] is None  # inf
    assert ue["payback_months"] == pytest.approx(0.0, abs=0.01)


# ── P&L ─────────────────────────────────────────────────────────────


def test_pnl_total_revenue(basic_report: dict) -> None:
    pnl = basic_report["pnl_summary"]
    expected = sum(m["revenue"] for m in basic_report["monthly_projections"])
    assert pnl["total_revenue"] == pytest.approx(expected, abs=1.0)


def test_pnl_gross_profit(basic_report: dict) -> None:
    pnl = basic_report["pnl_summary"]
    assert pnl["total_gross_profit"] == pytest.approx(
        pnl["total_revenue"] - pnl["total_cogs"], abs=1.0
    )


def test_pnl_net_profit(basic_report: dict) -> None:
    pnl = basic_report["pnl_summary"]
    expected = (
        pnl["total_gross_profit"]
        - pnl["total_fixed_costs"]
        - pnl["total_acquisition_costs"]
    )
    assert pnl["net_profit"] == pytest.approx(expected, abs=1.0)


def test_pnl_fixed_costs_match_months(basic_report: dict) -> None:
    pnl = basic_report["pnl_summary"]
    assert pnl["total_fixed_costs"] == pytest.approx(10_000.0 * 12, abs=0.01)


# ── Breakeven analysis ──────────────────────────────────────────────


def test_breakeven_reached() -> None:
    report = build_financial_projections(
        starting_customers=500,
        monthly_growth_rate=0.10,
        monthly_churn_rate=0.02,
        arpu=100.0,
        cac=50.0,
        fixed_costs=5_000.0,
        months=24,
    )
    be = report["breakeven"]
    assert be["breakeven_month"] is not None
    assert be["breakeven_month"] >= 1
    assert be["breakeven_customers"] is not None


def test_breakeven_not_reached() -> None:
    report = build_financial_projections(
        starting_customers=10,
        monthly_growth_rate=0.01,
        monthly_churn_rate=0.05,
        arpu=10.0,
        cac=500.0,
        fixed_costs=50_000.0,
        months=12,
    )
    be = report["breakeven"]
    assert be["breakeven_month"] is None
    assert be["cumulative_cash_flow"] < 0


def test_breakeven_cumulative_cash_flow(basic_report: dict) -> None:
    be = basic_report["breakeven"]
    expected = sum(m["net_cash_flow"] for m in basic_report["monthly_projections"])
    assert be["cumulative_cash_flow"] == pytest.approx(expected, abs=1.0)


# ── Configurable time horizons ───────────────────────────────────────


def test_custom_months() -> None:
    report = build_financial_projections(
        starting_customers=100,
        months=6,
    )
    assert len(report["monthly_projections"]) == 6


def test_single_month() -> None:
    report = build_financial_projections(
        starting_customers=100,
        months=1,
    )
    assert len(report["monthly_projections"]) == 1


# ── Rendering ────────────────────────────────────────────────────────


def test_render_markdown_contains_sections(basic_report: dict) -> None:
    md = render_financial_projections_markdown(basic_report)
    assert "# Financial Projections" in md
    assert "## Assumptions" in md
    assert "## Unit Economics" in md
    assert "## Monthly Projections" in md
    assert "## P&L Summary" in md
    assert "## Breakeven Analysis" in md


def test_render_markdown_ends_with_newline(basic_report: dict) -> None:
    md = render_financial_projections_markdown(basic_report)
    assert md.endswith("\n")
    assert not md.endswith("\n\n")


def test_render_json_valid(basic_report: dict) -> None:
    raw = render_financial_projections_json(basic_report)
    parsed = json.loads(raw)
    assert parsed["schema_version"] == "max.financial_projections.v1"
    assert "monthly_projections" in parsed


# ── Validation / edge cases ──────────────────────────────────────────


def test_negative_starting_customers_rejected() -> None:
    with pytest.raises(ValueError, match="starting_customers"):
        build_financial_projections(starting_customers=-1)


def test_invalid_churn_rate_rejected() -> None:
    with pytest.raises(ValueError, match="monthly_churn_rate"):
        build_financial_projections(starting_customers=100, monthly_churn_rate=1.5)


def test_invalid_growth_rate_rejected() -> None:
    with pytest.raises(ValueError, match="monthly_growth_rate"):
        build_financial_projections(starting_customers=100, monthly_growth_rate=-0.1)


def test_invalid_months_rejected() -> None:
    with pytest.raises(ValueError, match="months"):
        build_financial_projections(starting_customers=100, months=0)


def test_invalid_gross_margin_rejected() -> None:
    with pytest.raises(ValueError, match="gross_margin"):
        build_financial_projections(starting_customers=100, gross_margin=1.5)


def test_zero_customers() -> None:
    report = build_financial_projections(starting_customers=0, months=6)
    for m in report["monthly_projections"]:
        assert m["customers"] == 0
        assert m["mrr"] == 0.0


def test_projection_accuracy_known_scenario() -> None:
    """Verify projection math with a hand-calculated scenario."""
    report = build_financial_projections(
        starting_customers=100,
        monthly_growth_rate=0.10,
        monthly_churn_rate=0.0,
        arpu=100.0,
        cac=0.0,
        gross_margin=1.0,
        fixed_costs=0.0,
        months=1,
    )
    m = report["monthly_projections"][0]
    # 10% growth of 100 = 10 new, 0 churned => 110 customers
    assert m["customers"] == 110
    assert m["new_customers"] == 10
    assert m["churned_customers"] == 0
    assert m["mrr"] == pytest.approx(11_000.0, abs=0.01)
    assert m["arr"] == pytest.approx(132_000.0, abs=0.01)
