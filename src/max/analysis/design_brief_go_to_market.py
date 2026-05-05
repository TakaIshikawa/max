"""Deterministic go-to-market strategy exports for persisted design briefs."""

from __future__ import annotations

import csv
from io import StringIO
import json
from typing import Any

from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.go_to_market.v1"
KIND = "max.design_brief.go_to_market_strategy"

CSV_COLUMNS = (
    "design_brief_id",
    "design_brief_title",
    "section",
    "item_id",
    "segment_name",
    "positioning",
    "channel_name",
    "channel_type",
    "message",
    "priority",
    "owner",
    "timeline",
    "success_metric",
    "source_idea_ids",
)


def build_design_brief_go_to_market_strategy(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build a go-to-market strategy from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    context = _go_to_market_context(design_brief, source_ideas)
    segments = _market_segments(context, source_idea_ids)
    positioning = _positioning_statements(context, segments, source_idea_ids)
    channels = _distribution_channels(context, source_idea_ids)
    messaging = _key_messaging(context, positioning, source_idea_ids)
    timeline = _launch_timeline(design_brief, context, source_idea_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {
            "project": "max",
            "entity_type": "design_brief",
            "id": design_brief["id"],
            "generated_at": design_brief.get("updated_at") or design_brief.get("created_at"),
        },
        "design_brief": {
            "id": design_brief["id"],
            "title": design_brief["title"],
            "domain": design_brief.get("domain", ""),
            "theme": design_brief.get("theme", ""),
            "readiness_score": float(design_brief.get("readiness_score") or 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": source_idea_ids,
        },
        "summary": {
            "strategy_goal": f"Define go-to-market approach for {design_brief['title']}.",
            "target_market": context["target_market"],
            "value_proposition": context["value_proposition"],
            "competitive_position": context["competitive_position"],
            "segment_count": len(segments),
            "channel_count": len(channels),
            "messaging_count": len(messaging),
        },
        "market_segments": segments,
        "positioning_statements": positioning,
        "distribution_channels": channels,
        "key_messaging": messaging,
        "launch_timeline": timeline,
        "source_ideas": source_ideas,
    }


def render_design_brief_go_to_market_strategy(
    strategy: dict[str, Any], fmt: str = "json"
) -> str:
    """Render the go-to-market strategy as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(strategy, indent=2) + "\n"
    if fmt == "csv":
        return render_design_brief_go_to_market_strategy_csv(strategy)
    if fmt != "markdown":
        raise ValueError(f"Unsupported go-to-market strategy format: {fmt}")

    return _render_markdown(strategy)


def render_design_brief_go_to_market_strategy_csv(strategy: dict[str, Any]) -> str:
    """Render the go-to-market strategy as deterministic CSV rows."""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(strategy):
        writer.writerow(row)
    return output.getvalue()


def _go_to_market_context(
    design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]
) -> dict[str, Any]:
    """Extract go-to-market context from design brief and source ideas."""
    target_market = _text(design_brief.get("target_customer")) or _text(
        design_brief.get("primary_persona")
    )
    if not target_market:
        for idea in source_ideas:
            if not idea.get("missing"):
                target_market = _text(idea.get("specific_user"))
                if target_market:
                    break

    value_prop = _text(design_brief.get("value_proposition")) or _text(
        design_brief.get("why_statement")
    )
    if not value_prop:
        for idea in source_ideas:
            if not idea.get("missing"):
                value_prop = _text(idea.get("value_proposition"))
                if value_prop:
                    break

    competitive_position = _text(design_brief.get("competitive_position")) or _text(
        design_brief.get("differentiation")
    )

    return {
        "target_market": target_market or "primary users",
        "value_proposition": value_prop or "improved workflow efficiency",
        "competitive_position": competitive_position
        or "differentiated through implementation approach",
        "buyer": _text(design_brief.get("buyer")) or target_market or "end users",
        "workflow_context": _text(design_brief.get("workflow_context"))
        or _text(design_brief.get("title")),
    }


def _market_segments(
    context: dict[str, Any], source_idea_ids: list[str]
) -> list[dict[str, Any]]:
    """Generate market segments based on context."""
    segments = [
        {
            "id": "SEG01",
            "name": context["target_market"],
            "description": f"Primary target market for {context['workflow_context']}",
            "size": "estimated_primary_market",
            "priority": "high",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "SEG02",
            "name": context["buyer"],
            "description": "Decision-making stakeholder segment",
            "size": "estimated_buyer_market",
            "priority": "high" if context["buyer"] != context["target_market"] else "medium",
            "source_idea_ids": source_idea_ids,
        },
    ]
    return segments


def _positioning_statements(
    context: dict[str, Any],
    segments: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    """Generate positioning statements for each segment."""
    return [
        {
            "id": f"POS{i:02d}",
            "segment_id": segment["id"],
            "segment_name": segment["name"],
            "statement": f"For {segment['name']}, {context['workflow_context']} delivers {context['value_proposition']}. {context['competitive_position']}",
            "priority": segment["priority"],
            "source_idea_ids": source_idea_ids,
        }
        for i, segment in enumerate(segments, start=1)
    ]


def _distribution_channels(
    context: dict[str, Any], source_idea_ids: list[str]
) -> list[dict[str, Any]]:
    """Define distribution channels for go-to-market."""
    return [
        {
            "id": "CH01",
            "name": "Direct sales",
            "type": "direct",
            "description": "Direct engagement with buyers and users",
            "owner": "sales_team",
            "priority": "high",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "CH02",
            "name": "Product marketing",
            "type": "marketing",
            "description": "Marketing campaigns targeting identified segments",
            "owner": "marketing_team",
            "priority": "high",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "CH03",
            "name": "Customer success",
            "type": "retention",
            "description": "Existing customer adoption and expansion",
            "owner": "customer_success_team",
            "priority": "medium",
            "source_idea_ids": source_idea_ids,
        },
    ]


def _key_messaging(
    context: dict[str, Any],
    positioning: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    """Define key messaging for each positioning statement."""
    messages = []
    for i, pos in enumerate(positioning, start=1):
        messages.append(
            {
                "id": f"MSG{i:02d}",
                "positioning_id": pos["id"],
                "segment_name": pos["segment_name"],
                "message": pos["statement"],
                "channel": "all",
                "priority": pos["priority"],
                "source_idea_ids": source_idea_ids,
            }
        )
    return messages


def _launch_timeline(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    """Generate a basic launch timeline."""
    return [
        {
            "id": "TL01",
            "phase": "pre-launch",
            "activity": "Prepare messaging and sales enablement",
            "owner": "product_marketing",
            "priority": "high",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "TL02",
            "phase": "launch",
            "activity": "Announce to target segments via primary channels",
            "owner": "marketing_team",
            "priority": "critical",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "TL03",
            "phase": "post-launch",
            "activity": "Monitor adoption metrics and iterate messaging",
            "owner": "product_team",
            "priority": "high",
            "source_idea_ids": source_idea_ids,
        },
    ]


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch source ideas for the design brief."""
    source_ideas = []
    lead_idea_id = design_brief.get("lead_idea_id")
    source_idea_ids = design_brief.get("source_idea_ids") or []

    for idea_id in source_idea_ids:
        idea = store.get_buildable_unit(idea_id)
        if idea:
            source_ideas.append(
                {
                    "id": idea.id,
                    "title": idea.title,
                    "role": "lead" if idea.id == lead_idea_id else "supporting",
                    "missing": False,
                }
            )
        else:
            source_ideas.append({"id": idea_id, "missing": True})

    return source_ideas


def _csv_rows(strategy: dict[str, Any]) -> list[dict[str, str]]:
    """Generate CSV rows from go-to-market strategy."""
    rows: list[dict[str, str]] = []
    brief = strategy.get("design_brief", {})
    brief_id = brief.get("id", "")
    brief_title = brief.get("title", "")
    source_idea_ids = _csv_list(brief.get("source_idea_ids", []))

    # Market segments
    for segment in strategy.get("market_segments", []):
        rows.append(
            {
                "design_brief_id": brief_id,
                "design_brief_title": brief_title,
                "section": "market_segments",
                "item_id": _text(segment.get("id")),
                "segment_name": _text(segment.get("name")),
                "positioning": _text(segment.get("description")),
                "channel_name": "",
                "channel_type": "",
                "message": "",
                "priority": _text(segment.get("priority")),
                "owner": "",
                "timeline": "",
                "success_metric": _text(segment.get("size")),
                "source_idea_ids": source_idea_ids,
            }
        )

    # Positioning statements
    for pos in strategy.get("positioning_statements", []):
        rows.append(
            {
                "design_brief_id": brief_id,
                "design_brief_title": brief_title,
                "section": "positioning_statements",
                "item_id": _text(pos.get("id")),
                "segment_name": _text(pos.get("segment_name")),
                "positioning": _text(pos.get("statement")),
                "channel_name": "",
                "channel_type": "",
                "message": "",
                "priority": _text(pos.get("priority")),
                "owner": "",
                "timeline": "",
                "success_metric": "",
                "source_idea_ids": source_idea_ids,
            }
        )

    # Distribution channels
    for channel in strategy.get("distribution_channels", []):
        rows.append(
            {
                "design_brief_id": brief_id,
                "design_brief_title": brief_title,
                "section": "distribution_channels",
                "item_id": _text(channel.get("id")),
                "segment_name": "",
                "positioning": "",
                "channel_name": _text(channel.get("name")),
                "channel_type": _text(channel.get("type")),
                "message": _text(channel.get("description")),
                "priority": _text(channel.get("priority")),
                "owner": _text(channel.get("owner")),
                "timeline": "",
                "success_metric": "",
                "source_idea_ids": source_idea_ids,
            }
        )

    # Key messaging
    for msg in strategy.get("key_messaging", []):
        rows.append(
            {
                "design_brief_id": brief_id,
                "design_brief_title": brief_title,
                "section": "key_messaging",
                "item_id": _text(msg.get("id")),
                "segment_name": _text(msg.get("segment_name")),
                "positioning": "",
                "channel_name": _text(msg.get("channel")),
                "channel_type": "",
                "message": _text(msg.get("message")),
                "priority": _text(msg.get("priority")),
                "owner": "",
                "timeline": "",
                "success_metric": "",
                "source_idea_ids": source_idea_ids,
            }
        )

    # Launch timeline
    for item in strategy.get("launch_timeline", []):
        rows.append(
            {
                "design_brief_id": brief_id,
                "design_brief_title": brief_title,
                "section": "launch_timeline",
                "item_id": _text(item.get("id")),
                "segment_name": "",
                "positioning": "",
                "channel_name": "",
                "channel_type": "",
                "message": _text(item.get("activity")),
                "priority": _text(item.get("priority")),
                "owner": _text(item.get("owner")),
                "timeline": _text(item.get("phase")),
                "success_metric": "",
                "source_idea_ids": source_idea_ids,
            }
        )

    return rows


def _render_markdown(strategy: dict[str, Any]) -> str:
    """Render the go-to-market strategy as Markdown."""
    brief = strategy.get("design_brief", {})
    summary = strategy.get("summary", {})
    lines = [
        f"# Go-to-Market Strategy: {_text(brief.get('title'), 'Untitled')}",
        "",
        f"Schema: `{_text(strategy.get('schema_version'))}`",
        f"Design brief: `{_text(brief.get('id'))}`",
        f"Domain: {_text(brief.get('domain'), 'general')}",
        "",
        "## Summary",
        "",
        f"- **Strategy goal**: {_text(summary.get('strategy_goal'))}",
        f"- **Target market**: {_text(summary.get('target_market'))}",
        f"- **Value proposition**: {_text(summary.get('value_proposition'))}",
        f"- **Competitive position**: {_text(summary.get('competitive_position'))}",
        f"- **Market segments**: {summary.get('segment_count', 0)}",
        f"- **Distribution channels**: {summary.get('channel_count', 0)}",
        "",
        "## Market Segments",
        "",
    ]

    for segment in strategy.get("market_segments", []):
        lines.extend(
            [
                f"### {_text(segment.get('id'))}: {_text(segment.get('name'))}",
                "",
                f"- **Description**: {_text(segment.get('description'))}",
                f"- **Priority**: {_text(segment.get('priority'))}",
                f"- **Size**: {_text(segment.get('size'))}",
                "",
            ]
        )

    lines.extend(["## Distribution Channels", ""])
    for channel in strategy.get("distribution_channels", []):
        lines.extend(
            [
                f"### {_text(channel.get('id'))}: {_text(channel.get('name'))}",
                "",
                f"- **Type**: {_text(channel.get('type'))}",
                f"- **Owner**: {_text(channel.get('owner'))}",
                f"- **Priority**: {_text(channel.get('priority'))}",
                f"- **Description**: {_text(channel.get('description'))}",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def _text(value: Any, default: str = "") -> str:
    """Convert value to text with default fallback."""
    if value is None:
        return default
    return str(value).strip() or default


def _csv_list(values: list[str]) -> str:
    """Format list for CSV output."""
    return " | ".join(str(v).strip() for v in values if str(v).strip())
