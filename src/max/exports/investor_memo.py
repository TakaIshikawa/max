"""Investor memo export — concise investment memoranda.

Compiles market opportunity, competitive landscape, traction metrics,
and team overview into a structured investor-ready document.  Exports
to markdown and JSON formats with executive summary.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.investor_memo.v1"
KIND = "max.investor_memo"


# ── Public API ───────────────────────────────────────────────────────


def build_investor_memo(
    *,
    company_name: str,
    tagline: str = "",
    market_opportunity: dict[str, Any] | None = None,
    competitive_landscape: list[dict[str, Any]] | None = None,
    traction: dict[str, Any] | None = None,
    team: list[dict[str, str]] | None = None,
    ask_amount: float | None = None,
    use_of_funds: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build an investor memo document.

    Args:
        company_name: Name of the company.
        tagline: One-line company description.
        market_opportunity: Dict with 'tam', 'sam', 'som' and optional
            'description' keys (values in dollars).
        competitive_landscape: List of competitor dicts with 'name',
            'description', and optional 'differentiator' keys.
        traction: Dict with numeric KPI keys (e.g. 'mrr', 'arr',
            'customers', 'growth_rate').
        team: List of dicts with 'name', 'role', and optional 'bio'.
        ask_amount: Fundraise amount in dollars.
        use_of_funds: List of dicts with 'category' and 'percentage'.

    Returns:
        Dict with structured memo sections and executive summary.

    Raises:
        ValueError: If required data is missing.
    """
    _validate_inputs(company_name=company_name, use_of_funds=use_of_funds)

    executive_summary = _build_executive_summary(
        company_name, tagline, market_opportunity, traction, ask_amount,
    )
    market = _build_market_section(market_opportunity)
    competition = _build_competitive_section(competitive_landscape)
    traction_section = _build_traction_section(traction)
    team_section = _build_team_section(team)
    funding = _build_funding_section(ask_amount, use_of_funds)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "investor_memo",
        },
        "company_name": company_name,
        "tagline": tagline,
        "executive_summary": executive_summary,
        "market_opportunity": market,
        "competitive_landscape": competition,
        "traction": traction_section,
        "team": team_section,
        "funding": funding,
    }


def render_investor_memo_markdown(report: dict[str, Any]) -> str:
    """Render investor memo as Markdown."""
    lines = [
        f"# Investor Memo: {report['company_name']}",
        "",
    ]
    if report["tagline"]:
        lines.extend([f"*{report['tagline']}*", ""])

    lines.extend([
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
    ])

    # Executive summary
    es = report["executive_summary"]
    lines.extend(["## Executive Summary", "", es["text"], ""])

    # Market opportunity
    mkt = report["market_opportunity"]
    lines.extend(["## Market Opportunity", ""])
    if mkt["description"]:
        lines.extend([mkt["description"], ""])
    lines.extend([
        f"- **TAM**: ${mkt['tam']:,.0f}" if mkt["tam"] else "- **TAM**: N/A",
        f"- **SAM**: ${mkt['sam']:,.0f}" if mkt["sam"] else "- **SAM**: N/A",
        f"- **SOM**: ${mkt['som']:,.0f}" if mkt["som"] else "- **SOM**: N/A",
        "",
    ])

    # Competitive landscape
    lines.extend(["## Competitive Landscape", ""])
    if report["competitive_landscape"]:
        for comp in report["competitive_landscape"]:
            lines.append(f"- **{comp['name']}**: {comp['description']}")
            if comp.get("differentiator"):
                lines.append(f"  - *Our edge:* {comp['differentiator']}")
        lines.append("")
    else:
        lines.extend(["- No competitors identified yet.", ""])

    # Traction
    tr = report["traction"]
    lines.extend(["## Traction", ""])
    if tr["metrics"]:
        for k, v in tr["metrics"].items():
            if isinstance(v, float):
                lines.append(f"- **{k}**: {v:,.2f}")
            else:
                lines.append(f"- **{k}**: {v:,}" if isinstance(v, int) else f"- **{k}**: {v}")
        lines.append("")
    else:
        lines.extend(["- No traction data provided.", ""])

    # Team
    lines.extend(["## Team", ""])
    if report["team"]:
        for member in report["team"]:
            bio = f" — {member['bio']}" if member.get("bio") else ""
            lines.append(f"- **{member['name']}**, {member['role']}{bio}")
        lines.append("")
    else:
        lines.extend(["- Team details not provided.", ""])

    # Funding
    fd = report["funding"]
    lines.extend(["## The Ask", ""])
    if fd["ask_amount"] is not None:
        lines.extend([f"**Raising:** ${fd['ask_amount']:,.0f}", ""])
        if fd["use_of_funds"]:
            lines.append("**Use of Funds:**")
            lines.append("")
            for item in fd["use_of_funds"]:
                lines.append(f"- {item['category']}: {item['percentage']}%")
            lines.append("")
    else:
        lines.extend(["- Funding details not specified.", ""])

    return "\n".join(lines).rstrip() + "\n"


def render_investor_memo_json(report: dict[str, Any]) -> str:
    """Render investor memo as formatted JSON."""
    return json.dumps(report, indent=2, default=str)


# ── Internal helpers ─────────────────────────────────────────────────


def _validate_inputs(
    *,
    company_name: str,
    use_of_funds: list[dict[str, Any]] | None,
) -> None:
    """Validate memo inputs."""
    if not company_name or not company_name.strip():
        raise ValueError("company_name must be a non-empty string")
    if use_of_funds is not None:
        total = sum(item.get("percentage", 0) for item in use_of_funds)
        if abs(total - 100) > 0.01:
            raise ValueError(
                f"use_of_funds percentages must sum to 100 (got {total})"
            )


def _build_executive_summary(
    company_name: str,
    tagline: str,
    market: dict[str, Any] | None,
    traction: dict[str, Any] | None,
    ask_amount: float | None,
) -> dict[str, Any]:
    """Build executive summary text."""
    parts: list[str] = []

    if tagline:
        parts.append(f"{company_name} — {tagline}.")
    else:
        parts.append(f"{company_name} is building a category-defining product.")

    if market and market.get("tam"):
        parts.append(
            f"The addressable market is ${market['tam']:,.0f}."
        )

    if traction:
        highlights = []
        if "mrr" in traction:
            highlights.append(f"${traction['mrr']:,.0f} MRR")
        if "customers" in traction:
            highlights.append(f"{traction['customers']:,} customers")
        if "growth_rate" in traction:
            highlights.append(f"{traction['growth_rate']:.0%} MoM growth")
        if highlights:
            parts.append(f"Current traction: {', '.join(highlights)}.")

    if ask_amount is not None:
        parts.append(f"Raising ${ask_amount:,.0f} to accelerate growth.")

    return {"text": " ".join(parts)}


def _build_market_section(
    market: dict[str, Any] | None,
) -> dict[str, Any]:
    """Normalize market opportunity data."""
    if not market:
        return {"tam": None, "sam": None, "som": None, "description": None}
    return {
        "tam": market.get("tam"),
        "sam": market.get("sam"),
        "som": market.get("som"),
        "description": market.get("description"),
    }


def _build_competitive_section(
    competitors: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Normalize competitive landscape data."""
    if not competitors:
        return []
    result: list[dict[str, Any]] = []
    for comp in competitors:
        result.append({
            "name": comp.get("name", "Unknown"),
            "description": comp.get("description", ""),
            "differentiator": comp.get("differentiator", ""),
        })
    return result


def _build_traction_section(
    traction: dict[str, Any] | None,
) -> dict[str, Any]:
    """Normalize traction metrics."""
    return {"metrics": traction or {}}


def _build_team_section(
    team: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    """Normalize team data."""
    if not team:
        return []
    return [
        {
            "name": m.get("name", "Unknown"),
            "role": m.get("role", ""),
            "bio": m.get("bio", ""),
        }
        for m in team
    ]


def _build_funding_section(
    ask_amount: float | None,
    use_of_funds: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Build funding section."""
    return {
        "ask_amount": ask_amount,
        "use_of_funds": use_of_funds or [],
    }
