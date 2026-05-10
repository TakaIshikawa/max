"""Financial projections export — revenue and cost forecast documents.

Builds projection models with MRR/ARR calculations, churn assumptions,
and cost scaling curves.  Exports P&L projections, unit economics,
and breakeven analysis.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.financial_projections.v1"
KIND = "max.financial_projections"

# ── Default assumptions ──────────────────────────────────────────────

_DEFAULT_MONTHS = 24
_DEFAULT_MONTHLY_CHURN = 0.05  # 5 %
_DEFAULT_MONTHLY_GROWTH = 0.10  # 10 %
_DEFAULT_ARPU = 50.0  # average revenue per user
_DEFAULT_CAC = 200.0  # customer acquisition cost
_DEFAULT_GROSS_MARGIN = 0.80  # 80 %
_DEFAULT_FIXED_COSTS = 10_000.0  # monthly fixed costs


# ── Public API ───────────────────────────────────────────────────────


def build_financial_projections(
    *,
    starting_customers: int,
    monthly_growth_rate: float = _DEFAULT_MONTHLY_GROWTH,
    monthly_churn_rate: float = _DEFAULT_MONTHLY_CHURN,
    arpu: float = _DEFAULT_ARPU,
    cac: float = _DEFAULT_CAC,
    gross_margin: float = _DEFAULT_GROSS_MARGIN,
    fixed_costs: float = _DEFAULT_FIXED_COSTS,
    months: int = _DEFAULT_MONTHS,
) -> dict[str, Any]:
    """Build financial projections report.

    Args:
        starting_customers: Number of customers at month 0.
        monthly_growth_rate: Fractional monthly customer growth rate.
        monthly_churn_rate: Fractional monthly customer churn rate.
        arpu: Average revenue per user per month.
        cac: Customer acquisition cost.
        gross_margin: Gross margin as a fraction (0-1).
        fixed_costs: Monthly fixed operating costs.
        months: Number of months to project.

    Returns:
        Dict with monthly projections, unit economics, P&L, and
        breakeven analysis.

    Raises:
        ValueError: For invalid parameter values.
    """
    _validate_inputs(
        starting_customers=starting_customers,
        monthly_growth_rate=monthly_growth_rate,
        monthly_churn_rate=monthly_churn_rate,
        arpu=arpu,
        cac=cac,
        gross_margin=gross_margin,
        fixed_costs=fixed_costs,
        months=months,
    )

    monthly = _build_monthly_projections(
        starting_customers=starting_customers,
        monthly_growth_rate=monthly_growth_rate,
        monthly_churn_rate=monthly_churn_rate,
        arpu=arpu,
        cac=cac,
        gross_margin=gross_margin,
        fixed_costs=fixed_costs,
        months=months,
    )

    unit_economics = _compute_unit_economics(
        arpu=arpu,
        cac=cac,
        monthly_churn_rate=monthly_churn_rate,
        gross_margin=gross_margin,
    )

    pnl = _build_pnl(monthly, fixed_costs)

    breakeven = _compute_breakeven(monthly)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "financial_projections",
        },
        "assumptions": {
            "starting_customers": starting_customers,
            "monthly_growth_rate": monthly_growth_rate,
            "monthly_churn_rate": monthly_churn_rate,
            "arpu": arpu,
            "cac": cac,
            "gross_margin": gross_margin,
            "fixed_costs": fixed_costs,
            "months": months,
        },
        "monthly_projections": monthly,
        "unit_economics": unit_economics,
        "pnl_summary": pnl,
        "breakeven": breakeven,
    }


def render_financial_projections_markdown(report: dict[str, Any]) -> str:
    """Render financial projections report as Markdown."""
    lines = [
        "# Financial Projections",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
    ]

    # Assumptions
    a = report["assumptions"]
    lines.extend([
        "## Assumptions",
        "",
        f"- Starting customers: {a['starting_customers']:,}",
        f"- Monthly growth rate: {a['monthly_growth_rate']:.1%}",
        f"- Monthly churn rate: {a['monthly_churn_rate']:.1%}",
        f"- ARPU: ${a['arpu']:,.2f}",
        f"- CAC: ${a['cac']:,.2f}",
        f"- Gross margin: {a['gross_margin']:.0%}",
        f"- Fixed costs: ${a['fixed_costs']:,.2f}/mo",
        f"- Projection horizon: {a['months']} months",
        "",
    ])

    # Unit economics
    ue = report["unit_economics"]
    lines.extend([
        "## Unit Economics",
        "",
        f"- **LTV**: ${ue['ltv']:,.2f}",
        f"- **LTV/CAC ratio**: {ue['ltv_cac_ratio']:.2f}x",
        f"- **Payback period**: {ue['payback_months']:.1f} months",
        f"- **Gross profit/user/mo**: ${ue['gross_profit_per_user']:,.2f}",
        "",
    ])

    # Monthly projections table
    monthly = report["monthly_projections"]
    lines.extend([
        "## Monthly Projections",
        "",
        "| Month | Customers | MRR | ARR | New | Churned | Net Cash Flow |",
        "|-------|-----------|-----|-----|-----|---------|---------------|",
    ])
    for m in monthly:
        lines.append(
            f"| {m['month']} | {m['customers']:,} "
            f"| ${m['mrr']:,.0f} | ${m['arr']:,.0f} "
            f"| {m['new_customers']} | {m['churned_customers']} "
            f"| ${m['net_cash_flow']:,.0f} |"
        )
    lines.append("")

    # P&L summary
    pnl = report["pnl_summary"]
    lines.extend([
        "## P&L Summary",
        "",
        f"- Total revenue: ${pnl['total_revenue']:,.0f}",
        f"- Total COGS: ${pnl['total_cogs']:,.0f}",
        f"- Total gross profit: ${pnl['total_gross_profit']:,.0f}",
        f"- Total fixed costs: ${pnl['total_fixed_costs']:,.0f}",
        f"- Total acquisition costs: ${pnl['total_acquisition_costs']:,.0f}",
        f"- Net profit: ${pnl['net_profit']:,.0f}",
        "",
    ])

    # Breakeven
    be = report["breakeven"]
    lines.extend([
        "## Breakeven Analysis",
        "",
    ])
    if be["breakeven_month"] is not None:
        lines.append(
            f"- Breakeven reached at **month {be['breakeven_month']}** "
            f"with {be['breakeven_customers']:,} customers"
        )
    else:
        lines.append("- Breakeven **not reached** within projection horizon")
    lines.extend([
        f"- Cumulative cash flow at end: ${be['cumulative_cash_flow']:,.0f}",
        "",
    ])

    return "\n".join(lines).rstrip() + "\n"


def render_financial_projections_json(report: dict[str, Any]) -> str:
    """Render financial projections report as formatted JSON."""
    return json.dumps(report, indent=2, default=str)


# ── Internal helpers ─────────────────────────────────────────────────


def _validate_inputs(
    *,
    starting_customers: int,
    monthly_growth_rate: float,
    monthly_churn_rate: float,
    arpu: float,
    cac: float,
    gross_margin: float,
    fixed_costs: float,
    months: int,
) -> None:
    """Validate projection input parameters."""
    if starting_customers < 0:
        raise ValueError("starting_customers must be >= 0")
    if not 0.0 <= monthly_churn_rate <= 1.0:
        raise ValueError("monthly_churn_rate must be between 0 and 1")
    if monthly_growth_rate < 0.0:
        raise ValueError("monthly_growth_rate must be >= 0")
    if arpu < 0:
        raise ValueError("arpu must be >= 0")
    if cac < 0:
        raise ValueError("cac must be >= 0")
    if not 0.0 <= gross_margin <= 1.0:
        raise ValueError("gross_margin must be between 0 and 1")
    if fixed_costs < 0:
        raise ValueError("fixed_costs must be >= 0")
    if months < 1:
        raise ValueError("months must be >= 1")


def _build_monthly_projections(
    *,
    starting_customers: int,
    monthly_growth_rate: float,
    monthly_churn_rate: float,
    arpu: float,
    cac: float,
    gross_margin: float,
    fixed_costs: float,
    months: int,
) -> list[dict[str, Any]]:
    """Generate month-by-month projections."""
    rows: list[dict[str, Any]] = []
    customers = float(starting_customers)

    for month in range(1, months + 1):
        new_customers = int(math.floor(customers * monthly_growth_rate))
        churned_customers = int(math.floor(customers * monthly_churn_rate))
        customers = customers + new_customers - churned_customers

        mrr = customers * arpu
        arr = mrr * 12
        revenue = mrr
        cogs = revenue * (1 - gross_margin)
        gross_profit = revenue - cogs
        acquisition_cost = new_customers * cac
        net_cash_flow = gross_profit - fixed_costs - acquisition_cost

        rows.append({
            "month": month,
            "customers": int(customers),
            "new_customers": new_customers,
            "churned_customers": churned_customers,
            "mrr": round(mrr, 2),
            "arr": round(arr, 2),
            "revenue": round(revenue, 2),
            "cogs": round(cogs, 2),
            "gross_profit": round(gross_profit, 2),
            "acquisition_cost": round(acquisition_cost, 2),
            "net_cash_flow": round(net_cash_flow, 2),
        })

    return rows


def _compute_unit_economics(
    *,
    arpu: float,
    cac: float,
    monthly_churn_rate: float,
    gross_margin: float,
) -> dict[str, Any]:
    """Compute unit economics: LTV, LTV/CAC, payback period."""
    gross_profit_per_user = arpu * gross_margin

    if monthly_churn_rate > 0:
        avg_lifetime_months = 1.0 / monthly_churn_rate
    else:
        avg_lifetime_months = float("inf")

    ltv = gross_profit_per_user * avg_lifetime_months

    ltv_cac_ratio = ltv / cac if cac > 0 else float("inf")

    if gross_profit_per_user > 0:
        payback_months = cac / gross_profit_per_user
    else:
        payback_months = float("inf")

    return {
        "arpu": arpu,
        "gross_profit_per_user": round(gross_profit_per_user, 2),
        "avg_lifetime_months": round(avg_lifetime_months, 2) if math.isfinite(avg_lifetime_months) else None,
        "ltv": round(ltv, 2) if math.isfinite(ltv) else None,
        "ltv_cac_ratio": round(ltv_cac_ratio, 2) if math.isfinite(ltv_cac_ratio) else None,
        "payback_months": round(payback_months, 2) if math.isfinite(payback_months) else None,
        "cac": cac,
    }


def _build_pnl(
    monthly: list[dict[str, Any]],
    fixed_costs: float,
) -> dict[str, Any]:
    """Build P&L summary from monthly projections."""
    total_revenue = sum(m["revenue"] for m in monthly)
    total_cogs = sum(m["cogs"] for m in monthly)
    total_gross_profit = sum(m["gross_profit"] for m in monthly)
    total_fixed = fixed_costs * len(monthly)
    total_acq = sum(m["acquisition_cost"] for m in monthly)
    net_profit = total_gross_profit - total_fixed - total_acq

    return {
        "total_revenue": round(total_revenue, 2),
        "total_cogs": round(total_cogs, 2),
        "total_gross_profit": round(total_gross_profit, 2),
        "total_fixed_costs": round(total_fixed, 2),
        "total_acquisition_costs": round(total_acq, 2),
        "net_profit": round(net_profit, 2),
    }


def _compute_breakeven(
    monthly: list[dict[str, Any]],
) -> dict[str, Any]:
    """Find the first month where cumulative cash flow turns positive."""
    cumulative = 0.0
    breakeven_month: int | None = None
    breakeven_customers: int | None = None

    for m in monthly:
        cumulative += m["net_cash_flow"]
        if breakeven_month is None and cumulative > 0:
            breakeven_month = m["month"]
            breakeven_customers = m["customers"]

    return {
        "breakeven_month": breakeven_month,
        "breakeven_customers": breakeven_customers,
        "cumulative_cash_flow": round(cumulative, 2),
    }
