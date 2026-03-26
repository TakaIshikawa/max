"""CLI interface for max."""

from __future__ import annotations

from pathlib import Path

import click



@click.group()
@click.version_option(package_name="max")
def main() -> None:
    """Max — Generalized idea generation engine."""


@main.command()
@click.option("--output", "-o", type=click.Path(), default=".tact", help="Output directory for tact specs")
@click.option("--signal-limit", type=int, default=30, help="Max signals per adapter")
@click.option("--min-score", type=float, default=50.0, help="Minimum score to generate spec")
@click.option("--profile", type=str, default="default", help="Weight profile: default, quick_wins, moonshots, ecosystem, agent_first")
@click.option("--mode", type=click.Choice(["direct", "refinement", "cross_domain", "all"]), default="direct", help="Ideation mode")
def run(output: str, signal_limit: int, min_score: float, profile: str, mode: str) -> None:
    """Run the full pipeline: fetch → synthesize → ideate → evaluate → publish."""
    from max.pipeline.runner import run_pipeline

    output_dir = Path(output)
    click.echo("Running max pipeline...")
    click.echo(f"  Output:       {output_dir.resolve()}")
    click.echo(f"  Signal limit: {signal_limit}")
    click.echo(f"  Min score:    {min_score}")
    click.echo(f"  Profile:      {profile}")
    click.echo(f"  Mode:         {mode}")
    click.echo()

    result = run_pipeline(
        output_dir=output_dir,
        signal_limit=signal_limit,
        min_score=min_score,
        weight_profile=profile,
        ideation_mode=mode,
    )

    click.echo(f"Signals fetched:    {result.signals_fetched} ({result.signals_new} new)")
    click.echo(f"Insights generated: {result.insights_generated} (avg confidence: {result.avg_insight_confidence:.2f})")
    click.echo(f"Ideas generated:    {result.ideas_generated}")
    click.echo(f"Ideas evaluated:    {result.ideas_evaluated} (avg score: {result.avg_idea_score:.1f})")
    click.echo(f"Specs generated:    {result.specs_generated}")
    if result.token_usage:
        total = result.token_usage.get("total", 0)
        click.echo(f"Token usage:        {total:,} (in: {result.token_usage.get('total_input', 0):,}, out: {result.token_usage.get('total_output', 0):,})")
    click.echo()

    if result.top_ideas:
        click.echo("Top ideas:")
        for idea in result.top_ideas:
            marker = "✓" if idea["score"] >= min_score else " "
            click.echo(f"  [{marker}] {idea['score']:5.1f}  {idea['title']}  ({idea['recommendation']})")


@main.command()
@click.option("--status", type=str, default=None, help="Filter by status")
@click.option("--limit", type=int, default=20, help="Max results")
def ideas(status: str | None, limit: int) -> None:
    """List generated ideas with scores."""
    from max.store.db import Store

    store = Store()
    try:
        units = store.get_buildable_units(limit=limit, status=status)
        if not units:
            click.echo("No ideas found.")
            return

        for unit in units:
            evaluation = store.get_evaluation(unit.id)
            score = evaluation.overall_score if evaluation else 0.0
            rec = evaluation.recommendation if evaluation else "-"
            click.echo(f"  {score:5.1f}  [{unit.status:10s}]  {unit.title}  ({rec})  {unit.id}")
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
        click.echo(f"Category:    {unit.category.value}")
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
def serve(host: str | None, port: int | None, reload: bool) -> None:
    """Start the REST API + MCP server."""
    import uvicorn

    from max.config import MAX_HOST, MAX_PORT

    bind_host = host or MAX_HOST
    bind_port = port or MAX_PORT

    click.echo(f"Starting max server on {bind_host}:{bind_port}")
    click.echo(f"  REST API: http://{bind_host}:{bind_port}/api/v1")
    click.echo(f"  MCP:      http://{bind_host}:{bind_port}/mcp")
    click.echo()

    uvicorn.run(
        "max.server.app:create_app",
        host=bind_host,
        port=bind_port,
        reload=reload,
        factory=True,
    )
