from __future__ import annotations

from max.analysis import (
    generate_persona_interview_guide,
    render_persona_interview_guide_markdown,
)
from max.types.buildable_unit import BuildableUnit


def test_persona_interview_guide_infers_multiple_personas(sample_unit) -> None:
    sample_unit.target_users = "platform engineer, security reviewer"
    sample_unit.buyer = "VP of Engineering"

    guide = generate_persona_interview_guide(
        sample_unit,
        _evidence_chain(),
        profile_context={"personas": [{"name": "release manager"}]},
    )

    persona_names = [persona["name"] for persona in guide["personas"]]
    assert persona_names == [
        "Mcp Server Maintainer",
        "Platform Engineer",
        "Security Reviewer",
        "Vp Of Engineering",
        "Release Manager",
        "Compliance Lead",
    ]

    for persona in guide["personas"]:
        assert list(persona["sections"]) == [
            "problem_severity",
            "current_workaround",
            "buying_process",
            "risk_compliance",
            "validation_next_steps",
        ]
        assert all(section["questions"] for section in persona["sections"].values())


def test_persona_interview_guide_has_fallback_persona_without_target_users() -> None:
    unit = BuildableUnit(
        id="bu-persona-minimal",
        title="Minimal Discovery Export",
        one_liner="Create a discovery guide",
        category="feature",
        problem="The team lacks a customer discovery script.",
        solution="Generate persona interview prompts.",
        target_users="",
        value_proposition="Make demand validation easier.",
        domain="developer-tools",
    )

    guide = generate_persona_interview_guide(unit, None)

    assert len(guide["personas"]) == 1
    assert guide["personas"][0]["name"] == "Developer Tools Practitioner"
    assert guide["personas"][0]["sections"]["problem_severity"]["questions"][0] == (
        "How often do you encounter this problem: The team lacks a customer discovery script.?"
    )


def test_persona_interview_guide_markdown_preserves_evidence_titles_and_urls(sample_unit) -> None:
    guide = generate_persona_interview_guide(sample_unit, _evidence_chain())
    markdown = render_persona_interview_guide_markdown(guide)

    assert "## Evidence References" in markdown
    assert (
        "- forum:sig-persona-001 - Security teams want release approvals - "
        "https://example.com/security-approval"
    ) in markdown
    assert (
        "- survey:sig-persona-002 - Maintainers report manual test fatigue - "
        "https://example.com/test-fatigue"
    ) in markdown
    assert "Which evidence should we verify next: Security teams want release approvals; Maintainers report manual test fatigue?" in markdown


def test_render_persona_interview_guide_markdown_is_stable(sample_unit) -> None:
    first = generate_persona_interview_guide(sample_unit, _evidence_chain())
    second = generate_persona_interview_guide(sample_unit, _evidence_chain())

    assert first == second
    assert render_persona_interview_guide_markdown(first) == render_persona_interview_guide_markdown(second)
    assert render_persona_interview_guide_markdown(first).startswith(
        "# Persona Interview Guide: MCP Test Framework\n\n"
    )


def _evidence_chain() -> dict[str, object]:
    return {
        "signals": [
            {
                "id": "sig-persona-001",
                "source_type": "forum",
                "signal_role": "problem",
                "title": "Security teams want release approvals",
                "url": "https://example.com/security-approval",
                "tags": ["persona:compliance lead"],
                "metadata": {"persona": "compliance lead"},
            },
            {
                "id": "sig-persona-002",
                "source_type": "survey",
                "signal_role": "market",
                "title": "Maintainers report manual test fatigue",
                "url": "https://example.com/test-fatigue",
                "metadata": {"target_user": "MCP server maintainer"},
            },
        ]
    }
