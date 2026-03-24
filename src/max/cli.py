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
def run(output: str, signal_limit: int, min_score: float) -> None:
    """Run the full pipeline: fetch → synthesize → ideate → evaluate → publish."""
    from max.pipeline.runner import run_pipeline

    output_dir = Path(output)
    click.echo("Running max pipeline...")
    click.echo(f"  Output:       {output_dir.resolve()}")
    click.echo(f"  Signal limit: {signal_limit}")
    click.echo(f"  Min score:    {min_score}")
    click.echo()

    result = run_pipeline(
        output_dir=output_dir,
        signal_limit=signal_limit,
        min_score=min_score,
    )

    click.echo(f"Signals fetched:    {result.signals_fetched} ({result.signals_new} new)")
    click.echo(f"Insights generated: {result.insights_generated}")
    click.echo(f"Ideas generated:    {result.ideas_generated}")
    click.echo(f"Ideas evaluated:    {result.ideas_evaluated}")
    click.echo(f"Specs generated:    {result.specs_generated}")
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
