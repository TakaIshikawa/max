"""Domain quality rubric helpers."""

from __future__ import annotations

from max.profiles.schema import DomainContext, DomainQualityConfig


def rubric_context_text(domain: DomainContext | None, config: DomainQualityConfig | None) -> str:
    """Format rubric and memory hints for future prompt conditioning."""
    if not domain or not config or not config.enabled:
        return ""

    lines = [
        f"Domain quality rubric for {domain.name}:",
        f"- Minimum domain quality score: {config.min_score:.1f}/100",
    ]
    if config.required_fields:
        lines.append("- Required fields: " + ", ".join(config.required_fields))
    if config.preferred_patterns:
        lines.append("- Prefer patterns: " + "; ".join(config.preferred_patterns[:8]))
    if config.rejected_patterns:
        lines.append("- Avoid patterns: " + "; ".join(config.rejected_patterns[:8]))
    if domain.good_idea_criteria:
        lines.append("- Good idea criteria: " + "; ".join(domain.good_idea_criteria[:8]))
    if domain.bad_idea_patterns:
        lines.append("- Bad idea patterns: " + "; ".join(domain.bad_idea_patterns[:8]))
    return "\n".join(lines)
