"""CLI interface for max."""

from __future__ import annotations

from pathlib import Path

import click



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
        total = result.token_usage.get("total", 0)
        click.echo(f"Token usage:        {total:,} (in: {result.token_usage.get('total_input', 0):,}, out: {result.token_usage.get('total_output', 0):,})")
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
