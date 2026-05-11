"""Partner ecosystem map export for go-to-market and integration planning.

Priority tiers use a deterministic heuristic:

* tier_1: strategic value score is at least 4 and integration effort is at
  most 2, or value is at least 3 with low effort.
* tier_2: value is at least 3, or value is at least 2 with effort at most 2.
* tier_3: every other partner opportunity.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.partner_ecosystem_map.v1"
KIND = "max.partner_ecosystem_map"

_TYPE_ORDER = {"direct": 0, "integration": 1, "channel": 2}


def build_partner_ecosystem_map_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    """Build a partner ecosystem map from buildable unit metadata."""
    units = store.get_buildable_units(limit=1000, domain=domain)
    rows = [row for unit in units for row in _partner_rows(unit)]
    rows.sort(key=lambda row: (_priority_rank(row["priority_tier"]), row["ecosystem"], row["partner_name"].lower(), row["idea_id"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "partner_ecosystem_map",
            "domain_filter": domain,
        },
        "partner_row_count": len(rows),
        "partner_rows": rows,
        "summary": _summary(rows),
        "recommendations": _recommendations(rows),
    }


def render_partner_ecosystem_map_markdown(report: dict[str, Any]) -> str:
    """Render a partner ecosystem map as Markdown."""
    summary = report.get("summary", {})
    lines = [
        "# Partner Ecosystem Map",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        f"Partner opportunities: {report.get('partner_row_count', 0)}",
        "",
        "## Partner Opportunities",
        "",
    ]

    if report.get("partner_rows"):
        lines.extend([
            "| Partner | Unit | Type | Ecosystem | Value | Effort | Priority | Dependency Notes |",
            "|---------|------|------|-----------|-------|--------|----------|------------------|",
        ])
        for row in report["partner_rows"]:
            lines.append(
                f"| {row['partner_name']} | {row['unit_title']} | {', '.join(row['partner_types'])} | "
                f"{row['ecosystem']} | {row['strategic_value']} | {row['integration_effort']} | "
                f"{row['priority_tier']} | {', '.join(row['dependency_notes']) or 'none'} |"
            )
    else:
        lines.append("- No partner metadata found. Add partners, integration_partners, or channel_partners metadata to map ecosystem opportunities.")

    lines.extend([
        "",
        "## Ecosystem Rollup",
        "",
        "| Ecosystem | Partners | Tier 1 | Tier 2 | Tier 3 |",
        "|-----------|----------|--------|--------|--------|",
    ])
    for row in summary.get("by_ecosystem", []):
        counts = row["priority_counts"]
        lines.append(f"| {row['ecosystem']} | {row['partner_count']} | {counts['tier_1']} | {counts['tier_2']} | {counts['tier_3']} |")

    lines.extend([
        "",
        "## Partner Type Rollup",
        "",
        "| Partner Type | Partners | Tier 1 | Tier 2 | Tier 3 |",
        "|--------------|----------|--------|--------|--------|",
    ])
    for row in summary.get("by_partner_type", []):
        counts = row["priority_counts"]
        lines.append(f"| {row['partner_type']} | {row['partner_count']} | {counts['tier_1']} | {counts['tier_2']} | {counts['tier_3']} |")

    lines.extend(["", "## Recommendations", ""])
    for recommendation in report.get("recommendations", []):
        lines.append(f"- {recommendation}")

    return "\n".join(lines).rstrip() + "\n"


def render_partner_ecosystem_map_json(report: dict[str, Any]) -> str:
    """Render a partner ecosystem map as stable formatted JSON."""
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def _partner_rows(unit: Any) -> list[dict[str, Any]]:
    metadata = _metadata(unit)
    candidates = (
        _partner_values(metadata.get("partners"), metadata, "direct")
        + _partner_values(metadata.get("integration_partners"), metadata, "integration")
        + _partner_values(metadata.get("channel_partners"), metadata, "channel")
    )
    consolidated: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        name = str(candidate.get("partner_name") or "").strip()
        if not name:
            continue
        key = name.lower()
        existing = consolidated.get(key)
        if existing is None:
            consolidated[key] = candidate
            continue
        existing["partner_types"] = sorted(
            set(existing["partner_types"]) | set(candidate["partner_types"]),
            key=lambda value: (_TYPE_ORDER.get(value, 99), value),
        )
        existing["strategic_value_score"] = max(existing["strategic_value_score"], candidate["strategic_value_score"])
        existing["integration_effort_score"] = min(existing["integration_effort_score"], candidate["integration_effort_score"])
        if existing["ecosystem"] == "unspecified" and candidate["ecosystem"] != "unspecified":
            existing["ecosystem"] = candidate["ecosystem"]
        existing["dependency_notes"] = sorted(set(existing["dependency_notes"]) | set(candidate["dependency_notes"]))

    rows = []
    for item in consolidated.values():
        value_score = item["strategic_value_score"]
        effort_score = item["integration_effort_score"]
        priority = _priority_tier(value_score, effort_score)
        rows.append({
            "idea_id": str(getattr(unit, "id", "")),
            "unit_title": str(getattr(unit, "title", "Untitled")),
            "domain": str(getattr(unit, "domain", "") or "general"),
            "partner_name": item["partner_name"],
            "partner_type": item["partner_types"][0],
            "partner_types": item["partner_types"],
            "ecosystem": item["ecosystem"],
            "strategic_value": _score_label(value_score),
            "strategic_value_score": value_score,
            "integration_effort": _effort_label(effort_score),
            "integration_effort_score": effort_score,
            "priority_tier": priority,
            "dependency_notes": _dependency_notes(item["dependency_notes"], priority, effort_score, item["ecosystem"]),
        })
    return rows


def _partner_values(value: Any, metadata: dict[str, Any], default_type: str) -> list[dict[str, Any]]:
    values = _items(value)
    return [_partner_value(item, metadata, default_type) for item in values]


def _partner_value(item: Any, metadata: dict[str, Any], default_type: str) -> dict[str, Any]:
    details = item if isinstance(item, dict) else {"partner_name": item}
    partner_type = str(details.get("partner_type") or details.get("type") or metadata.get("partner_type") or default_type).strip().lower()
    if partner_type not in _TYPE_ORDER:
        partner_type = default_type
    value_score = _score(details.get("strategic_value", metadata.get("strategic_value")), default=2)
    effort_score = _score(details.get("integration_effort", metadata.get("integration_effort")), default=2)
    notes = _items(details.get("dependency_notes", details.get("notes", metadata.get("dependency_notes", []))))
    return {
        "partner_name": str(details.get("partner_name") or details.get("name") or details.get("partner") or "").strip(),
        "partner_types": [partner_type],
        "ecosystem": str(details.get("ecosystem") or metadata.get("ecosystem") or "unspecified").strip() or "unspecified",
        "strategic_value_score": value_score,
        "integration_effort_score": effort_score,
        "dependency_notes": notes,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "priority_counts": {tier: sum(1 for row in rows if row["priority_tier"] == tier) for tier in ["tier_1", "tier_2", "tier_3"]},
        "by_partner_type": _rollups(rows, "partner_type", explode_types=True),
        "by_ecosystem": _rollups(rows, "ecosystem"),
    }


def _rollups(rows: list[dict[str, Any]], key: str, *, explode_types: bool = False) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        names = row["partner_types"] if explode_types else [row[key]]
        for name in names:
            groups[str(name)].append(row)
    return [
        {
            key: name,
            "partner_count": len(items),
            "priority_counts": {tier: sum(1 for row in items if row["priority_tier"] == tier) for tier in ["tier_1", "tier_2", "tier_3"]},
        }
        for name, items in sorted(groups.items())
    ]


def _recommendations(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Add partner metadata to buildable units before ecosystem planning."]
    recommendations = []
    tier_1 = [row for row in rows if row["priority_tier"] == "tier_1"]
    high_effort = [row for row in rows if row["integration_effort_score"] >= 3]
    if tier_1:
        names = ", ".join(row["partner_name"] for row in tier_1[:3])
        recommendations.append(f"Prioritize tier_1 partner discovery for {names}.")
    if high_effort:
        recommendations.append("Validate integration ownership and sequencing for high-effort partner dependencies.")
    ecosystems = {row["ecosystem"] for row in rows if row["ecosystem"] != "unspecified"}
    if len(ecosystems) <= 1:
        recommendations.append("Broaden ecosystem coverage to reduce partner concentration risk.")
    return recommendations or ["Maintain partner coverage and revisit priority tiers as metadata changes."]


def _dependency_notes(notes: list[str], priority: str, effort_score: int, ecosystem: str) -> list[str]:
    values = list(notes)
    if effort_score >= 3:
        values.append("high integration effort")
    if ecosystem == "unspecified":
        values.append("ecosystem unspecified")
    if priority == "tier_1":
        values.append("executive sponsorship recommended")
    return sorted(set(values))


def _items(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    if isinstance(value, dict):
        return [
            dict(details, partner_name=name) if isinstance(details, dict) else {"partner_name": name, "strategic_value": details}
            for name, details in value.items()
        ]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [value]


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _score(value: Any, *, default: int) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, int | float):
        return max(1, min(int(value), 4))
    normalized = str(value).strip().lower().replace("-", "_")
    labels = {
        "low": 1,
        "small": 1,
        "medium": 2,
        "moderate": 2,
        "high": 3,
        "large": 3,
        "strategic": 4,
        "critical": 4,
        "transformational": 4,
    }
    return labels.get(normalized, default)


def _score_label(score: int) -> str:
    return {1: "low", 2: "medium", 3: "high", 4: "strategic"}.get(score, "medium")


def _effort_label(score: int) -> str:
    return {1: "low", 2: "medium", 3: "high", 4: "very_high"}.get(score, "medium")


def _priority_tier(value_score: int, effort_score: int) -> str:
    if (value_score >= 4 and effort_score <= 2) or (value_score >= 3 and effort_score <= 1):
        return "tier_1"
    if value_score >= 3 or (value_score >= 2 and effort_score <= 2):
        return "tier_2"
    return "tier_3"


def _priority_rank(value: str) -> int:
    return {"tier_1": 0, "tier_2": 1, "tier_3": 2}.get(value, 3)
