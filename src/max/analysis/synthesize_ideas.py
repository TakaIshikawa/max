"""Idea synthesis — merge clustered ideas into superior combined ideas."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from max.analysis.dedup import IdeaCluster
from max.llm.client import structured_call
from max.types.buildable_unit import BuildableUnit, IdeationMode

logger = logging.getLogger(__name__)


# ── Pydantic output schemas ─────────────────────────────────────

class SynthesizedIdeaOutput(BaseModel):
    title: str
    one_liner: str
    category: str
    problem: str
    solution: str
    target_users: str = "both"
    value_proposition: str
    inspiring_insights: list[str] = Field(default_factory=list)
    tech_approach: str = ""
    suggested_stack: dict = Field(default_factory=dict)
    composability_notes: str = ""
    synthesis_rationale: str = ""


class IntraClusterOutput(BaseModel):
    synthesized_idea: SynthesizedIdeaOutput


class ComplementaryGroup(BaseModel):
    idea_ids: list[str]
    complementarity_reason: str
    combined_value_proposition: str
    synergy_score: float = 0.0


class CrossClusterDetectionOutput(BaseModel):
    complementary_groups: list[ComplementaryGroup] = Field(default_factory=list)


class CrossClusterSynthesisOutput(BaseModel):
    synthesized_idea: SynthesizedIdeaOutput


# ── Result dataclass ─────────────────────────────────────────────

@dataclass
class SynthesisResult:
    intra_synthesized: list[BuildableUnit] = field(default_factory=list)
    cross_synthesized: list[BuildableUnit] = field(default_factory=list)
    source_idea_ids: list[str] = field(default_factory=list)
    complementary_groups_found: int = 0
    skipped_clusters: int = 0


# ── Prompts ─────────────────────────────────��────────────────────

INTRA_CLUSTER_SYSTEM = """\
You are a product synthesis engine. Your job is to merge multiple similar \
project ideas into a single superior idea that combines the best elements \
of each source idea.

The resulting idea must:
- Take the strongest problem framing from any source
- Combine the best solution approaches where they complement each other
- Preserve the broadest target user scope
- Unify technical approaches into a coherent architecture
- Maintain all evidence traceability (include ALL inspiring insight IDs from all sources)
"""

CROSS_DETECTION_SYSTEM = """\
You are a product strategist. Your job is to identify groups of ideas \
that would be significantly more valuable when combined into a single product \
than they are separately. You are looking for genuine synergy, not just \
feature bundling or similarity.\
"""

CROSS_SYNTHESIS_SYSTEM = """\
You are a product synthesis engine. Your job is to merge complementary \
project ideas into a single cohesive product that captures the synergy \
between them. The ideas solve different aspects of a related problem, \
and combining them creates value greater than the sum of parts.\
"""


def _ideas_to_json(ideas: list[BuildableUnit]) -> str:
    """Serialize ideas to JSON for LLM input."""
    return json.dumps(
        [
            {
                "id": u.id,
                "title": u.title,
                "one_liner": u.one_liner,
                "category": u.category,
                "domain": u.domain,
                "problem": u.problem,
                "solution": u.solution,
                "target_users": u.target_users,
                "value_proposition": u.value_proposition,
                "inspiring_insights": u.inspiring_insights,
                "tech_approach": u.tech_approach,
                "suggested_stack": u.suggested_stack,
                "composability_notes": u.composability_notes,
            }
            for u in ideas
        ],
        indent=2,
    )


def _build_intra_cluster_prompt(ideas: list[BuildableUnit]) -> str:
    return f"""\
These {len(ideas)} ideas are semantically similar and address overlapping problems. \
Synthesize them into ONE superior idea that takes the best from each.

SOURCE IDEAS:
{_ideas_to_json(ideas)}

For the synthesized idea:
1. Pick the strongest problem framing — or combine framings if they're complementary
2. Merge solution approaches: keep components that complement each other, \
resolve conflicts by choosing the approach with better evidence backing
3. Unify the technical approach into a single coherent architecture
4. Combine ALL inspiring_insight IDs from all source ideas (union of all lists)
5. Write a synthesis_rationale explaining which elements you took from which \
source idea (reference by title) and why
6. The category should reflect the merged solution (may differ from any single source)
7. The value proposition should be stronger than any individual source idea

Do NOT simply pick one idea and discard the rest. \
The goal is a genuine synthesis that is better than any individual source.\
"""


def _build_cross_detection_prompt(
    ideas: list[BuildableUnit], *, max_groups: int = 5,
) -> str:
    return f"""\
Review these distinct project ideas. Identify groups of 2-4 ideas that are \
COMPLEMENTARY — meaning they solve different aspects of a related problem, \
and combining them creates synergy (1+1=3).

IDEAS:
{_ideas_to_json(ideas)}

For each complementary group:
1. List the idea IDs that compose well together
2. Explain WHY they are complementary (not just similar)
3. Describe the combined value proposition
4. Rate synergy (0.0-1.0): 1.0 means they are clearly parts of one product

Rules:
- An idea can appear in at most 2 groups
- Only report groups with synergy_score >= 0.6
- Ignore ideas that are simply similar (that's dedup's job) — \
look for complementary capabilities that together form a cohesive product
- Maximum {max_groups} groups

Return complementary_groups sorted by synergy_score descending.\
"""


def _build_cross_synthesis_prompt(
    ideas: list[BuildableUnit], group: ComplementaryGroup,
) -> str:
    return f"""\
These ideas have been identified as complementary. \
Synthesize them into ONE cohesive product idea.

SOURCE IDEAS:
{_ideas_to_json(ideas)}

COMPLEMENTARITY ASSESSMENT:
- Reason: {group.complementarity_reason}
- Combined value proposition: {group.combined_value_proposition}
- Synergy score: {group.synergy_score}

For the synthesized idea:
1. Frame the problem as the unified problem space that all ideas address
2. Design a solution that naturally integrates all approaches — \
not just bundling features
3. The architecture should have clear internal boundaries where each \
source idea's contribution lives
4. Combine ALL inspiring_insight IDs from all source ideas
5. Write a synthesis_rationale explaining the integration design
6. The value proposition should articulate the synergy — \
why this is more than the sum of parts

The synthesized idea should feel like a single coherent product, \
not separate products stapled together.\
"""


# ── Core functions ───────────────────────────────────────────────

def _output_to_unit(
    output: SynthesizedIdeaOutput,
    *,
    source_ideas: list[BuildableUnit],
    mode: IdeationMode,
) -> BuildableUnit:
    """Convert LLM output to BuildableUnit with proper traceability."""
    # Union all insight IDs and signal IDs from source ideas
    all_insights: set[str] = set()
    all_signals: set[str] = set()
    for u in source_ideas:
        all_insights.update(u.inspiring_insights)
        all_signals.update(u.evidence_signals)

    # Validate and include insights from LLM output
    if isinstance(output.inspiring_insights, list):
        all_insights.update(output.inspiring_insights)
    else:
        logger.warning(
            "Invalid inspiring_insights type in LLM output: %s, defaulting to empty list",
            type(output.inspiring_insights).__name__,
        )

    # Pick domain from most common among sources
    domains = [u.domain for u in source_ideas if u.domain]
    domain = max(set(domains), key=domains.count) if domains else ""

    # Validate target_users
    target_users = output.target_users
    if not target_users or target_users not in ("humans", "agents", "both"):
        if target_users and target_users not in ("humans", "agents", "both"):
            logger.warning(
                "Invalid target_users '%s' in LLM output, defaulting to 'both'",
                target_users,
            )
        target_users = "both"

    return BuildableUnit(
        title=output.title,
        one_liner=output.one_liner,
        category=output.category,
        ideation_mode=mode,
        problem=output.problem,
        solution=output.solution,
        target_users=target_users,
        value_proposition=output.value_proposition,
        inspiring_insights=sorted(all_insights),
        evidence_signals=sorted(all_signals),
        source_idea_ids=[u.id for u in source_ideas],
        tech_approach=output.tech_approach,
        suggested_stack=output.suggested_stack,
        composability_notes=output.composability_notes,
        domain=domain,
    )


def synthesize_cluster(cluster: IdeaCluster) -> BuildableUnit:
    """Merge all ideas in a multi-member cluster into one superior idea."""
    ideas = [u for u, _ in cluster.members]

    result = structured_call(
        system=INTRA_CLUSTER_SYSTEM,
        prompt=_build_intra_cluster_prompt(ideas),
        output_type=IntraClusterOutput,
        stage="synthesis_ideas",
    )

    return _output_to_unit(
        result.synthesized_idea,
        source_ideas=ideas,
        mode=IdeationMode.SYNTHESIS,
    )


def detect_complementary_groups(
    ideas: list[BuildableUnit],
    *,
    max_groups: int = 5,
) -> list[ComplementaryGroup]:
    """Identify groups of complementary ideas that compose well together."""
    if len(ideas) < 2:
        return []

    result = structured_call(
        system=CROSS_DETECTION_SYSTEM,
        prompt=_build_cross_detection_prompt(ideas, max_groups=max_groups),
        output_type=CrossClusterDetectionOutput,
        stage="synthesis_ideas",
    )

    # Filter to valid groups with synergy >= 0.6
    idea_ids = {u.id for u in ideas}
    valid: list[ComplementaryGroup] = []
    for group in result.complementary_groups:
        # Validate and clamp synergy_score
        original_score = group.synergy_score
        if not isinstance(original_score, (int, float)):
            logger.warning(
                "Non-numeric synergy_score '%s' for group %s, defaulting to 0.0",
                original_score, group.idea_ids,
            )
            group.synergy_score = 0.0
        else:
            clamped_score = max(0.0, min(1.0, float(original_score)))
            if clamped_score != original_score:
                logger.debug(
                    "Clamped synergy_score from %.2f to %.2f for group %s",
                    original_score, clamped_score, group.idea_ids,
                )
            group.synergy_score = clamped_score

        # Validate idea IDs and filter out invalid ones
        valid_idea_ids = [gid for gid in group.idea_ids if gid in idea_ids]
        invalid_ids = [gid for gid in group.idea_ids if gid not in idea_ids]
        if invalid_ids:
            logger.warning(
                "Filtered out invalid idea IDs from group: %s", invalid_ids,
            )

        if group.synergy_score >= 0.6 and len(valid_idea_ids) >= 2:
            group.idea_ids = valid_idea_ids
            valid.append(group)

    valid.sort(key=lambda g: g.synergy_score, reverse=True)
    return valid[:max_groups]


def synthesize_group(
    ideas: list[BuildableUnit],
    group: ComplementaryGroup,
) -> BuildableUnit:
    """Merge complementary ideas into one cohesive product."""
    result = structured_call(
        system=CROSS_SYNTHESIS_SYSTEM,
        prompt=_build_cross_synthesis_prompt(ideas, group),
        output_type=CrossClusterSynthesisOutput,
        stage="synthesis_ideas",
    )

    return _output_to_unit(
        result.synthesized_idea,
        source_ideas=ideas,
        mode=IdeationMode.CROSS_SYNTHESIS,
    )


def run_synthesis(
    clusters: list[IdeaCluster],
    *,
    cross_cluster: bool = False,
    max_cross_groups: int = 5,
    dry_run: bool = False,
) -> SynthesisResult:
    """Orchestrate the full synthesis flow.

    Phase 1: Intra-cluster synthesis (multi-member clusters only)
    Phase 2: Cross-cluster synthesis (opt-in, find complementary groups)
    """
    result = SynthesisResult()

    # Phase 1: intra-cluster
    multi_clusters = [c for c in clusters if c.size > 1]

    if dry_run:
        # Just record what would be synthesized
        for cluster in multi_clusters:
            for u, _ in cluster.members:
                result.source_idea_ids.append(u.id)
        return result

    for cluster in multi_clusters:
        try:
            new_unit = synthesize_cluster(cluster)
            result.intra_synthesized.append(new_unit)
            for u, _ in cluster.members:
                result.source_idea_ids.append(u.id)
        except Exception:
            result.skipped_clusters += 1
            logger.warning(
                "Failed to synthesize cluster (representative: %s)",
                cluster.representative.title,
                exc_info=True,
            )

    # Log summary if any clusters were skipped
    if result.skipped_clusters > 0:
        logger.info(
            "Intra-cluster synthesis complete: %d clusters processed, %d skipped due to errors",
            len(result.intra_synthesized), result.skipped_clusters,
        )

    # Phase 2: cross-cluster (opt-in)
    if cross_cluster:
        # Collect all singleton representatives + newly synthesized ideas
        candidates: list[BuildableUnit] = []
        for cluster in clusters:
            if cluster.size == 1:
                candidates.append(cluster.representative)
        candidates.extend(result.intra_synthesized)

        if len(candidates) >= 2:
            try:
                groups = detect_complementary_groups(
                    candidates, max_groups=max_cross_groups,
                )
                result.complementary_groups_found = len(groups)
            except Exception:
                logger.warning(
                    "Failed to detect complementary groups, continuing with empty groups",
                    exc_info=True,
                )
                groups = []
                result.complementary_groups_found = 0

            for group in groups:
                group_ideas = [
                    u for u in candidates if u.id in group.idea_ids
                ]
                if len(group_ideas) < 2:
                    continue
                try:
                    new_unit = synthesize_group(group_ideas, group)
                    result.cross_synthesized.append(new_unit)
                    for u in group_ideas:
                        if u.id not in result.source_idea_ids:
                            result.source_idea_ids.append(u.id)
                except Exception:
                    logger.warning(
                        "Failed to synthesize cross-cluster group: %s",
                        group.idea_ids,
                        exc_info=True,
                    )

    return result
