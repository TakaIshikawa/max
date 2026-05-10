"""Pricing model analysis export — pricing strategy documents.

Analyzes competitor pricing, value metrics, and willingness-to-pay signals to
generate pricing tier recommendations, feature gating strategies, and revenue
projections.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.pricing_model.v1"
KIND = "max.pricing_model"

# Default pricing assumptions
_BASE_PRICE_FREE = 0
_BASE_PRICE_STARTER = 29
_BASE_PRICE_PRO = 99
_BASE_PRICE_ENTERPRISE = 499

# Conversion rate assumptions
_FREE_TO_STARTER = 0.05
_STARTER_TO_PRO = 0.25
_PRO_TO_ENTERPRISE = 0.10


def build_pricing_model(
    store: Store,
    domain: str | None = None,
) -> dict[str, Any]:
    """Build pricing model analysis from signals and buildable units.

    Args:
        store: Database store with signals and buildable units.
        domain: Optional domain filter.

    Returns:
        Dict with tier definitions, competitor pricing, value metrics,
        and revenue projections.
    """
    units = store.get_buildable_units(limit=1000, domain=domain)
    signals = store.get_signals(limit=1000)

    features = _extract_feature_set(units)
    tiers = _define_tiers(features)
    competitor_pricing = _analyze_competitor_pricing(signals, store, units)
    value_metrics = _analyze_value_metrics(units, signals)
    revenue = _project_revenue(tiers, signals)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "pricing_model",
            "domain_filter": domain,
        },
        "tiers": tiers,
        "feature_matrix": _build_feature_gate_matrix(tiers),
        "competitor_pricing": competitor_pricing,
        "value_metrics": value_metrics,
        "revenue_projections": revenue,
    }


def render_pricing_model_markdown(report: dict[str, Any]) -> str:
    """Render pricing model report as Markdown."""
    lines = [
        "# Pricing Model Analysis",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
    ]

    # Tier summary
    lines.extend(["## Pricing Tiers", ""])
    for tier in report["tiers"]:
        price_label = "Free" if tier["price"] == 0 else f"${tier['price']}/mo"
        lines.extend([
            f"### {tier['name']} — {price_label}",
            "",
            f"{tier['description']}",
            "",
            "**Features:**",
        ])
        for feat in tier["features"]:
            lines.append(f"- {feat}")
        lines.append("")

    # Feature gate matrix
    lines.extend(["## Feature Gating Matrix", ""])
    fm = report["feature_matrix"]
    if fm["features"]:
        header = "| Feature | " + " | ".join(fm["tier_names"]) + " |"
        sep = "|---------|" + "|".join(["---"] * len(fm["tier_names"])) + "|"
        lines.extend([header, sep])
        for feat_row in fm["features"]:
            cells = " | ".join(feat_row["availability"])
            lines.append(f"| {feat_row['name']} | {cells} |")
        lines.append("")

    # Competitor pricing
    lines.extend(["## Competitor Pricing Comparison", ""])
    if report["competitor_pricing"]:
        for comp in report["competitor_pricing"]:
            lines.extend([
                f"- **{comp['name']}**: {comp['pricing_summary']}",
            ])
        lines.append("")
    else:
        lines.extend(["- No competitor pricing data available", ""])

    # Value metrics
    lines.extend(["## Value Metrics", ""])
    vm = report["value_metrics"]
    for metric in vm:
        lines.append(f"- **{metric['metric']}**: {metric['description']}")
    lines.append("")

    # Revenue projections
    lines.extend(["## Revenue Projections", ""])
    rp = report["revenue_projections"]
    lines.extend([
        f"- Estimated user base: {rp['estimated_users']:,}",
        "",
        "| Tier | Users | MRR |",
        "|------|-------|-----|",
    ])
    for tr in rp["tier_revenue"]:
        lines.append(f"| {tr['tier']} | {tr['users']:,} | ${tr['mrr']:,.0f} |")
    lines.extend([
        "",
        f"**Total MRR**: ${rp['total_mrr']:,.0f}",
        f"**Total ARR**: ${rp['total_arr']:,.0f}",
        "",
    ])

    return "\n".join(lines).rstrip() + "\n"


def render_pricing_model_json(report: dict[str, Any]) -> str:
    """Render pricing model report as formatted JSON."""
    return json.dumps(report, indent=2, default=str)


# ── Internal helpers ─────────────────────────────────────────────────


def _extract_feature_set(units: list[Any]) -> list[str]:
    """Extract distinct features from unit solutions and value propositions."""
    features: list[str] = []
    seen: set[str] = set()

    for unit in units:
        for field in ("solution", "value_proposition", "one_liner"):
            text = getattr(unit, field, "")
            if text and text not in seen:
                seen.add(text)
                features.append(text)

    return features


def _define_tiers(features: list[str]) -> list[dict[str, Any]]:
    """Define pricing tiers with feature allocation."""
    # Split features across tiers by position (simulating priority)
    total = len(features)
    free_count = max(total // 4, 1) if total else 1
    starter_count = max(total // 3, 1) if total else 1
    pro_count = max(total // 3, 1) if total else 1

    free_features = features[:free_count] if features else ["Basic access"]
    starter_features = features[:free_count + starter_count] if features else ["Basic access", "Standard features"]
    pro_features = features[:free_count + starter_count + pro_count] if features else ["Basic access", "Standard features", "Advanced features"]
    enterprise_features = features if features else ["Basic access", "Standard features", "Advanced features", "Enterprise support"]

    return [
        {
            "name": "Free",
            "price": _BASE_PRICE_FREE,
            "description": "Core functionality for individual users and evaluation.",
            "features": free_features,
            "target_segment": "individual developers",
        },
        {
            "name": "Starter",
            "price": _BASE_PRICE_STARTER,
            "description": "Essential features for small teams getting started.",
            "features": starter_features,
            "target_segment": "small teams",
        },
        {
            "name": "Pro",
            "price": _BASE_PRICE_PRO,
            "description": "Full feature set for growing teams with advanced needs.",
            "features": pro_features,
            "target_segment": "growing teams",
        },
        {
            "name": "Enterprise",
            "price": _BASE_PRICE_ENTERPRISE,
            "description": "Complete platform with SLA, SSO, and dedicated support.",
            "features": enterprise_features,
            "target_segment": "large organizations",
        },
    ]


def _build_feature_gate_matrix(tiers: list[dict[str, Any]]) -> dict[str, Any]:
    """Build feature availability matrix across tiers."""
    # Collect all unique features
    all_features: list[str] = []
    seen: set[str] = set()
    for tier in tiers:
        for feat in tier["features"]:
            if feat not in seen:
                seen.add(feat)
                all_features.append(feat)

    tier_names = [t["name"] for t in tiers]
    tier_feature_sets = [set(t["features"]) for t in tiers]

    rows: list[dict[str, Any]] = []
    for feat in all_features:
        availability = []
        for feat_set in tier_feature_sets:
            availability.append("Yes" if feat in feat_set else "—")
        rows.append({"name": feat, "availability": availability})

    return {"tier_names": tier_names, "features": rows}


def _analyze_competitor_pricing(
    signals: list[Any],
    store: Store,
    units: list[Any],
) -> list[dict[str, Any]]:
    """Analyze competitor pricing from prior art and signals."""
    competitors: dict[str, dict[str, Any]] = {}

    for unit in units:
        prior_art = store.get_prior_art_matches(unit.id)
        for match in prior_art:
            name = match.get("title", "Unknown")
            if name not in competitors:
                competitors[name] = {
                    "name": name,
                    "source": match.get("source", "unknown"),
                    "mentions": 0,
                }
            competitors[name]["mentions"] += 1

    result: list[dict[str, Any]] = []
    for comp in sorted(competitors.values(), key=lambda c: c["mentions"], reverse=True)[:10]:
        comp["pricing_summary"] = f"Mentioned in {comp['mentions']} prior art matches"
        result.append(comp)

    return result


def _analyze_value_metrics(
    units: list[Any],
    signals: list[Any],
) -> list[dict[str, Any]]:
    """Identify value metrics that drive willingness-to-pay."""
    metrics: list[dict[str, Any]] = []

    # Infer from target user types
    target_counts: Counter[str] = Counter()
    for unit in units:
        target = getattr(unit, "target_users", "both")
        target_counts[target] += 1

    if target_counts.get("agents", 0) > 0:
        metrics.append({
            "metric": "API calls",
            "description": "Usage-based pricing per API call for agent integrations",
        })

    if target_counts.get("humans", 0) > 0 or target_counts.get("both", 0) > 0:
        metrics.append({
            "metric": "Seats",
            "description": "Per-user pricing for human team members",
        })

    # Signal volume as proxy for market activity
    if len(signals) > 50:
        metrics.append({
            "metric": "Data volume",
            "description": "Tiered pricing based on data/signal processing volume",
        })

    if not metrics:
        metrics.append({
            "metric": "Flat rate",
            "description": "Simple flat monthly subscription",
        })

    return metrics


def _project_revenue(
    tiers: list[dict[str, Any]],
    signals: list[Any],
) -> dict[str, Any]:
    """Project revenue based on tier pricing and estimated user base."""
    # Estimate user base from signal volume (heuristic)
    estimated_users = max(len(signals) * 100, 1000)

    # Distribution across tiers
    free_users = int(estimated_users * 0.70)
    starter_users = int(estimated_users * _FREE_TO_STARTER * 0.70 / 0.05)
    # Simplify: use fixed conversion percentages
    starter_users = max(int(estimated_users * 0.15), 1)
    pro_users = max(int(estimated_users * 0.10), 1)
    enterprise_users = max(int(estimated_users * 0.05), 1)

    tier_revenue = [
        {"tier": "Free", "users": free_users, "mrr": 0.0},
        {"tier": "Starter", "users": starter_users, "mrr": starter_users * _BASE_PRICE_STARTER},
        {"tier": "Pro", "users": pro_users, "mrr": pro_users * _BASE_PRICE_PRO},
        {"tier": "Enterprise", "users": enterprise_users, "mrr": enterprise_users * _BASE_PRICE_ENTERPRISE},
    ]

    total_mrr = sum(tr["mrr"] for tr in tier_revenue)

    return {
        "estimated_users": estimated_users,
        "tier_revenue": tier_revenue,
        "total_mrr": total_mrr,
        "total_arr": total_mrr * 12,
    }
