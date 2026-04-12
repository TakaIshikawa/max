"""CLI interface for max."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from max.types.buildable_unit import BuildableUnit
    from max.types.evaluation import UtilityEvaluation



@click.group()
@click.version_option(package_name="max")
def main() -> None:
    """Max — Generalized idea generation engine."""


@main.command()
@click.option("--profile", "-p", type=str, default=None, help="Pipeline profile name (e.g. 'devtools', 'healthcare')")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output directory for tact specs")
@click.option("--signal-limit", type=int, default=None, help="Max signals per adapter")
@click.option("--min-score", type=float, default=None, help="Minimum score to generate spec")
@click.option("--weight-profile", type=str, default=None, help="Weight profile: default, quick_wins, moonshots, ecosystem, agent_first")
@click.option("--mode", type=click.Choice(["direct", "refinement", "cross_domain", "all"]), default=None, help="Ideation mode")
def run(
    profile: str | None,
    output: str | None,
    signal_limit: int | None,
    min_score: float | None,
    weight_profile: str | None,
    mode: str | None,
) -> None:
    """Run the full pipeline: fetch → synthesize → ideate → evaluate → publish."""
    from max.config import MAX_PROFILE
    from max.pipeline.runner import run_pipeline
    from max.profiles.loader import get_default_profile, load_profile

    # Resolve profile: CLI flag > env var > default
    profile_name = profile or MAX_PROFILE or None
    if profile_name:
        p = load_profile(profile_name)
    else:
        p = get_default_profile()

    # CLI flags override profile values
    if signal_limit is not None:
        p.signal_limit = signal_limit
    if min_score is not None:
        p.evaluation.min_score = min_score
    if weight_profile is not None:
        p.evaluation.weight_profile = weight_profile
    if mode is not None:
        p.ideation_mode = mode

    output_dir = Path(output) if output else Path(p.output_dir)

    click.echo("Running max pipeline...")
    click.echo(f"  Profile:      {p.name}")
    click.echo(f"  Domain:       {p.domain.name}")
    click.echo(f"  Output:       {output_dir.resolve()}")
    click.echo(f"  Signal limit: {p.signal_limit}")
    click.echo(f"  Min score:    {p.evaluation.min_score}")
    click.echo(f"  Weights:      {p.evaluation.weight_profile}")
    click.echo(f"  Mode:         {p.ideation_mode}")
    click.echo()

    result = run_pipeline(
        profile=p,
        output_dir=output_dir,
    )

    click.echo(f"Signals fetched:    {result.signals_fetched} ({result.signals_new} new, {result.signals_skipped} already synthesized)")
    click.echo(f"Insights generated: {result.insights_generated} ({result.insights_duplicates_skipped} duplicates skipped, avg confidence: {result.avg_insight_confidence:.2f})")
    click.echo(f"Ideas generated:    {result.ideas_generated} ({result.ideas_duplicates_skipped} duplicates skipped)")
    click.echo(f"Ideas evaluated:    {result.ideas_evaluated} (avg score: {result.avg_idea_score:.1f})")
    click.echo(f"Specs generated:    {result.specs_generated}")
    if result.token_usage:
        total_input = result.token_usage.get("total_input", 0)
        total_output = result.token_usage.get("total_output", 0)
        cost = result.estimated_cost_usd
        click.echo(f"Token usage:        {total_input:,}in / {total_output:,}out (~${cost:.4f})")
    if result.budget_exceeded:
        click.echo("⚠️  Budget exceeded - pipeline stopped early with partial results")
    click.echo()

    if result.top_ideas:
        click.echo("Top ideas:")
        for idea in result.top_ideas:
            marker = "✓" if idea["score"] >= p.evaluation.min_score else " "
            click.echo(f"  [{marker}] {idea['score']:5.1f}  {idea['title']}  ({idea['recommendation']})")


@main.command()
def profiles() -> None:
    """List available pipeline profiles."""
    from max.profiles.loader import list_profiles, load_profile

    names = list_profiles()
    if not names:
        click.echo("No profiles found in profiles/ directory.")
        return

    click.echo("Available pipeline profiles:")
    click.echo()
    for name in sorted(names):
        try:
            p = load_profile(name)
            sources_count = len([s for s in p.sources if s.enabled])
            click.echo(f"  {name:20s}  {p.domain.name:20s}  {p.domain.description[:50]}")
            click.echo(f"  {'':20s}  sources: {sources_count}  categories: {len(p.domain.categories)}")
        except Exception as e:
            click.echo(f"  {name:20s}  (error: {e})")
    click.echo()
    click.echo("Usage: max run --profile <name>")


@main.command()
@click.option("--status", type=str, default=None, help="Filter by status")
@click.option("--domain", "-d", type=str, default=None, help="Filter by domain (e.g. 'healthcare', 'fintech')")
@click.option("--limit", type=int, default=20, help="Max results")
def ideas(status: str | None, domain: str | None, limit: int) -> None:
    """List generated ideas with scores."""
    from max.store.db import Store

    store = Store()
    try:
        units = store.get_buildable_units(limit=limit, status=status, domain=domain)
        if not units:
            click.echo("No ideas found.")
            return

        for unit in units:
            evaluation = store.get_evaluation(unit.id)
            score = evaluation.overall_score if evaluation else 0.0
            rec = evaluation.recommendation if evaluation else "-"
            domain_label = f"[{unit.domain}]" if unit.domain else ""
            click.echo(f"  {score:5.1f}  [{unit.status:10s}]  {domain_label:16s}  {unit.title}  ({rec})  {unit.id}")
    finally:
        store.close()


@main.command()
@click.argument("unit_id")
def inspect(unit_id: str) -> None:
    """Inspect a buildable unit with its evaluation."""
    from max.store.db import Store

    store = Store()
    try:
        unit = store.get_buildable_unit(unit_id)
        if not unit:
            click.echo(f"Not found: {unit_id}")
            return

        click.echo(f"Title:       {unit.title}")
        click.echo(f"One-liner:   {unit.one_liner}")
        click.echo(f"Category:    {unit.category}")
        click.echo(f"Status:      {unit.status}")
        click.echo(f"Target:      {unit.target_users}")
        click.echo()
        click.echo(f"Problem:     {unit.problem}")
        click.echo(f"Solution:    {unit.solution}")
        click.echo(f"Value Prop:  {unit.value_proposition}")
        click.echo()

        evaluation = store.get_evaluation(unit.id)
        if evaluation:
            click.echo(f"Overall Score: {evaluation.overall_score}")
            click.echo(f"Recommendation: {evaluation.recommendation}")
            click.echo()
            for dim_name in [
                "pain_severity", "addressable_scale", "build_effort",
                "composability", "competitive_density", "timing_fit", "compounding_value",
            ]:
                dim: object = getattr(evaluation, dim_name)
                click.echo(f"  {dim_name:22s}  {dim.value:4.1f}  (conf: {dim.confidence:.2f})  {dim.reasoning[:80]}")

            if evaluation.strengths:
                click.echo()
                click.echo("Strengths:")
                for s in evaluation.strengths:
                    click.echo(f"  + {s}")
            if evaluation.weaknesses:
                click.echo("Weaknesses:")
                for w in evaluation.weaknesses:
                    click.echo(f"  - {w}")
    finally:
        store.close()


@main.command()
@click.argument("unit_id")
@click.option("--output", "-o", type=click.Path(), default=".tact", help="Output directory")
@click.option("--dry-run", is_flag=True, help="Print spec JSON instead of writing files")
def publish(unit_id: str, output: str, dry_run: bool) -> None:
    """Generate and publish a tact spec for a buildable unit."""
    from max.publisher.file_writer import write_tact_spec
    from max.spec.generator import generate_spec
    from max.store.db import Store

    store = Store()
    try:
        unit = store.get_buildable_unit(unit_id)
        if not unit:
            click.echo(f"Not found: {unit_id}")
            return

        evaluation = store.get_evaluation(unit_id)
        if not evaluation:
            click.echo(f"No evaluation for {unit_id}. Run the pipeline first.")
            return

        # Check if spec already exists
        existing = store.get_tact_spec(unit_id)
        if existing:
            spec = existing
            click.echo(f"Using existing spec for {unit.title}")
        else:
            click.echo(f"Generating spec for: {unit.title}")
            spec = generate_spec(unit, evaluation)
            store.insert_tact_spec(spec)

        if dry_run:
            click.echo(spec.model_dump_json(indent=2, by_alias=True))
        else:
            output_dir = Path(output) / spec.product.name
            write_tact_spec(spec, output_dir)
            click.echo(f"Written to: {output_dir.resolve()}")
            store.update_buildable_unit_status(unit_id, "published")
    finally:
        store.close()


@main.command()
@click.argument("unit_id")
@click.argument("outcome", type=click.Choice(["approved", "rejected", "published", "abandoned"]))
@click.option("--reason", "-r", type=str, default="", help="Reason for the feedback")
def feedback(unit_id: str, outcome: str, reason: str) -> None:
    """Record feedback on a buildable unit (approved/rejected/published/abandoned)."""
    from max.store.db import Store

    store = Store()
    try:
        unit = store.get_buildable_unit(unit_id)
        if not unit:
            click.echo(f"Not found: {unit_id}")
            return

        store.insert_feedback(unit_id, outcome, reason)
        store.update_buildable_unit_status(unit_id, outcome)
        click.echo(f"Recorded: {unit.title} → {outcome}")
    finally:
        store.close()


@main.command()
@click.option("--domain", "-d", type=str, default=None, help="Filter by domain")
@click.option("--approve-threshold", type=float, default=68.0, help="Auto-approve score threshold (default: 68)")
@click.option("--reject-threshold", type=float, default=50.0, help="Auto-reject score threshold (default: 50)")
@click.option("--dry-run", is_flag=True, help="Show what would be triaged without applying changes")
@click.option("--limit", type=int, default=500, help="Max ideas to consider")
def triage(domain: str | None, approve_threshold: float, reject_threshold: float, dry_run: bool, limit: int) -> None:
    """Auto-approve/reject ideas by score thresholds.

    Default thresholds: auto-approve >= 68 with rec=yes, auto-reject < 50 or rec=no.
    Remaining ideas are left for human review.
    """
    from max.store.db import Store

    store = Store()
    try:
        units = store.get_buildable_units(limit=limit, domain=domain)
        if not units:
            click.echo("No ideas found.")
            return

        auto_approved = []
        auto_rejected = []
        pending = []

        for unit in units:
            ev = store.get_evaluation(unit.id)
            if not ev:
                continue
            if store.has_feedback(unit.id):
                continue

            if ev.overall_score >= approve_threshold and ev.recommendation == "yes":
                auto_approved.append((unit, ev))
            elif ev.overall_score < reject_threshold or ev.recommendation == "no":
                auto_rejected.append((unit, ev))
            else:
                pending.append((unit, ev))

        if not auto_approved and not auto_rejected:
            click.echo("No ideas matched triage thresholds.")
            click.echo(f"  {len(pending)} ideas remain for manual review.")
            return

        # Display results
        if auto_approved:
            click.echo(f"Auto-approve ({len(auto_approved)} ideas, score >= {approve_threshold} + rec=yes):")
            for unit, ev in auto_approved:
                domain_label = f"[{unit.domain}]" if unit.domain else ""
                click.echo(f"  {ev.overall_score:5.1f}  {domain_label:16s}  {unit.title}")

        if auto_rejected:
            click.echo(f"Auto-reject ({len(auto_rejected)} ideas, score < {reject_threshold} or rec=no):")
            for unit, ev in auto_rejected:
                domain_label = f"[{unit.domain}]" if unit.domain else ""
                click.echo(f"  {ev.overall_score:5.1f}  {domain_label:16s}  {unit.title}")

        click.echo(f"\nPending manual review: {len(pending)} ideas")

        if dry_run:
            click.echo("\nDRY RUN: No changes applied.")
            return

        # Apply triage
        for unit, ev in auto_approved:
            store.insert_feedback(unit.id, "approved", "auto-triage: score >= threshold + rec=yes")
            store.update_buildable_unit_status(unit.id, "approved")
        for unit, ev in auto_rejected:
            reason = f"auto-triage: score={ev.overall_score:.1f}, rec={ev.recommendation}"
            store.insert_feedback(unit.id, "rejected", reason)
            store.update_buildable_unit_status(unit.id, "rejected")

        click.echo(f"\nApplied: {len(auto_approved)} approved, {len(auto_rejected)} rejected")
    finally:
        store.close()


@main.command()
@click.option("--threshold", type=float, default=0.85, help="Similarity threshold for clustering (default: 0.85)")
@click.option("--domain", "-d", type=str, default=None, help="Filter by domain")
@click.option("--dry-run", is_flag=True, help="Show duplicates without marking them")
@click.option("--limit", type=int, default=500, help="Max ideas to consider")
def dedup(threshold: float, domain: str | None, dry_run: bool, limit: int) -> None:
    """Find and mark duplicate ideas across domains.

    Clusters ideas by semantic similarity. Within each cluster, keeps the
    highest-scored idea and marks others as duplicates.
    """
    from max.analysis.dedup import cluster_ideas
    from max.store.db import Store

    store = Store()
    try:
        units = store.get_buildable_units(limit=limit, domain=domain)
        if not units:
            click.echo("No ideas found.")
            return

        # Build (unit, eval) pairs — only evaluated, non-duplicate ideas
        ideas = []
        for unit in units:
            if unit.status == "duplicate":
                continue
            ev = store.get_evaluation(unit.id)
            if not ev:
                continue
            ideas.append((unit, ev))

        if not ideas:
            click.echo("No evaluated ideas to cluster.")
            return

        clusters = cluster_ideas(ideas, similarity_threshold=threshold)

        # Filter to clusters with >1 member (actual duplicates)
        dup_clusters = [c for c in clusters if c.size > 1]

        if not dup_clusters:
            click.echo(f"No duplicates found at threshold {threshold}.")
            click.echo(f"  {len(clusters)} unique ideas across {len(ideas)} evaluated.")
            return

        total_dups = sum(len(c.duplicates) for c in dup_clusters)
        click.echo(f"Found {len(dup_clusters)} clusters with {total_dups} duplicates:\n")

        for i, cluster in enumerate(dup_clusters, 1):
            rep = cluster.representative
            rep_ev = cluster.representative_eval
            rep_score = rep_ev.overall_score if rep_ev else 0.0
            click.echo(f"  Cluster {i} ({cluster.size} ideas, domains: {', '.join(sorted(cluster.domains))})")
            click.echo(f"    KEEP: {rep_score:5.1f}  [{rep.domain}]  {rep.title}")
            for unit, ev in cluster.duplicates:
                score = ev.overall_score if ev else 0.0
                click.echo(f"    DUP:  {score:5.1f}  [{unit.domain}]  {unit.title}")
            click.echo()

        if dry_run:
            click.echo("DRY RUN: No changes applied.")
            return

        # Mark duplicates
        marked = 0
        for cluster in dup_clusters:
            for unit, ev in cluster.duplicates:
                reason = f"duplicate of {cluster.representative.id} ({cluster.representative.title[:50]})"
                store.insert_feedback(unit.id, "rejected", f"auto-dedup: {reason}")
                store.update_buildable_unit_status(unit.id, "duplicate")
                marked += 1

        click.echo(f"Marked {marked} ideas as duplicate.")
    finally:
        store.close()


@main.command(name="prior-art")
@click.option("--domain", "-d", type=str, default=None, help="Filter by domain")
@click.option("--limit", type=int, default=80, help="Max ideas to check")
@click.option("--re-scan", is_flag=True, help="Re-check ideas that already have results")
@click.option("--auto-reject", is_flag=True, help="Auto-reject ideas with strong matches")
@click.option("--dry-run", is_flag=True, help="Show queries without making API calls")
def prior_art(domain: str | None, limit: int, re_scan: bool, auto_reject: bool, dry_run: bool) -> None:
    """Check for existing implementations matching generated ideas.

    Searches GitHub, npm, PyPI, and Product Hunt for prior art.
    Results are stored and surfaced during `max review`.
    """
    from max.analysis.prior_art import (
        build_search_queries,
        check_prior_art,
        select_sources,
    )
    from max.store.db import Store

    store = Store()
    try:
        # Get ideas to check
        units = store.get_buildable_units(limit=limit, domain=domain)
        if not re_scan:
            units = [u for u in units if u.prior_art_status == "unchecked"]

        # Filter to evaluated/approved (not rejected/duplicate)
        units = [u for u in units if u.status not in ("rejected", "duplicate")]

        if not units:
            click.echo("No ideas to check.")
            return

        click.echo(f"Checking prior art for {len(units)} ideas...")

        if dry_run:
            for unit in units:
                queries = build_search_queries(unit)
                sources = select_sources(unit)
                click.echo(f"\n  {unit.title}")
                click.echo(f"    Sources: {', '.join(sources)}")
                for q in queries:
                    click.echo(f"    Query: {q}")
            click.echo(f"\nDry run — {len(units)} ideas would be checked.")
            return

        # Clear old matches if re-scanning
        if re_scan:
            for unit in units:
                store.delete_prior_art_matches(unit.id)

        results = check_prior_art(units, dry_run=False)

        strong_count = 0
        weak_count = 0
        clear_count = 0

        for result in results:
            unit = next(u for u in units if u.id == result.buildable_unit_id)

            # Store matches
            for match in result.matches:
                store.insert_prior_art_match(unit.id, {
                    "source": match.source,
                    "title": match.title,
                    "url": match.url,
                    "description": match.description,
                    "relevance_score": match.relevance_score,
                    "match_signals": match.match_signals,
                    "search_query": match.search_query,
                })

            # Update status
            store.update_prior_art_status(unit.id, result.status)

            if result.status == "strong_match":
                strong_count += 1
                click.echo(f"\n  [!!] {unit.title}")
                for m in result.matches[:3]:
                    signals = ""
                    if m.source == "github":
                        signals = f"({m.match_signals.get('stars', 0)} stars)"
                    elif m.source == "npm":
                        signals = ""
                    elif m.source == "product_hunt":
                        signals = f"({m.match_signals.get('votes', 0)} votes)"
                    click.echo(
                        f"       {m.relevance_score:.2f}  {m.source:<13} {m.title} {signals}"
                    )
                    click.echo(f"       {m.url}")

                if auto_reject:
                    store.insert_feedback(unit.id, "rejected", "auto-rejected: strong prior art match")
                    store.update_buildable_unit_status(unit.id, "rejected")
                    click.echo("       -> auto-rejected")

            elif result.status == "weak_match":
                weak_count += 1
                click.echo(f"  [~]  {unit.title}  ({len(result.matches)} weak matches)")

            else:
                clear_count += 1

        click.echo(f"\nResults: {strong_count} strong, {weak_count} weak, {clear_count} clear")

        if auto_reject and strong_count:
            click.echo(f"Auto-rejected {strong_count} ideas with strong prior art matches.")
    finally:
        store.close()


@main.command()
@click.option("--domain", "-d", type=str, default=None, help="Filter by domain")
@click.option("--min-score", type=float, default=0.0, help="Minimum score to include")
@click.option("--limit", type=int, default=50, help="Max ideas to review")
@click.option("--threshold", type=float, default=0.85, help="Similarity threshold for clustering (default: 0.85)")
def review(domain: str | None, min_score: float, limit: int, threshold: float) -> None:
    """Interactively review ideas in clusters.

    Similar ideas are grouped together for batch review. For each cluster:
    [a] approve best idea, reject rest  [A] approve all in cluster
    [r] reject entire cluster  [p] pick individually  [s] skip  [q] quit
    """
    from max.analysis.dedup import cluster_ideas
    from max.evaluation.weights import adapt_weights as do_adapt, get_weights
    from max.store.db import Store

    store = Store()
    try:
        units = store.get_buildable_units(limit=limit * 3, domain=domain)
        if not units:
            click.echo("No ideas found.")
            return

        # Build review queue: evaluated, no feedback yet, sorted by score desc
        queue = []
        for unit in units:
            ev = store.get_evaluation(unit.id)
            if not ev:
                continue
            if ev.overall_score < min_score:
                continue
            if store.has_feedback(unit.id):
                continue
            queue.append((unit, ev))

        queue.sort(key=lambda x: x[1].overall_score, reverse=True)
        queue = queue[:limit]

        if not queue:
            click.echo("No ideas pending review (all have feedback or don't meet criteria).")
            return

        # Cluster similar ideas for batch review
        clusters = cluster_ideas(queue, similarity_threshold=threshold)

        multi = [c for c in clusters if c.size > 1]
        singles = [c for c in clusters if c.size == 1]

        click.echo(f"Review queue: {len(queue)} ideas in {len(clusters)} clusters")
        click.echo(f"  {len(multi)} clusters with similar ideas, {len(singles)} individual ideas")
        if domain:
            click.echo(f"  Domain: {domain}")
        click.echo()

        approved = 0
        rejected = 0
        skipped = 0
        quit_review = False

        for ci, cluster in enumerate(clusters, 1):
            if quit_review:
                break

            rep = cluster.representative
            rep_ev = cluster.representative_eval

            if cluster.size == 1:
                # Single idea — standard review
                click.echo(f"--- [{ci}/{len(clusters)}] {'─' * 60}")
                _display_idea_card(rep, rep_ev)

                choice = _single_review_prompt(store, rep, rep_ev)
                if choice == "approved":
                    approved += 1
                elif choice == "rejected":
                    rejected += 1
                elif choice == "quit":
                    quit_review = True
                else:
                    skipped += 1
            else:
                # Cluster — batch review
                click.echo(f"=== Cluster [{ci}/{len(clusters)}] ({cluster.size} similar ideas) {'═' * 40}")
                click.echo(f"  Domains: {', '.join(sorted(cluster.domains))}")
                click.echo()

                # Show representative (best)
                click.echo("  BEST:")
                _display_idea_card(rep, rep_ev, indent=4)

                # Show other members
                for unit, ev in cluster.duplicates:
                    score = ev.overall_score if ev else 0.0
                    rec = ev.recommendation if ev else "-"
                    click.echo(f"    also: {score:5.1f} ({rec})  [{unit.domain}]  {unit.title}")

                click.echo()

                while True:
                    choice = click.prompt(
                        "  [a]pprove best, reject rest  [A]pprove all  [r]eject all  [p]ick individually  [s]kip  [q]uit",
                        type=str,
                        default="s",
                    ).strip()

                    if choice == "a":
                        # Approve best, reject rest
                        reason = click.prompt("  Reason (optional)", default="", show_default=False)
                        store.insert_feedback(rep.id, "approved", reason)
                        store.update_buildable_unit_status(rep.id, "approved")
                        approved += 1
                        for unit, ev in cluster.duplicates:
                            store.insert_feedback(unit.id, "rejected", f"cluster-review: kept {rep.id}")
                            store.update_buildable_unit_status(unit.id, "rejected")
                            rejected += 1
                        click.echo(f"  -> approved best, rejected {len(cluster.duplicates)} others")
                        break
                    elif choice == "A":
                        # Approve all in cluster
                        reason = click.prompt("  Reason (optional)", default="", show_default=False)
                        for unit, ev in cluster.members:
                            store.insert_feedback(unit.id, "approved", reason)
                            store.update_buildable_unit_status(unit.id, "approved")
                            approved += 1
                        click.echo(f"  -> approved all {cluster.size} ideas")
                        break
                    elif choice in ("r", "R"):
                        reason = click.prompt("  Reason (optional)", default="", show_default=False)
                        for unit, ev in cluster.members:
                            store.insert_feedback(unit.id, "rejected", reason)
                            store.update_buildable_unit_status(unit.id, "rejected")
                            rejected += 1
                        click.echo(f"  -> rejected all {cluster.size} ideas")
                        break
                    elif choice in ("p", "P"):
                        # Fall back to individual review for each member
                        for unit, ev in cluster.members:
                            click.echo()
                            _display_idea_card(unit, ev)
                            result = _single_review_prompt(store, unit, ev)
                            if result == "approved":
                                approved += 1
                            elif result == "rejected":
                                rejected += 1
                            elif result == "quit":
                                quit_review = True
                                break
                            else:
                                skipped += 1
                        break
                    elif choice in ("s", "S"):
                        skipped += cluster.size
                        break
                    elif choice in ("q", "Q"):
                        quit_review = True
                        break
                    else:
                        click.echo("  Invalid choice. Use a/A/r/p/s/q.")

            click.echo()

        # Summary
        click.echo()
        click.echo(f"Review complete: {approved} approved, {rejected} rejected, {skipped} skipped")

        # Auto-adapt weights if we have enough feedback diversity
        if approved > 0 and rejected > 0:
            outcomes = store.get_feedback_outcomes()
            success_count = sum(1 for o in outcomes if o.get("success"))
            failure_count = len(outcomes) - success_count
            if success_count > 0 and failure_count > 0:
                base = get_weights("default")
                adapted = do_adapt(outcomes, base)
                click.echo()
                click.echo(f"Weight adaptation ({len(outcomes)} total feedback):")
                for dim, weight in adapted.items():
                    base_w = base.get(dim, 0)
                    delta = weight - base_w
                    if abs(delta) > 0.001:
                        marker = "+" if delta > 0 else ""
                        click.echo(f"  {dim:22s}  {weight:.4f}  ({marker}{delta:.4f})")
                click.echo("  (weights auto-apply on next pipeline run)")
        elif approved > 0 or rejected > 0:
            total_outcomes = store.get_feedback_outcomes()
            click.echo(f"\n{len(total_outcomes)} total feedback records. Need both approved + rejected for weight adaptation.")
    finally:
        store.close()


def _display_idea_card(
    unit: BuildableUnit, ev: UtilityEvaluation | None, *, indent: int = 2
) -> None:
    """Display a compact idea card for review."""
    pad = " " * indent
    score = ev.overall_score if ev else 0.0
    rec = ev.recommendation if ev else "-"
    pa_tag = ""
    if unit.prior_art_status == "strong_match":
        pa_tag = " [!!]"
    elif unit.prior_art_status == "weak_match":
        pa_tag = " [~]"
    click.echo(f"{pad}{score:5.1f}  ({rec})  [{unit.domain}] {unit.category}{pa_tag}")
    click.echo(f"{pad}{unit.title}")
    click.echo(f"{pad}{unit.one_liner}")
    click.echo()
    click.echo(f"{pad}Problem:  {unit.problem}")
    click.echo(f"{pad}Solution: {unit.solution}")

    if ev:
        dims = [
            ("pain", ev.pain_severity.value),
            ("scale", ev.addressable_scale.value),
            ("effort", ev.build_effort.value),
            ("compose", ev.composability.value),
            ("compete", ev.competitive_density.value),
            ("timing", ev.timing_fit.value),
            ("compound", ev.compounding_value.value),
        ]
        dims.sort(key=lambda x: x[1], reverse=True)
        top3 = "  ".join(f"{name}={val:.0f}" for name, val in dims[:3])
        bot2 = "  ".join(f"{name}={val:.0f}" for name, val in dims[-2:])
        click.echo(f"{pad}Strongest: {top3}    Weakest: {bot2}")
    click.echo()


def _single_review_prompt(store, unit: BuildableUnit, ev: UtilityEvaluation | None) -> str:
    """Run single-idea review prompt. Returns 'approved', 'rejected', 'skipped', or 'quit'."""
    while True:
        choice = click.prompt(
            "  [a]pprove  [r]eject  [s]kip  [d]etail  [q]uit",
            type=str,
            default="s",
        ).strip().lower()

        if choice in ("a", "approve"):
            reason = click.prompt("  Reason (optional)", default="", show_default=False)
            store.insert_feedback(unit.id, "approved", reason)
            store.update_buildable_unit_status(unit.id, "approved")
            click.echo("  -> approved")
            return "approved"
        elif choice in ("r", "reject"):
            reason = click.prompt("  Reason (optional)", default="", show_default=False)
            store.insert_feedback(unit.id, "rejected", reason)
            store.update_buildable_unit_status(unit.id, "rejected")
            click.echo("  -> rejected")
            return "rejected"
        elif choice in ("s", "skip"):
            return "skipped"
        elif choice in ("d", "detail"):
            click.echo()
            click.echo(f"  Value Prop:  {unit.value_proposition}")
            click.echo(f"  Tech:        {unit.tech_approach}")
            click.echo(f"  Target:      {unit.target_users}")
            click.echo()
            if ev and ev.strengths:
                for s in ev.strengths:
                    click.echo(f"  + {s}")
            if ev and ev.weaknesses:
                for w in ev.weaknesses:
                    click.echo(f"  - {w}")
            # Show prior art matches if any
            if unit.prior_art_status in ("strong_match", "weak_match"):
                pa_matches = store.get_prior_art_matches(unit.id)
                if pa_matches:
                    label = "!!" if unit.prior_art_status == "strong_match" else "~"
                    click.echo(f"  Prior Art [{label}]:")
                    for m in pa_matches[:5]:
                        click.echo(f"    {m['relevance_score']:.2f}  {m['source']:<13} {m['title']}")
                        click.echo(f"    {m['url']}")
            click.echo()
            # Loop back to prompt
        elif choice in ("q", "quit"):
            return "quit"
        else:
            click.echo("  Invalid choice. Use a/r/s/d/q.")


@main.command()
@click.option("--limit", type=int, default=20, help="Max records to show")
def feedback_log(limit: int) -> None:
    """Show recent feedback history."""
    from max.store.db import Store

    store = Store()
    try:
        records = store.get_feedback_log(limit=limit)
        if not records:
            click.echo("No feedback recorded yet.")
            return

        click.echo(f"{'Outcome':<10s} {'Score':>5s} {'Domain':<16s} {'Title':<50s} {'Reason'}")
        click.echo("-" * 110)
        for r in records:
            score = f"{r['score']:.1f}" if r["score"] else "  -"
            domain = f"[{r['domain']}]" if r["domain"] else ""
            reason = r["reason"][:30] if r["reason"] else ""
            click.echo(f"{r['outcome']:<10s} {score:>5s} {domain:<16s} {r['title'][:50]:<50s} {reason}")

        # Summary counts
        approved = sum(1 for r in records if r["outcome"] in ("approved", "published"))
        rejected = sum(1 for r in records if r["outcome"] in ("rejected", "abandoned"))
        click.echo(f"\n{len(records)} records: {approved} approved, {rejected} rejected")
    finally:
        store.close()


@main.command()
@click.option("--base-profile", type=str, default="default", help="Base weight profile to adapt from")
@click.option("--save", type=click.Path(), default=None, help="Save adapted weights to file")
def adapt_weights(base_profile: str, save: str | None) -> None:
    """Adapt evaluation weights based on feedback history."""
    from max.evaluation.weights import adapt_weights as do_adapt, get_weights, save_weights
    from max.store.db import Store

    store = Store()
    try:
        outcomes = store.get_feedback_outcomes()
        if not outcomes:
            click.echo("No feedback recorded yet. Use 'max feedback <id> approved/rejected' first.")
            return

        base = get_weights(base_profile)
        adapted = do_adapt(outcomes, base)

        click.echo(f"Adapted weights from {len(outcomes)} feedback records:")
        click.echo(f"  Base profile: {base_profile}")
        click.echo()
        for dim, weight in adapted.items():
            base_w = base.get(dim, 0)
            delta = weight - base_w
            marker = "+" if delta > 0 else ""
            click.echo(f"  {dim:22s}  {weight:.4f}  ({marker}{delta:.4f})")

        if save:
            save_weights(adapted, Path(save))
            click.echo(f"\nSaved to: {save}")
    finally:
        store.close()


@main.command()
def backfill_roles() -> None:
    """Backfill signal_role on signals that have no role classification."""
    from max.analysis.roles import classify_signal_role
    from max.store.db import Store

    store = Store()
    try:
        signals = store.get_signals(limit=1000)
        unclassified = [s for s in signals if not s.metadata.get("signal_role")]
        if not unclassified:
            click.echo("All signals already have roles.")
            return

        click.echo(f"Backfilling {len(unclassified)} unclassified signals...")
        for sig in unclassified:
            role = classify_signal_role(sig)
            sig.metadata["signal_role"] = role
            store.update_signal_role(sig.id, role)

        # Summary
        roles: dict[str, int] = {}
        for sig in unclassified:
            r = sig.metadata["signal_role"]
            roles[r] = roles.get(r, 0) + 1
        for role, count in sorted(roles.items(), key=lambda x: -x[1]):
            click.echo(f"  {role:10s} {count}")
        click.echo("Done.")
    finally:
        store.close()


@main.command()
def summary() -> None:
    """Show cross-domain summary of all ideas."""
    from max.store.db import Store

    store = Store()
    try:
        all_units = store.get_buildable_units(limit=10000)
        if not all_units:
            click.echo("No ideas found.")
            return

        # Group by domain
        by_domain: dict[str, list] = {}
        for unit in all_units:
            d = unit.domain or "(unassigned)"
            by_domain.setdefault(d, [])
            ev = store.get_evaluation(unit.id)
            by_domain[d].append((unit, ev))

        click.echo(f"{'Domain':<20s} {'Ideas':>5s} {'Eval':>5s} {'Avg':>6s} {'Top':>6s} {'Yes':>4s} {'Maybe':>5s} {'No':>4s}  {'Top idea'}")
        click.echo("-" * 110)

        grand_total = 0
        grand_evaluated = 0
        grand_scores: list[float] = []

        for domain in sorted(by_domain.keys()):
            entries = by_domain[domain]
            total = len(entries)
            scores = [ev.overall_score for _, ev in entries if ev]
            evaluated = len(scores)
            avg = sum(scores) / len(scores) if scores else 0.0
            top = max(scores) if scores else 0.0
            yes_count = sum(1 for _, ev in entries if ev and ev.recommendation == "yes")
            maybe_count = sum(1 for _, ev in entries if ev and ev.recommendation == "maybe")
            no_count = sum(1 for _, ev in entries if ev and ev.recommendation == "no")

            # Find top idea
            best = max(entries, key=lambda x: x[1].overall_score if x[1] else 0.0)
            best_title = best[0].title[:40]

            click.echo(
                f"{domain:<20s} {total:>5d} {evaluated:>5d} {avg:>6.1f} {top:>6.1f} {yes_count:>4d} {maybe_count:>5d} {no_count:>4d}  {best_title}"
            )

            grand_total += total
            grand_evaluated += evaluated
            grand_scores.extend(scores)

        click.echo("-" * 110)
        grand_avg = sum(grand_scores) / len(grand_scores) if grand_scores else 0.0
        grand_top = max(grand_scores) if grand_scores else 0.0
        click.echo(f"{'TOTAL':<20s} {grand_total:>5d} {grand_evaluated:>5d} {grand_avg:>6.1f} {grand_top:>6.1f}")
    finally:
        store.close()


@main.command()
@click.option("--windows", type=int, default=5, help="Number of trend windows to display")
@click.option("--window-size", type=int, default=5, help="Pipeline runs per window")
def trends(windows: int, window_size: int) -> None:
    """Show approval rate trends over recent pipeline runs."""
    from max.analysis.retrospective import detect_trends
    from max.store.db import Store

    store = Store()
    try:
        points = detect_trends(store, window=window_size)
        if not points:
            click.echo("Not enough pipeline runs to compute trends.")
            return

        # Show the last N windows.
        display = points[-windows:]

        click.echo(f"{'Window':<6s}  {'Start':>19s}  {'End':>19s}  {'Approval':>8s}  {'Avg Score':>9s}  {'Signals':>7s}  {'Trend'}")
        click.echo("-" * 90)

        for i, pt in enumerate(display, 1):
            start_str = pt.window_start.strftime("%Y-%m-%d %H:%M")
            end_str = pt.window_end.strftime("%Y-%m-%d %H:%M")
            click.echo(
                f"{i:<6d}  {start_str:>19s}  {end_str:>19s}"
                f"  {pt.approval_rate:>7.1%}  {pt.avg_score:>9.1f}  {pt.signal_count:>7d}  {pt.trend_direction}"
            )

        click.echo("-" * 90)
        if len(display) >= 2:
            first = display[0].approval_rate
            last = display[-1].approval_rate
            overall_delta = last - first
            if overall_delta > 0.05:
                summary_label = "improving"
            elif overall_delta < -0.05:
                summary_label = "declining"
            else:
                summary_label = "stable"
            click.echo(f"Overall: {summary_label} ({overall_delta:+.1%} over {len(display)} windows)")
    finally:
        store.close()


@main.command()
def backfill_domains() -> None:
    """Backfill domain on buildable units using pipeline run timestamps."""
    from max.store.db import Store

    store = Store()
    try:
        # Get pipeline runs with profile info
        runs = store.get_pipeline_runs(limit=200)
        runs_with_profile = [
            r for r in runs
            if r["ideas_generated"] > 0 and r["config"].get("profile")
        ]

        if not runs_with_profile:
            click.echo("No pipeline runs with profile info found.")
            return

        updated = 0
        for run in runs_with_profile:
            profile = run["config"]["profile"]
            started = run["started_at"]
            completed = run["completed_at"] or "9999-12-31"

            # Find BUs created during this run's window that have no domain set
            rows = store.conn.execute(
                """UPDATE buildable_units
                   SET domain = ?
                   WHERE domain = '' AND created_at >= ? AND created_at <= ?""",
                (profile, started, completed),
            )
            count = rows.rowcount
            if count > 0:
                updated += count
                click.echo(f"  {profile:20s}  {count} ideas updated")

        store.conn.commit()

        # Check for remaining unassigned
        remaining = store.conn.execute(
            "SELECT COUNT(*) FROM buildable_units WHERE domain = ''"
        ).fetchone()[0]

        click.echo(f"\nBackfilled {updated} ideas. {remaining} remain unassigned.")
    finally:
        store.close()


@main.command()
@click.option("--days", type=int, default=None, help="Days before archival (default: MAX_RETENTION_DAYS or 90)")
@click.option("--purge", is_flag=True, help="Also purge archived records older than 180 days")
@click.option("--purge-days", type=int, default=180, help="Days before purging archived records (default: 180)")
@click.option("--dry-run", is_flag=True, help="Show what would be archived/purged without modifying data")
def archive(days: int | None, purge: bool, purge_days: int, dry_run: bool) -> None:
    """Archive old records and optionally purge archived data."""
    from max.config import MAX_RETENTION_DAYS
    from max.store.db import Store

    archive_days = days if days is not None else MAX_RETENTION_DAYS

    store = Store()
    try:
        if dry_run:
            click.echo(f"DRY RUN: Showing what would be affected (--days={archive_days})")
            click.echo()

            # Show current stats
            stats = store.retention_stats()
            click.echo("Current retention status:")
            for table, counts in stats.items():
                click.echo(
                    f"  {table:20s}  total: {counts['total']:6d}  "
                    f"active: {counts['active']:6d}  archived: {counts['archived']:6d}"
                )
            click.echo()

            # Estimate what would be archived
            from datetime import datetime, timedelta, timezone

            cutoff = (datetime.now(timezone.utc) - timedelta(days=archive_days)).isoformat()

            # Count synthesized signals older than cutoff
            sig_count = store.conn.execute(
                """SELECT COUNT(*) FROM signals
                   WHERE archived_at IS NULL
                   AND synthesized_at IS NOT NULL
                   AND fetched_at < ?""",
                (cutoff,),
            ).fetchone()[0]

            # Count old pipeline runs
            run_count = store.conn.execute(
                """SELECT COUNT(*) FROM pipeline_runs
                   WHERE archived_at IS NULL AND started_at < ?""",
                (cutoff,),
            ).fetchone()[0]

            # Count archivable insights (simplified estimate)
            ins_count = store.conn.execute(
                """SELECT COUNT(*) FROM insights
                   WHERE archived_at IS NULL AND created_at < ?""",
                (cutoff,),
            ).fetchone()[0]

            click.echo(f"Would archive (records older than {archive_days} days):")
            click.echo(f"  signals:       {sig_count:6d} (synthesized only)")
            click.echo(f"  insights:      {ins_count:6d} (estimate, actual may be less)")
            click.echo(f"  pipeline_runs: {run_count:6d}")
            click.echo()

            if purge:
                purge_cutoff = (
                    datetime.now(timezone.utc) - timedelta(days=purge_days)
                ).isoformat()

                sig_del = store.conn.execute(
                    """SELECT COUNT(*) FROM signals
                       WHERE archived_at IS NOT NULL AND archived_at < ?""",
                    (purge_cutoff,),
                ).fetchone()[0]

                ins_del = store.conn.execute(
                    """SELECT COUNT(*) FROM insights
                       WHERE archived_at IS NOT NULL AND archived_at < ?""",
                    (purge_cutoff,),
                ).fetchone()[0]

                run_del = store.conn.execute(
                    """SELECT COUNT(*) FROM pipeline_runs
                       WHERE archived_at IS NOT NULL AND archived_at < ?""",
                    (purge_cutoff,),
                ).fetchone()[0]

                click.echo(f"Would purge (archived > {purge_days} days ago):")
                click.echo(f"  signals:       {sig_del:6d}")
                click.echo(f"  insights:      {ins_del:6d}")
                click.echo(f"  pipeline_runs: {run_del:6d}")

            click.echo("\nRun without --dry-run to apply changes.")
            return

        # Actual archival
        click.echo(f"Archiving records older than {archive_days} days...")
        result = store.archive_old_records(days=archive_days)
        click.echo(f"  signals:       {result['signals_archived']:6d} archived")
        click.echo(f"  insights:      {result['insights_archived']:6d} archived")
        click.echo(f"  pipeline_runs: {result['runs_archived']:6d} archived")
        click.echo()

        if purge:
            click.echo(f"Purging archived records older than {purge_days} days...")
            purge_result = store.purge_archived(before_days=purge_days)
            click.echo(f"  signals:       {purge_result['signals_deleted']:6d} deleted")
            click.echo(f"  insights:      {purge_result['insights_deleted']:6d} deleted")
            click.echo(f"  pipeline_runs: {purge_result['runs_deleted']:6d} deleted")
            click.echo()

        # Show final stats
        stats = store.retention_stats()
        click.echo("Retention status after changes:")
        for table, counts in stats.items():
            click.echo(
                f"  {table:20s}  total: {counts['total']:6d}  "
                f"active: {counts['active']:6d}  archived: {counts['archived']:6d}"
            )
    finally:
        store.close()


@main.command()
@click.argument("unit_id")
@click.option("--tact-url", type=str, default="http://localhost:4800/api/v1", help="Tact daemon URL")
def push(unit_id: str, tact_url: str) -> None:
    """Push a spec to the tact daemon via REST API."""
    from max.publisher.tact_api import push_to_tact_sync
    from max.store.db import Store

    store = Store()
    try:
        spec = store.get_tact_spec(unit_id)
        if not spec:
            click.echo(f"No spec for {unit_id}. Run 'max publish {unit_id}' first.")
            return

        click.echo(f"Pushing {spec.product.name} to {tact_url}...")
        results = push_to_tact_sync(spec, tact_url=tact_url)

        for endpoint, success in results.items():
            status = "ok" if success else "FAILED"
            click.echo(f"  {endpoint}: {status}")
    finally:
        store.close()


@main.command()
@click.option("--host", type=str, default=None, help="Bind host (default: MAX_HOST or 0.0.0.0)")
@click.option("--port", type=int, default=None, help="Bind port (default: MAX_PORT or 8000)")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
@click.option("--schedule-interval", type=int, default=None, help="Pipeline schedule interval in seconds (default: 21600 = 6h)")
@click.option("--no-schedule", is_flag=True, help="Disable scheduled pipeline runs")
def serve(host: str | None, port: int | None, reload: bool, schedule_interval: int | None, no_schedule: bool) -> None:
    """Start the REST API + MCP server with scheduled pipeline runs."""
    import os

    import uvicorn

    # Set env vars BEFORE importing config (app factory reads them fresh)
    if schedule_interval is not None:
        os.environ["MAX_SCHEDULE_INTERVAL"] = str(schedule_interval)
    if no_schedule:
        os.environ["MAX_SCHEDULE_ENABLED"] = "false"

    from max.config import MAX_HOST, MAX_PORT

    bind_host = host or MAX_HOST
    bind_port = port or MAX_PORT

    schedule_label = "disabled" if no_schedule else f"every {schedule_interval or int(os.getenv('MAX_SCHEDULE_INTERVAL', '21600'))}s"
    click.echo(f"Starting max server on {bind_host}:{bind_port}")
    click.echo(f"  REST API:  http://{bind_host}:{bind_port}/api/v1")
    click.echo(f"  MCP:       http://{bind_host}:{bind_port}/mcp")
    click.echo(f"  Scheduler: {schedule_label}")
    click.echo()

    uvicorn.run(
        "max.server.app:create_app",
        host=bind_host,
        port=bind_port,
        reload=reload,
        factory=True,
    )
