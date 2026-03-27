"""Prompts for the evaluation engine."""

from max.evaluation.weights import DIMENSION_DESCRIPTIONS

SYSTEM = """\
You are a utility evaluation engine for developer tool and AI infrastructure ideas. \
Your job is to rigorously score ideas across 7 dimensions.

Be calibrated: a score of 5 is average, 7+ is notably good, 3- is notably poor. \
Don't cluster scores around 6-7 — use the full range.

For INVERTED dimensions (build_effort, competitive_density), a HIGH score means \
FAVORABLE conditions (easy to build, few competitors).

Provide specific reasoning for each dimension — cite evidence, not platitudes.

When supporting evidence is provided, fact-check the idea's claims against it. \
Score with HIGHER confidence when evidence directly validates a dimension, and \
LOWER confidence when evidence is thin or tangential.
"""


def build_evaluation_prompt(
    unit_json: str,
    *,
    evidence_json: str | None = None,
) -> str:
    dims_text = "\n".join(
        f"- {name}: {desc}" for name, desc in DIMENSION_DESCRIPTIONS.items()
    )

    evidence_block = ""
    if evidence_json:
        evidence_block = f"""

SUPPORTING EVIDENCE (signals and insights that inspired this idea):
{evidence_json}

When scoring, fact-check the idea's claims against this evidence:
- Does the evidence support the stated problem severity?
- Is the claimed addressable scale substantiated?
- Score LOWER confidence when evidence is thin or tangential.
- Score HIGHER confidence when evidence directly validates a dimension.
"""

    return f"""\
Evaluate this buildable unit idea across 7 utility dimensions.

IDEA:
{unit_json}
{evidence_block}
DIMENSIONS (score each 0-10):
{dims_text}

For each dimension, provide:
- value: numeric score 0-10
- confidence: how sure you are about this score (0.0-1.0)
- reasoning: specific evidence-based justification (2-3 sentences)

Also provide:
- strengths: 2-3 key strengths of this idea
- weaknesses: 2-3 key weaknesses or risks
- recommendation: one of strong_yes | yes | maybe | no | strong_no\
"""
