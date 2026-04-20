"""Prompts for the ideation engine (insights → buildable units)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from max.profiles.schema import DomainContext

_DEFAULT_SYSTEM = """\
You are a product ideation engine for the developer tools and AI agent ecosystem. \
Your job is to generate concrete, buildable project ideas from synthesized insights.

Every idea must:
- Solve a real problem backed by evidence
- Serve developers, AI agents, or both
- Be buildable as a focused project (not a platform or framework)
- Have a clear value proposition

Categories:
- mcp_server: An MCP-compatible tool server
- cli_tool: A command-line utility
- library: A reusable code package
- integration: Connects two or more existing systems
- automation: Automates a manual workflow
- application: A standalone application
- feature: An enhancement to an existing system

Target users: humans | agents | both
"""

# Keep SYSTEM as module-level constant for backward compat
SYSTEM = _DEFAULT_SYSTEM


def get_system_prompt(domain: DomainContext | None = None) -> str:
    """Get the ideation system prompt, optionally parameterized by domain."""
    if domain is None:
        return _DEFAULT_SYSTEM
    categories_text = "\n".join(f"- {cat}" for cat in domain.categories)
    target_text = " | ".join(domain.target_user_types)
    constraints_text = "\n".join(f"- {c}" for c in domain.hard_constraints)
    bad_patterns_text = "\n".join(f"- {p}" for p in domain.bad_idea_patterns)
    criteria_text = "\n".join(f"- {c}" for c in domain.good_idea_criteria)
    quality_blocks = ""
    if constraints_text:
        quality_blocks += f"\n\nHard constraints:\n{constraints_text}"
    if bad_patterns_text:
        quality_blocks += f"\n\nAvoid these weak idea patterns:\n{bad_patterns_text}"
    if criteria_text:
        quality_blocks += f"\n\nGood ideas should satisfy:\n{criteria_text}"
    extra = f"\n\n{domain.extra_instructions}" if domain.extra_instructions else ""
    return f"""\
You are a product ideation engine for {domain.description}. \
Your job is to generate concrete, buildable project ideas from synthesized insights.

Every idea must:
- Solve a real problem backed by evidence
- Serve {target_text}
- Be buildable as a focused project (not a platform or framework)
- Have a clear value proposition

Categories:
{categories_text}

Target users: {target_text}\
{quality_blocks}\
{extra}
"""


def build_ideation_prompt(
    insights_json: str,
    *,
    existing_ideas_text: str | None = None,
    gaps_text: str | None = None,
    learned_context: str | None = None,
    domain: DomainContext | None = None,
) -> str:
    learned_block = ""
    if learned_context:
        learned_block = f"""
{learned_context}

"""

    existing_block = ""
    if existing_ideas_text:
        existing_block = f"""
EXISTING IDEAS (do NOT regenerate these — generate DIFFERENT ideas):
{existing_ideas_text}

"""

    gaps_block = ""
    if gaps_text:
        gaps_block = f"""
{gaps_text}

"""

    domain_label = f"the {domain.name} domain" if domain else "the developer/AI ecosystem"
    target_label = " | ".join(domain.target_user_types) if domain else "humans, agents, or both"
    domain_focus = ""
    if domain:
        focus_lines = []
        if domain.target_segments:
            focus_lines.append(f"Target segments: {', '.join(domain.target_segments)}")
        if domain.workflows:
            focus_lines.append(f"Workflows: {', '.join(domain.workflows)}")
        if domain.buyer_roles:
            focus_lines.append(f"Buyer roles: {', '.join(domain.buyer_roles)}")
        if focus_lines:
            domain_focus = "DOMAIN FOCUS:\n" + "\n".join(focus_lines) + "\n\n"

    return f"""\
Generate buildable project ideas based on these insights from {domain_label}.
{learned_block}{existing_block}{gaps_block}{domain_focus}
INSIGHTS:
{insights_json}

For each idea:
1. Link it to specific insight IDs that inspired it
2. Clearly state the problem and proposed solution
3. Identify target users ({target_label})
4. Articulate the value proposition
5. Sketch the technical approach
6. Note composability — how it could integrate with other tools/systems
7. Identify the specific user, buyer, workflow moment, current workaround, why now, validation plan, first 10 customers, domain risks, and evidence rationale

Generate 3-5 distinct ideas. Favor ideas that:
- Address pain points with high severity
- Serve the broadest relevant audience
- Have high composability with existing ecosystems
- Can be built and shipped as focused, well-scoped projects
- Are specific enough to test with real users within 2 weeks
- Avoid generic assistants, dashboards, marketplaces, and ideas without a clear buyer\
"""


def build_refinement_prompt(existing_units_json: str, new_insights_json: str) -> str:
    return f"""\
You are refining existing project ideas based on new evidence. \
Review each existing idea against the new insights. For each idea, either:
- IMPROVE it with new evidence, sharper framing, or expanded scope
- PIVOT it if new insights suggest a better direction for the core problem
- KEEP it unchanged if it's already well-positioned

EXISTING IDEAS:
{existing_units_json}

NEW INSIGHTS:
{new_insights_json}

For each refined idea:
1. Reference the original idea's ID
2. Explain what changed and why
3. Link to the new insight IDs that prompted the refinement
4. Update the problem/solution/value proposition as needed
5. Update the technical approach if the refinement warrants it

Return 2-4 refined ideas. Only refine ideas where new insights materially \
improve or redirect them — don't refine for the sake of refining.\
"""


def build_cross_domain_prompt(
    domain_a_insights_json: str,
    domain_b_insights_json: str,
    *,
    existing_ideas_text: str | None = None,
    gaps_text: str | None = None,
    learned_context: str | None = None,
    domain: DomainContext | None = None,
) -> str:
    learned_block = ""
    if learned_context:
        learned_block = f"""
{learned_context}

"""

    existing_block = ""
    if existing_ideas_text:
        existing_block = f"""
EXISTING IDEAS (do NOT regenerate these — generate DIFFERENT ideas):
{existing_ideas_text}

"""

    gaps_block = ""
    if gaps_text:
        gaps_block = f"""
{gaps_text}

"""

    return f"""\
Generate novel project ideas by combining insights from TWO DIFFERENT domains. \
The best ideas come from applying solutions from one domain to problems in another.
{learned_block}{existing_block}{gaps_block}
DOMAIN A INSIGHTS:
{domain_a_insights_json}

DOMAIN B INSIGHTS:
{domain_b_insights_json}

For each idea:
1. Identify which insight from Domain A and which from Domain B inspired it
2. Explain the cross-domain connection — what pattern or solution transfers
3. State the problem and proposed solution
4. Identify target users (humans, agents, or both)
5. Articulate why this cross-domain combination is non-obvious and valuable
6. Sketch the technical approach
7. Note composability

Generate 2-4 cross-domain ideas. Prioritize ideas where:
- The combination is genuinely non-obvious (not just feature bundling)
- The cross-domain transfer creates a 1+1=3 effect
- The resulting idea is still focused and buildable\
"""
