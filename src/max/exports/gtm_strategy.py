"""Go-to-market strategy export — GTM planning documents.

Synthesizes market signals into channel strategies, launch timelines,
and messaging frameworks.  Exports positioning statements, target segment
priorities, and distribution channel recommendations.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.gtm_strategy.v1"
KIND = "max.gtm_strategy"

# ── Default channel weights ──────────────────────────────────────────

_CHANNEL_CATALOG: list[dict[str, Any]] = [
    {"name": "Content Marketing", "category": "inbound", "effort": "medium", "cost": "low"},
    {"name": "SEO / Organic Search", "category": "inbound", "effort": "high", "cost": "low"},
    {"name": "Paid Search (SEM)", "category": "paid", "effort": "low", "cost": "high"},
    {"name": "Social Media Ads", "category": "paid", "effort": "low", "cost": "medium"},
    {"name": "Developer Relations", "category": "community", "effort": "high", "cost": "medium"},
    {"name": "Partnerships / Integrations", "category": "partnerships", "effort": "high", "cost": "low"},
    {"name": "Email / Nurture Campaigns", "category": "inbound", "effort": "medium", "cost": "low"},
    {"name": "Product-Led Growth", "category": "product", "effort": "high", "cost": "low"},
]


# ── Public API ───────────────────────────────────────────────────────


def build_gtm_strategy(
    *,
    product_name: str,
    target_segments: list[dict[str, Any]],
    positioning: dict[str, str] | None = None,
    channels: list[str] | None = None,
    launch_date: str | None = None,
    milestones: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build a go-to-market strategy document.

    Args:
        product_name: Name of the product being launched.
        target_segments: List of segment dicts with at least 'name' and
            'description' keys; optional 'priority' (1-5, lower = higher).
        positioning: Optional dict with 'statement', 'differentiator',
            'value_proposition' keys.
        channels: Optional list of channel names to include.  If *None*,
            all channels from the catalog are recommended.
        launch_date: Optional ISO-8601 date string for the launch.
        milestones: Optional list of dicts with 'name' and 'date' keys.

    Returns:
        Dict with positioning, segments, channel plan, timeline, and
        messaging framework.

    Raises:
        ValueError: If required data is missing or malformed.
    """
    _validate_inputs(product_name=product_name, target_segments=target_segments)

    prioritized_segments = _prioritize_segments(target_segments)
    pos = _build_positioning(product_name, positioning)
    channel_plan = _build_channel_plan(channels)
    timeline = _build_timeline(launch_date, milestones)
    messaging = _build_messaging_framework(product_name, prioritized_segments, pos)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "gtm_strategy",
        },
        "product_name": product_name,
        "positioning": pos,
        "target_segments": prioritized_segments,
        "channel_plan": channel_plan,
        "timeline": timeline,
        "messaging_framework": messaging,
    }


def render_gtm_strategy_markdown(report: dict[str, Any]) -> str:
    """Render GTM strategy report as Markdown."""
    lines = [
        f"# Go-to-Market Strategy: {report['product_name']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
    ]

    # Positioning
    pos = report["positioning"]
    lines.extend([
        "## Positioning",
        "",
        f"**Statement:** {pos['statement']}",
        "",
        f"**Differentiator:** {pos['differentiator']}",
        "",
        f"**Value Proposition:** {pos['value_proposition']}",
        "",
    ])

    # Target segments
    lines.extend(["## Target Segments", ""])
    for seg in report["target_segments"]:
        lines.extend([
            f"### {seg['name']} (Priority: {seg['priority']})",
            "",
            f"{seg['description']}",
            "",
        ])
        if seg.get("rationale"):
            lines.extend([f"**Rationale:** {seg['rationale']}", ""])

    # Channel plan
    lines.extend([
        "## Distribution Channels",
        "",
        "| Channel | Category | Effort | Cost |",
        "|---------|----------|--------|------|",
    ])
    for ch in report["channel_plan"]:
        lines.append(
            f"| {ch['name']} | {ch['category']} | {ch['effort']} | {ch['cost']} |"
        )
    lines.append("")

    # Timeline
    tl = report["timeline"]
    lines.extend(["## Launch Timeline", ""])
    if tl["launch_date"]:
        lines.append(f"**Target Launch:** {tl['launch_date']}")
        lines.append("")
    if tl["milestones"]:
        lines.append("**Milestones:**")
        lines.append("")
        for ms in tl["milestones"]:
            lines.append(f"- **{ms['name']}**: {ms['date']}")
        lines.append("")

    # Messaging framework
    lines.extend(["## Messaging Framework", ""])
    for msg in report["messaging_framework"]:
        lines.extend([
            f"### {msg['segment']}",
            "",
            f"- **Headline:** {msg['headline']}",
            f"- **Key message:** {msg['key_message']}",
            "",
        ])

    return "\n".join(lines).rstrip() + "\n"


def render_gtm_strategy_json(report: dict[str, Any]) -> str:
    """Render GTM strategy report as formatted JSON."""
    return json.dumps(report, indent=2, default=str)


# ── Internal helpers ─────────────────────────────────────────────────


def _validate_inputs(
    *,
    product_name: str,
    target_segments: list[dict[str, Any]],
) -> None:
    """Validate GTM strategy inputs."""
    if not product_name or not product_name.strip():
        raise ValueError("product_name must be a non-empty string")
    if not target_segments:
        raise ValueError("target_segments must contain at least one segment")
    for seg in target_segments:
        if "name" not in seg or "description" not in seg:
            raise ValueError("each target segment must have 'name' and 'description'")


def _prioritize_segments(
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sort and annotate target segments by priority."""
    result: list[dict[str, Any]] = []
    for seg in segments:
        entry = {
            "name": seg["name"],
            "description": seg["description"],
            "priority": seg.get("priority", 3),
            "rationale": seg.get("rationale", ""),
        }
        result.append(entry)
    result.sort(key=lambda s: s["priority"])
    return result


def _build_positioning(
    product_name: str,
    positioning: dict[str, str] | None,
) -> dict[str, str]:
    """Build positioning statement block."""
    if positioning:
        return {
            "statement": positioning.get(
                "statement",
                f"{product_name} is the leading solution in its category.",
            ),
            "differentiator": positioning.get(
                "differentiator",
                "Unique technology and approach.",
            ),
            "value_proposition": positioning.get(
                "value_proposition",
                f"{product_name} delivers measurable results.",
            ),
        }
    return {
        "statement": f"{product_name} is the leading solution in its category.",
        "differentiator": "Unique technology and approach.",
        "value_proposition": f"{product_name} delivers measurable results.",
    }


def _build_channel_plan(
    channels: list[str] | None,
) -> list[dict[str, Any]]:
    """Build distribution channel plan."""
    if channels is None:
        return list(_CHANNEL_CATALOG)
    result: list[dict[str, Any]] = []
    catalog_map = {ch["name"]: ch for ch in _CHANNEL_CATALOG}
    for name in channels:
        if name in catalog_map:
            result.append(catalog_map[name])
        else:
            result.append({
                "name": name,
                "category": "custom",
                "effort": "unknown",
                "cost": "unknown",
            })
    return result


def _build_timeline(
    launch_date: str | None,
    milestones: list[dict[str, str]] | None,
) -> dict[str, Any]:
    """Build launch timeline with milestones."""
    return {
        "launch_date": launch_date,
        "milestones": milestones or [],
    }


def _build_messaging_framework(
    product_name: str,
    segments: list[dict[str, Any]],
    positioning: dict[str, str],
) -> list[dict[str, Any]]:
    """Generate per-segment messaging framework."""
    messages: list[dict[str, Any]] = []
    for seg in segments:
        messages.append({
            "segment": seg["name"],
            "headline": f"{product_name} for {seg['name']}",
            "key_message": (
                f"{positioning['value_proposition']} — "
                f"tailored for {seg['description'].lower().rstrip('.')}."
            ),
        })
    return messages
