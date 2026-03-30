"""Prompts for the synthesis engine (signals → insights)."""

SYSTEM = """\
You are a technology analyst specializing in developer tools, AI/agent ecosystems, \
and infrastructure. Your job is to synthesize raw signals into actionable insights.

An insight is a higher-level pattern, gap, pain point, trend, or convergence that \
emerges from multiple signals. Each insight must be grounded in specific signal evidence.

Each signal has a `signal_role` indicating what it represents:
- problem: pain points, bugs, vulnerabilities, unmet needs
- solution: packages, tools, repos being built
- market: attention, funding, adoption momentum

Cross-reference problem signals against solution signals to find gaps. \
Insights backed by signals from multiple roles are higher confidence.

Categories:
- pain_point: A recurring developer/user frustration
- gap: A missing capability in the ecosystem
- trend: A directional shift gaining momentum
- vulnerability: A systemic weakness or risk
- convergence: Multiple independent signals pointing to the same opportunity
- emerging_pattern: A nascent pattern not yet widely recognized
"""


def build_synthesis_prompt(
    signals_json: str,
    *,
    cluster_context: str | None = None,
) -> str:
    cluster_block = ""
    if cluster_context:
        cluster_block = f"""

CROSS-SOURCE CORROBORATION:
{cluster_context}

Signals in multi-source clusters are independently corroborated — weight them more heavily.
"""

    return f"""\
Analyze these signals from the developer/AI ecosystem and synthesize them into insights.

SIGNALS:
{signals_json}
{cluster_block}
For each insight you identify:
1. Ground it in specific signal IDs from the input
2. Assess confidence (0.0-1.0) based on evidence strength
3. Identify which domains it affects
4. State implications for what could be built
5. Estimate time horizon (near_term: <6mo, medium_term: 6-18mo, long_term: >18mo)

Return a list of 3-7 insights. Prioritize non-obvious connections over surface-level observations.\
"""


def build_incremental_synthesis_prompt(
    signals_json: str,
    prior_insights_json: str,
    *,
    cluster_context: str | None = None,
) -> str:
    cluster_block = ""
    if cluster_context:
        cluster_block = f"""

CROSS-SOURCE CORROBORATION:
{cluster_context}

Signals in multi-source clusters are independently corroborated — weight them more heavily.
"""

    return f"""\
Analyze these NEW signals from the developer/AI ecosystem and synthesize them into insights.

EXISTING INSIGHTS (from prior analysis — do NOT restate these):
{prior_insights_json}

NEW SIGNALS:
{signals_json}
{cluster_block}
Generate NEW insights that complement or build on the existing ones. Focus on:
1. What the new signals reveal that existing insights don't cover
2. How new signals strengthen, weaken, or evolve existing insight themes
3. New connections between the new signals and patterns from prior analysis

For each insight:
1. Ground it in specific signal IDs from the NEW SIGNALS input
2. Assess confidence (0.0-1.0) based on evidence strength
3. Identify which domains it affects
4. State implications for what could be built
5. Estimate time horizon (near_term: <6mo, medium_term: 6-18mo, long_term: >18mo)

Return a list of 3-7 insights. Do not duplicate existing insights — only add genuinely new observations.\
"""
