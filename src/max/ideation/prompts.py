"""Prompts for the ideation engine (insights → buildable units)."""

SYSTEM = """\
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


def build_ideation_prompt(
    insights_json: str,
    *,
    existing_ideas_text: str | None = None,
    gaps_text: str | None = None,
) -> str:
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
Generate buildable project ideas based on these insights from the developer/AI ecosystem.
{existing_block}{gaps_block}
INSIGHTS:
{insights_json}

For each idea:
1. Link it to specific insight IDs that inspired it
2. Clearly state the problem and proposed solution
3. Identify target users (humans, agents, or both)
4. Articulate the value proposition
5. Sketch the technical approach
6. Note composability — how it could integrate with other tools/systems

Generate 3-5 distinct ideas. Favor ideas that:
- Address pain points with high severity
- Serve dual audiences (humans AND agents)
- Have high composability with existing ecosystems (MCP, tact, etc.)
- Can be built and shipped as focused, well-scoped projects\
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
) -> str:
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
{existing_block}{gaps_block}
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
