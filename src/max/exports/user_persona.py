"""User persona document export from collected signals.

Generates detailed user persona profiles with demographics, goals, pain points,
motivations, behavior patterns, and technology preferences. Exports to markdown
and structured JSON formats for design and product teams.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.user_persona.v1"
KIND = "max.user_persona"

# Keywords used to infer technology preferences from signal content
_TECH_KEYWORDS = [
    "python", "javascript", "typescript", "rust", "go", "java", "react",
    "vue", "angular", "node", "docker", "kubernetes", "aws", "gcp", "azure",
    "terraform", "ci/cd", "graphql", "rest", "grpc", "sql", "nosql",
    "redis", "postgres", "mongodb", "elasticsearch", "kafka",
    "machine learning", "deep learning", "llm", "langchain", "openai",
    "anthropic", "mcp", "rag", "embedding", "vector database",
]

# Keywords for inferring pain point themes
_PAIN_POINT_INDICATORS = [
    "difficult", "hard", "complex", "slow", "expensive", "broken",
    "missing", "lack", "frustrat", "painful", "confus", "error",
    "bug", "fail", "limit", "workaround", "hack", "manual",
]

# Keywords for inferring motivation themes
_MOTIVATION_INDICATORS = [
    "automat", "faster", "simpl", "efficient", "productive", "scale",
    "secure", "reliab", "maintain", "monitor", "deploy", "integrat",
    "collaborat", "streamlin", "optimiz",
]


def build_user_personas(
    store: Store,
    domain: str | None = None,
    *,
    max_personas: int = 5,
) -> dict[str, Any]:
    """Build user persona profiles from signals and buildable units.

    Analyzes collected signals and buildable units to synthesize user personas
    with demographics, goals, pain points, motivations, and technology
    preferences.

    Args:
        store: Database store containing signals and buildable units.
        domain: Optional domain filter for scoping persona generation.
        max_personas: Maximum number of personas to generate.

    Returns:
        Dict with schema metadata and a list of persona profiles.
    """
    units = store.get_buildable_units(limit=1000, domain=domain)
    signals = store.get_signals(limit=1000)

    # Group units by target user archetype
    user_groups = _group_by_user_archetype(units)

    # Build persona for each group
    personas: list[dict[str, Any]] = []
    for archetype, group_units in list(user_groups.items())[:max_personas]:
        # Collect signals referenced by these units
        group_signal_ids: set[str] = set()
        for unit in group_units:
            group_signal_ids.update(getattr(unit, "evidence_signals", []))

        group_signals = [s for s in signals if s.id in group_signal_ids]

        persona = _build_single_persona(archetype, group_units, group_signals)
        personas.append(persona)

    # If no units produced groupings, create a default persona from signals
    if not personas and signals:
        persona = _build_single_persona("developer", [], signals)
        personas.append(persona)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "user_persona",
            "domain_filter": domain,
        },
        "persona_count": len(personas),
        "personas": personas,
    }


def render_user_personas_markdown(report: dict[str, Any]) -> str:
    """Render user persona report as Markdown.

    Args:
        report: Persona report dict from build_user_personas.

    Returns:
        Markdown formatted persona document.
    """
    lines = [
        "# User Personas",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        f"Total personas: {report['persona_count']}",
        "",
    ]

    for i, persona in enumerate(report["personas"], 1):
        lines.extend(_render_persona_markdown(i, persona))

    return "\n".join(lines).rstrip() + "\n"


def render_user_personas_json(report: dict[str, Any]) -> str:
    """Render user persona report as formatted JSON.

    Args:
        report: Persona report dict from build_user_personas.

    Returns:
        JSON string of the persona report.
    """
    return json.dumps(report, indent=2, default=str)


# ── Internal helpers ─────────────────────────────────────────────────


def _group_by_user_archetype(units: list[Any]) -> dict[str, list[Any]]:
    """Group buildable units by target user archetype.

    Uses specific_user, target_users, and domain fields to cluster units
    into user archetypes.
    """
    groups: dict[str, list[Any]] = defaultdict(list)

    for unit in units:
        archetype = _infer_archetype(unit)
        groups[archetype].append(unit)

    return dict(groups)


def _infer_archetype(unit: Any) -> str:
    """Infer user archetype from a buildable unit's fields."""
    specific = getattr(unit, "specific_user", "")
    if specific:
        return specific.lower().strip()

    target = getattr(unit, "target_users", "both")
    domain = getattr(unit, "domain", "")

    if target == "agents":
        return "ai agent developer"
    if domain:
        return f"{domain} developer"
    return "developer"


def _build_single_persona(
    archetype: str,
    units: list[Any],
    signals: list[Any],
) -> dict[str, Any]:
    """Build a single persona profile from units and signals."""
    demographics = _infer_demographics(archetype, units)
    goals = _extract_goals(units)
    pain_points = _extract_pain_points(units, signals)
    motivations = _extract_motivations(units, signals)
    tech_preferences = _extract_tech_preferences(signals, units)
    behavior_patterns = _extract_behavior_patterns(signals)

    return {
        "name": _generate_persona_name(archetype),
        "archetype": archetype,
        "demographics": demographics,
        "goals": goals,
        "pain_points": pain_points,
        "motivations": motivations,
        "technology_preferences": tech_preferences,
        "behavior_patterns": behavior_patterns,
        "evidence": {
            "unit_count": len(units),
            "signal_count": len(signals),
        },
    }


def _generate_persona_name(archetype: str) -> str:
    """Generate a display name for a persona from its archetype."""
    return archetype.replace("_", " ").title()


def _infer_demographics(archetype: str, units: list[Any]) -> dict[str, Any]:
    """Infer demographic attributes for a persona."""
    roles: list[str] = []
    domains: set[str] = set()

    for unit in units:
        domain = getattr(unit, "domain", "")
        if domain:
            domains.add(domain)
        buyer = getattr(unit, "buyer", "")
        if buyer:
            roles.append(buyer)

    return {
        "role": archetype.replace("_", " ").title(),
        "domains": sorted(domains),
        "buyer_roles": sorted(set(roles))[:5],
        "experience_level": _guess_experience_level(units, archetype),
    }


def _guess_experience_level(units: list[Any], archetype: str) -> str:
    """Heuristic for experience level based on unit complexity."""
    if not units:
        return "mid-level"

    avg_quality = sum(getattr(u, "quality_score", 0.0) for u in units) / len(units)
    if avg_quality > 0.7:
        return "senior"
    elif avg_quality > 0.4:
        return "mid-level"
    return "junior"


def _extract_goals(units: list[Any]) -> list[str]:
    """Extract user goals from value propositions and solutions."""
    goals: list[str] = []

    for unit in units:
        vp = getattr(unit, "value_proposition", "")
        if vp and vp not in goals:
            goals.append(vp)

    return goals[:10]


def _extract_pain_points(units: list[Any], signals: list[Any]) -> list[str]:
    """Extract pain points from problems and signal content."""
    pain_points: list[str] = []

    for unit in units:
        problem = getattr(unit, "problem", "")
        if problem and problem not in pain_points:
            pain_points.append(problem)

        workaround = getattr(unit, "current_workaround", "")
        if workaround and workaround not in pain_points:
            pain_points.append(f"Current workaround: {workaround}")

    # Supplement from signals with pain-point language
    for signal in signals:
        content_lower = signal.content.lower()
        if any(kw in content_lower for kw in _PAIN_POINT_INDICATORS):
            if signal.title not in pain_points:
                pain_points.append(signal.title)

    return pain_points[:15]


def _extract_motivations(units: list[Any], signals: list[Any]) -> list[str]:
    """Extract motivations from why-now rationale and signal content."""
    motivations: list[str] = []

    for unit in units:
        why_now = getattr(unit, "why_now", "")
        if why_now and why_now not in motivations:
            motivations.append(why_now)

    # Supplement from signals with motivation language
    for signal in signals:
        content_lower = signal.content.lower()
        if any(kw in content_lower for kw in _MOTIVATION_INDICATORS):
            if signal.title not in motivations:
                motivations.append(signal.title)

    return motivations[:10]


def _extract_tech_preferences(
    signals: list[Any],
    units: list[Any],
) -> dict[str, Any]:
    """Extract technology preferences from signals and unit tech stacks."""
    tech_counter: Counter[str] = Counter()

    # Count tech mentions in signals
    for signal in signals:
        text = (signal.title + " " + signal.content).lower()
        for kw in _TECH_KEYWORDS:
            if kw in text:
                tech_counter[kw] += 1

    # Count from suggested stacks
    for unit in units:
        stack = getattr(unit, "suggested_stack", {})
        if isinstance(stack, dict):
            for value in stack.values():
                val_lower = str(value).lower()
                for kw in _TECH_KEYWORDS:
                    if kw in val_lower:
                        tech_counter[kw] += 1

    # Collect tags
    tag_counter: Counter[str] = Counter()
    for signal in signals:
        for tag in signal.tags:
            tag_counter[tag.lower()] += 1

    top_techs = [t for t, _ in tech_counter.most_common(10)]
    top_tags = [t for t, _ in tag_counter.most_common(10)]

    return {
        "technologies": top_techs,
        "tags": top_tags,
    }


def _extract_behavior_patterns(signals: list[Any]) -> list[str]:
    """Infer behavior patterns from signal source types and metadata."""
    source_counts: Counter[str] = Counter()
    for signal in signals:
        source_counts[str(signal.source_type)] += 1

    patterns: list[str] = []
    for source_type, count in source_counts.most_common(5):
        patterns.append(f"Engages with {source_type} content ({count} signals)")

    if not patterns:
        patterns.append("No specific behavior patterns detected")

    return patterns


def _render_persona_markdown(index: int, persona: dict[str, Any]) -> list[str]:
    """Render a single persona as markdown sections."""
    lines: list[str] = []
    lines.extend([
        f"## Persona {index}: {persona['name']}",
        "",
        f"**Archetype**: {persona['archetype']}",
        "",
    ])

    # Demographics
    demo = persona["demographics"]
    lines.extend([
        "### Demographics",
        "",
        f"- **Role**: {demo['role']}",
        f"- **Experience level**: {demo['experience_level']}",
    ])
    if demo["domains"]:
        lines.append(f"- **Domains**: {', '.join(demo['domains'])}")
    if demo["buyer_roles"]:
        lines.append(f"- **Buyer roles**: {', '.join(demo['buyer_roles'])}")
    lines.append("")

    # Goals
    lines.extend(["### Goals", ""])
    if persona["goals"]:
        for goal in persona["goals"]:
            lines.append(f"- {goal}")
    else:
        lines.append("- No specific goals identified")
    lines.append("")

    # Pain Points
    lines.extend(["### Pain Points", ""])
    if persona["pain_points"]:
        for pp in persona["pain_points"]:
            lines.append(f"- {pp}")
    else:
        lines.append("- No specific pain points identified")
    lines.append("")

    # Motivations
    lines.extend(["### Motivations", ""])
    if persona["motivations"]:
        for m in persona["motivations"]:
            lines.append(f"- {m}")
    else:
        lines.append("- No specific motivations identified")
    lines.append("")

    # Technology Preferences
    tech = persona["technology_preferences"]
    lines.extend(["### Technology Preferences", ""])
    if tech["technologies"]:
        lines.append(f"- **Technologies**: {', '.join(tech['technologies'])}")
    if tech["tags"]:
        lines.append(f"- **Topics**: {', '.join(tech['tags'])}")
    if not tech["technologies"] and not tech["tags"]:
        lines.append("- No specific technology preferences detected")
    lines.append("")

    # Behavior Patterns
    lines.extend(["### Behavior Patterns", ""])
    for bp in persona["behavior_patterns"]:
        lines.append(f"- {bp}")
    lines.append("")

    # Evidence
    ev = persona["evidence"]
    lines.extend([
        "### Evidence",
        "",
        f"- Based on {ev['unit_count']} buildable units and {ev['signal_count']} signals",
        "",
    ])

    return lines
