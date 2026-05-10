"""Executive summary report export for C-level briefing documents.

Synthesizes key findings, market opportunities, and recommended actions
from signals and buildable units into a concise one-page summary with
supporting data highlights. Exports to markdown and JSON with configurable
detail level (brief, standard, detailed).
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.executive_summary.v1"
KIND = "max.executive_summary"

# Valid detail levels
DETAIL_LEVELS = ("brief", "standard", "detailed")

# Risk indicator keywords in signal content
_RISK_KEYWORDS = [
    "risk", "threat", "vulnerab", "compet", "decline", "disrupt",
    "regulat", "compliance", "security", "deprecat", "obsole",
    "churn", "attrition", "shortage", "bottleneck",
]

# Opportunity indicator keywords
_OPPORTUNITY_KEYWORDS = [
    "opportun", "growth", "expand", "emerging", "untapped", "demand",
    "trend", "adoption", "market", "innovat", "partner", "acquisit",
    "scale", "revenue", "monetiz",
]

# Action indicator keywords
_ACTION_KEYWORDS = [
    "recommend", "should", "must", "priorit", "invest", "build",
    "launch", "migrate", "adopt", "implement", "automat", "hire",
    "improve", "optimiz", "focus",
]


def build_executive_summary(
    store: Store,
    domain: str | None = None,
    *,
    detail_level: str = "standard",
) -> dict[str, Any]:
    """Build executive summary from signals and buildable units.

    Args:
        store: Database store containing signals and buildable units.
        domain: Optional domain filter for scoping the summary.
        detail_level: One of 'brief', 'standard', 'detailed'.

    Returns:
        Dict with schema metadata, key findings, opportunities, risks,
        and recommended actions.
    """
    if detail_level not in DETAIL_LEVELS:
        detail_level = "standard"

    units = store.get_buildable_units(limit=1000, domain=domain)
    signals = store.get_signals(limit=1000)

    key_findings = _extract_key_findings(units, signals, detail_level)
    market_opportunities = _extract_opportunities(units, signals, detail_level)
    risk_highlights = _extract_risks(signals, detail_level)
    recommended_actions = _extract_actions(units, signals, detail_level)
    data_highlights = _build_data_highlights(units, signals)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "executive_summary",
            "domain_filter": domain,
        },
        "detail_level": detail_level,
        "key_findings": key_findings,
        "market_opportunities": market_opportunities,
        "risk_highlights": risk_highlights,
        "recommended_actions": recommended_actions,
        "data_highlights": data_highlights,
    }


def render_executive_summary_markdown(report: dict[str, Any]) -> str:
    """Render executive summary report as Markdown.

    Args:
        report: Summary report dict from build_executive_summary.

    Returns:
        Markdown formatted executive summary document.
    """
    lines = [
        "# Executive Summary",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        f"Detail level: {report['detail_level']}",
        "",
    ]

    # Key Findings
    lines.extend(["## Key Findings", ""])
    if report["key_findings"]:
        for finding in report["key_findings"]:
            lines.append(f"- **{finding['title']}**: {finding['summary']}")
    else:
        lines.append("- No key findings identified")
    lines.append("")

    # Market Opportunities
    lines.extend(["## Market Opportunities", ""])
    if report["market_opportunities"]:
        for opp in report["market_opportunities"]:
            lines.append(f"- **{opp['title']}**: {opp['description']}")
    else:
        lines.append("- No market opportunities identified")
    lines.append("")

    # Risk Highlights
    lines.extend(["## Risk Highlights", ""])
    if report["risk_highlights"]:
        for risk in report["risk_highlights"]:
            lines.append(f"- **{risk['severity'].upper()}** — {risk['description']}")
    else:
        lines.append("- No significant risks identified")
    lines.append("")

    # Recommended Actions
    lines.extend(["## Recommended Actions", ""])
    if report["recommended_actions"]:
        for i, action in enumerate(report["recommended_actions"], 1):
            lines.append(f"{i}. **{action['action']}** — {action['rationale']}")
    else:
        lines.append("- No specific actions recommended")
    lines.append("")

    # Data Highlights
    lines.extend(["## Data Highlights", ""])
    dh = report["data_highlights"]
    lines.append(f"- **Signals analyzed**: {dh['signal_count']}")
    lines.append(f"- **Buildable units**: {dh['unit_count']}")
    if dh["top_domains"]:
        lines.append(f"- **Top domains**: {', '.join(dh['top_domains'])}")
    if dh["top_sources"]:
        lines.append(f"- **Top sources**: {', '.join(dh['top_sources'])}")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_executive_summary_json(report: dict[str, Any]) -> str:
    """Render executive summary report as formatted JSON.

    Args:
        report: Summary report dict from build_executive_summary.

    Returns:
        JSON string of the executive summary report.
    """
    return json.dumps(report, indent=2, default=str)


# ── Internal helpers ─────────────────────────────────────────────────


def _detail_limit(detail_level: str) -> int:
    """Return item limit based on detail level."""
    return {"brief": 3, "standard": 5, "detailed": 10}.get(detail_level, 5)


def _extract_key_findings(
    units: list[Any],
    signals: list[Any],
    detail_level: str,
) -> list[dict[str, str]]:
    """Extract key findings from units and high-credibility signals."""
    findings: list[dict[str, str]] = []
    limit = _detail_limit(detail_level)

    # High-quality buildable units as findings
    scored_units = sorted(
        units,
        key=lambda u: getattr(u, "quality_score", 0.0),
        reverse=True,
    )
    for unit in scored_units[:limit]:
        solution = getattr(unit, "solution", "")
        problem = getattr(unit, "problem", "")
        if solution:
            findings.append({
                "title": solution,
                "summary": problem or "Identified from buildable unit analysis",
                "source": "buildable_unit",
            })

    # Supplement with high-credibility signals
    credible = sorted(signals, key=lambda s: s.credibility, reverse=True)
    for signal in credible:
        if len(findings) >= limit:
            break
        if signal.title not in {f["title"] for f in findings}:
            findings.append({
                "title": signal.title,
                "summary": signal.content[:200],
                "source": "signal",
            })

    return findings[:limit]


def _extract_opportunities(
    units: list[Any],
    signals: list[Any],
    detail_level: str,
) -> list[dict[str, str]]:
    """Extract market opportunities from signals and unit value propositions."""
    opportunities: list[dict[str, str]] = []
    limit = _detail_limit(detail_level)

    # From unit value propositions
    for unit in units:
        vp = getattr(unit, "value_proposition", "")
        why_now = getattr(unit, "why_now", "")
        if vp:
            opportunities.append({
                "title": vp,
                "description": why_now or "Market opportunity identified",
            })

    # From signals with opportunity language
    for signal in signals:
        content_lower = signal.content.lower()
        if any(kw in content_lower for kw in _OPPORTUNITY_KEYWORDS):
            if signal.title not in {o["title"] for o in opportunities}:
                opportunities.append({
                    "title": signal.title,
                    "description": signal.content[:200],
                })

    return opportunities[:limit]


def _extract_risks(
    signals: list[Any],
    detail_level: str,
) -> list[dict[str, Any]]:
    """Extract risk highlights from signals."""
    risks: list[dict[str, str]] = []
    limit = _detail_limit(detail_level)

    for signal in signals:
        content_lower = signal.content.lower()
        matching = [kw for kw in _RISK_KEYWORDS if kw in content_lower]
        if matching:
            severity = "high" if len(matching) >= 3 else "medium" if len(matching) >= 2 else "low"
            risks.append({
                "description": signal.title,
                "severity": severity,
                "indicators": matching,
            })

    # Sort by severity
    severity_order = {"high": 0, "medium": 1, "low": 2}
    risks.sort(key=lambda r: severity_order.get(r["severity"], 3))

    return risks[:limit]


def _extract_actions(
    units: list[Any],
    signals: list[Any],
    detail_level: str,
) -> list[dict[str, str]]:
    """Extract recommended actions from units and signals."""
    actions: list[dict[str, str]] = []
    limit = _detail_limit(detail_level)

    # From buildable units with high quality scores
    scored = sorted(
        units,
        key=lambda u: getattr(u, "quality_score", 0.0),
        reverse=True,
    )
    for unit in scored[:limit]:
        solution = getattr(unit, "solution", "")
        vp = getattr(unit, "value_proposition", "")
        if solution:
            actions.append({
                "action": f"Invest in: {solution}",
                "rationale": vp or "High-quality opportunity identified",
                "priority": "high" if getattr(unit, "quality_score", 0.0) > 0.7 else "medium",
            })

    # From signals with action language
    for signal in signals:
        if len(actions) >= limit:
            break
        content_lower = signal.content.lower()
        if any(kw in content_lower for kw in _ACTION_KEYWORDS):
            if signal.title not in {a["action"] for a in actions}:
                actions.append({
                    "action": signal.title,
                    "rationale": signal.content[:200],
                    "priority": "medium",
                })

    return actions[:limit]


def _build_data_highlights(
    units: list[Any],
    signals: list[Any],
) -> dict[str, Any]:
    """Build data highlights summary."""
    domain_counter: Counter[str] = Counter()
    for unit in units:
        domain = getattr(unit, "domain", "")
        if domain:
            domain_counter[domain] += 1

    source_counter: Counter[str] = Counter()
    for signal in signals:
        source_counter[str(signal.source_type)] += 1

    return {
        "signal_count": len(signals),
        "unit_count": len(units),
        "top_domains": [d for d, _ in domain_counter.most_common(5)],
        "top_sources": [s for s, _ in source_counter.most_common(5)],
    }
