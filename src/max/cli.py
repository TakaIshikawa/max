"""CLI interface for max."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict
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
@click.option("--output", "-o", type=click.Path(), default=None, help="Output directory")
@click.option("--signal-limit", type=int, default=None, help="Max signals per adapter")
@click.option("--min-score", type=float, default=None, help="Minimum score to generate spec")
@click.option("--weight-profile", type=str, default=None, help="Weight profile: default, quick_wins, moonshots, ecosystem, agent_first")
@click.option("--mode", type=click.Choice(["direct", "refinement", "cross_domain", "all"]), default=None, help="Ideation mode")
@click.option("--quality-loop/--no-quality-loop", default=None, help="Run draft critique, revision, and quality gate before evaluation")
@click.option("--draft-count", type=int, default=None, help="Max draft ideas to pass through the quality loop")
@click.option("--dry-run", is_flag=True, help="Simulate execution without LLM calls or writes")
@click.option("--stages", type=str, default=None, help="Comma-separated list of stages to run (fetch,annotate,synthesize,detect_gaps,retrospective,ideate,evaluate)")
@click.option("--manifest", "--manifest-path", "manifest_path", type=click.Path(), default=None, help="Write a JSON run manifest to this file or directory")
@click.option("--include-all", is_flag=True, help="With --profile all, ignore focus filter and run every profile")
def run(
    profile: str | None,
    output: str | None,
    signal_limit: int | None,
    min_score: float | None,
    weight_profile: str | None,
    mode: str | None,
    quality_loop: bool | None,
    draft_count: int | None,
    dry_run: bool,
    stages: str | None,
    manifest_path: str | None,
    include_all: bool,
) -> None:
    """Run the full pipeline: fetch → synthesize → ideate → evaluate.

    Use --profile all to run across all configured domain profiles.
    With focus configured, out-of-focus profiles are skipped unless
    --include-all is passed.
    """
    from max.config import MAX_PROFILE
    from max.focus import focused_profile_names
    from max.profiles.loader import get_default_profile, list_profiles, load_profile

    # Parse stages parameter
    stages_list = None
    if stages:
        stages_list = [s.strip() for s in stages.split(',')]

    # Resolve profile: CLI flag > env var > default
    profile_name = profile or MAX_PROFILE or None

    if profile_name == "all":
        all_names = list_profiles()
        if not all_names:
            click.echo("No profiles found in profiles/ directory.")
            return

        names, skipped, focus_domains = focused_profile_names(include_all=include_all)
        if focus_domains is not None and skipped:
            click.echo(
                f"Focus domains: {', '.join(focus_domains)}. "
                f"Skipping {len(skipped)} out-of-focus profile(s): {', '.join(skipped)}"
            )
            click.echo("  (use --include-all to run every profile)")
            click.echo()
        if focus_domains is not None and not names:
            click.echo("No profiles match focus. Use 'max focus clear' or --include-all.")
            return

        click.echo(f"Running pipeline across {len(names)} profile(s): {', '.join(names)}")
        click.echo()
        for i, name in enumerate(names, 1):
            click.echo(f"{'=' * 80}")
            click.echo(f"[{i}/{len(names)}] Profile: {name}")
            click.echo(f"{'=' * 80}")
            p = load_profile(name)
            _run_single_profile(
                p, output, signal_limit, min_score, weight_profile, mode,
                quality_loop, draft_count, dry_run, stages_list,
                _profile_manifest_path(manifest_path, name) if manifest_path else None,
            )
            click.echo()
        click.echo(f"All {len(names)} profile(s) complete.")
        if not dry_run:
            _run_post_eval_stages()
        return

    if profile_name:
        p = load_profile(profile_name)
    else:
        p = get_default_profile()

    _run_single_profile(
        p, output, signal_limit, min_score, weight_profile, mode,
        quality_loop, draft_count, dry_run, stages_list, manifest_path,
    )
    if not dry_run:
        _run_post_eval_stages(domain=p.domain.name)


def _run_single_profile(
    p,
    output: str | None,
    signal_limit: int | None,
    min_score: float | None,
    weight_profile: str | None,
    mode: str | None,
    quality_loop: bool | None,
    draft_count: int | None,
    dry_run: bool,
    stages_list: list[str] | None,
    manifest_path: str | None = None,
) -> None:
    """Execute the pipeline for a single profile."""
    from max.pipeline.runner import run_pipeline
    from max.types.pipeline import DryRunReport

    # CLI flags override profile values
    if signal_limit is not None:
        p.signal_limit = signal_limit
    if min_score is not None:
        p.evaluation.min_score = min_score
    if weight_profile is not None:
        p.evaluation.weight_profile = weight_profile
    if mode is not None:
        p.ideation_mode = mode
    if quality_loop is not None:
        p.quality_loop_enabled = quality_loop
    if draft_count is not None:
        p.draft_count = draft_count

    output_dir = Path(output) if output else Path(p.output_dir)

    if dry_run:
        click.echo("DRY RUN: Simulating pipeline execution...")
    else:
        click.echo("Running max pipeline...")
    click.echo(f"  Profile:      {p.name}")
    click.echo(f"  Domain:       {p.domain.name}")
    click.echo(f"  Output:       {output_dir.resolve()}")
    click.echo(f"  Signal limit: {p.signal_limit}")
    click.echo(f"  Min score:    {p.evaluation.min_score}")
    click.echo(f"  Weights:      {p.evaluation.weight_profile}")
    click.echo(f"  Mode:         {p.ideation_mode}")
    click.echo(f"  Quality loop: {'on' if p.quality_loop_enabled else 'off'}")
    if p.quality_loop_enabled:
        click.echo(f"  Draft count:  {p.draft_count}")
    if stages_list:
        click.echo(f"  Stages:       {', '.join(stages_list)}")
    if manifest_path:
        click.echo(f"  Manifest:     {Path(manifest_path).resolve()}")
    click.echo()

    result = run_pipeline(
        profile=p,
        output_dir=output_dir,
        dry_run=dry_run,
        stages=stages_list,
        manifest_path=Path(manifest_path) if manifest_path else None,
    )

    # Handle dry-run output
    if isinstance(result, DryRunReport):
        click.echo("Pipeline Dry-Run Report")
        click.echo("=" * 80)
        click.echo()
        click.echo(f"{'Stage':<20s} {'Items':<8s} {'LLM Calls':<10s} {'Status':<12s} {'Reason'}")
        click.echo("-" * 80)
        for stage in result.stages:
            status = "SKIPPED" if stage.skipped else "READY"
            items = str(stage.would_process)
            llm_calls = str(stage.estimated_llm_calls)
            reason = stage.reason[:40] if stage.reason else ""
            click.echo(f"{stage.name:<20s} {items:<8s} {llm_calls:<10s} {status:<12s} {reason}")
        click.echo("-" * 80)
        click.echo(f"{'TOTAL':<20s} {'':<8s} {result.estimated_total_llm_calls:<10d}")
        click.echo()
        click.echo(f"Estimated token budget: ~{result.estimated_token_budget:,} tokens")
        click.echo()
        click.echo("No changes were made (dry-run mode).")
        return

    # Normal execution output
    click.echo(f"Signals fetched:    {result.signals_fetched} ({result.signals_new} new, {result.signals_skipped} already synthesized)")
    click.echo(f"Insights generated: {result.insights_generated} ({result.insights_duplicates_skipped} duplicates skipped, avg confidence: {result.avg_insight_confidence:.2f})")
    click.echo(f"Ideas generated:    {result.ideas_generated} ({result.ideas_duplicates_skipped} duplicates skipped)")
    if result.draft_ideas_generated or result.ideas_revised or result.ideas_rejected_by_quality_gate:
        click.echo(
            f"Quality loop:       {result.draft_ideas_generated} drafts, "
            f"{result.ideas_revised} revised, "
            f"{result.ideas_rejected_by_quality_gate} rejected"
        )
    if result.ideas_rejected_by_domain_quality or result.avg_domain_quality_score:
        click.echo(
            f"Domain quality:     avg {result.avg_domain_quality_score:.1f}, "
            f"{result.ideas_rejected_by_domain_quality} rejected"
        )
    if result.avg_novelty_score or result.avg_usefulness_score:
        click.echo(
            f"Quality scores:     novelty {result.avg_novelty_score:.1f}, "
            f"usefulness {result.avg_usefulness_score:.1f}"
        )
    click.echo(f"Ideas evaluated:    {result.ideas_evaluated} (avg score: {result.avg_idea_score:.1f})")
    if result.token_usage:
        total_input = result.token_usage.get("total_input", 0)
        total_output = result.token_usage.get("total_output", 0)
        cost = result.estimated_cost_usd
        click.echo(f"Token usage:        {total_input:,}in / {total_output:,}out (~${cost:.4f})")
    if result.budget_exceeded:
        click.echo("Budget exceeded - pipeline stopped early with partial results")
    click.echo()

    if result.top_ideas:
        click.echo("Top ideas:")
        for idea in result.top_ideas:
            marker = "+" if idea["score"] >= p.evaluation.min_score else " "
            click.echo(f"  [{marker}] {idea['score']:5.1f}  {idea['title']}  ({idea['recommendation']})")


@main.command(name="compare-runs")
@click.argument("base_run_id", type=str)
@click.argument("target_run_id", type=str)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON")
def compare_runs(base_run_id: str, target_run_id: str, as_json: bool) -> None:
    """Compare two persisted pipeline runs without re-running work."""
    from max.analysis.run_comparison import (
        PipelineRunComparisonNotFound,
        compare_pipeline_runs,
    )
    from max.store.db import Store

    with Store() as store:
        try:
            comparison = compare_pipeline_runs(
                store,
                base_run_id=base_run_id,
                target_run_id=target_run_id,
            )
        except PipelineRunComparisonNotFound as exc:
            missing = ", ".join(exc.missing_run_ids)
            raise click.ClickException(f"Pipeline run ID not found: {missing}") from exc

    if as_json:
        click.echo(json.dumps(comparison, indent=2))
        return

    _render_run_comparison(comparison)


def _render_run_comparison(comparison: dict[str, object]) -> None:
    """Render a run comparison as a compact terminal report."""
    base_run = comparison["base_run"]
    target_run = comparison["target_run"]

    click.echo("Pipeline run comparison")
    click.echo(f"Base:   {base_run['id']}  ({base_run['status']})")
    click.echo(f"Target: {target_run['id']}  ({target_run['status']})")
    click.echo()

    _render_comparison_section("Signals", comparison["fetched_signals"])
    _render_comparison_section("Insights", comparison["insights"])
    _render_comparison_section("Ideas", comparison["generated_ideas"])
    _render_comparison_section(
        "Approval / publish outputs",
        comparison["approved_published_outputs"],
    )
    _render_comparison_section("Budget usage", comparison["budget_usage"])
    _render_adapter_comparison(comparison["adapter_metrics"])


def _render_comparison_section(title: str, metrics: dict[str, dict[str, int | float]]) -> None:
    click.echo(title)
    click.echo(f"{'Metric':<28s} {'Base':>12s} {'Target':>12s} {'Delta':>12s}")
    click.echo("-" * 68)
    for metric_name, delta in metrics.items():
        click.echo(
            f"{metric_name:<28s} "
            f"{_format_comparison_value(delta['base']):>12s} "
            f"{_format_comparison_value(delta['target']):>12s} "
            f"{_format_comparison_delta(delta['delta']):>12s}"
        )
    click.echo()


def _render_adapter_comparison(adapters: list[dict[str, object]]) -> None:
    click.echo("Adapter changes")
    click.echo(
        f"{'Adapter':<18s} {'Base':<10s} {'Target':<10s} {'Changed':<8s} "
        f"{'Metric deltas':<36s} Errors"
    )
    click.echo("-" * 120)
    for row in adapters:
        metric_deltas = ", ".join(
            f"{name}={_format_comparison_delta(metric['delta'])}"
            for name, metric in row["metrics"].items()
        ) or "-"
        errors = _format_adapter_errors(row["base_error_message"], row["target_error_message"])
        click.echo(
            f"{row['adapter']:<18s} "
            f"{_format_optional_text(row['base_status']):<10s} "
            f"{_format_optional_text(row['target_status']):<10s} "
            f"{'yes' if row['status_changed'] else 'no':<8s} "
            f"{metric_deltas:<36s} "
            f"{errors}"
        )


def _format_adapter_errors(base_error: object, target_error: object) -> str:
    parts = []
    if base_error:
        parts.append(f"base={base_error}")
    if target_error:
        parts.append(f"target={target_error}")
    return "; ".join(parts) if parts else "-"


def _format_optional_text(value: object) -> str:
    return str(value) if value is not None else "-"


def _format_comparison_value(value: int | float) -> str:
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _format_comparison_delta(value: int | float) -> str:
    if isinstance(value, float):
        if value.is_integer():
            return f"{value:+.0f}"
        return f"{value:+.4f}".rstrip("0").rstrip(".")
    return f"{value:+d}"


def _profile_manifest_path(manifest_path: str, profile_name: str) -> str:
    """Derive a per-profile manifest path for ``max run --profile all``."""
    path = Path(manifest_path)
    if path.suffix:
        return str(path.with_name(f"{path.stem}-{profile_name}{path.suffix}"))
    return str(path / f"{profile_name}-run-manifest.json")


def _run_post_eval_stages(domain: str | None = None) -> None:
    """Run post-evaluation stages: dedup → synthesize → prior-art → triage."""
    from max.pipeline.runner import run_post_pipeline

    click.echo()
    click.echo(f"{'=' * 80}")
    click.echo("Post-evaluation: dedup → synthesize → prior-art → triage")
    click.echo(f"{'=' * 80}")
    click.echo()

    result = run_post_pipeline(domain=domain)

    # Report results
    if result.duplicates_marked:
        click.echo(f"Dedup:          {result.duplicates_marked} duplicates removed")
    else:
        click.echo("Dedup:          no duplicates found")

    if result.ideas_synthesized:
        click.echo(
            f"Synthesize:     {result.ideas_synthesized} ideas merged from "
            f"{result.source_ideas_merged} sources ({result.synthesis_clusters} clusters)"
        )
    else:
        click.echo("Synthesize:     no clusters to merge")

    if result.prior_art_checked:
        click.echo(
            f"Prior art:      {result.prior_art_checked} checked — "
            f"{result.prior_art_strong} strong, {result.prior_art_weak} weak, "
            f"{result.prior_art_clear} clear"
        )
    else:
        click.echo("Prior art:      no ideas to check")

    if result.triage_auto_approved or result.triage_auto_rejected:
        click.echo(
            f"Triage:         {result.triage_auto_approved} auto-approved, "
            f"{result.triage_auto_rejected} auto-rejected, "
            f"{result.triage_pending_review} pending review"
        )
    else:
        click.echo(f"Triage:         {result.triage_pending_review} ideas pending review")

    click.echo()
    click.echo("Ready for: max review")


@main.group(name="budget")
def budget_group() -> None:
    """Inspect LLM token and budget usage."""


@budget_group.command(name="usage")
@click.option("--limit", type=int, default=20, show_default=True, help="Pipeline runs to include")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json"]),
    default="table",
    show_default=True,
)
@click.option(
    "--current/--no-current",
    default=True,
    show_default=True,
    help="Include in-process token tracker usage",
)
def budget_usage(limit: int, fmt: str, current: bool) -> None:
    """Show current and historical LLM budget usage."""
    from max.analysis.budget_usage import build_llm_budget_usage
    from max.store.db import Store

    store = Store()
    try:
        usage = build_llm_budget_usage(store, limit=limit, include_current=current)
    finally:
        store.close()

    if fmt == "json":
        click.echo(json.dumps(usage, indent=2))
        return

    _print_budget_usage(usage)


@budget_group.command(name="anomalies")
@click.option("--limit", type=int, default=50, show_default=True, help="Recent pipeline runs to inspect")
@click.option("--z-threshold", type=float, default=2.0, show_default=True, help="Anomaly score threshold")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def budget_anomalies(limit: int, z_threshold: float, fmt: str) -> None:
    """Show anomalous LLM cost or token usage in recent pipeline runs."""
    from max.analysis.cost_anomalies import build_cost_anomaly_report
    from max.store.db import Store

    store = Store()
    try:
        report = build_cost_anomaly_report(store, limit=limit, z_threshold=z_threshold)
    finally:
        store.close()

    if fmt == "json":
        click.echo(json.dumps(report, indent=2))
        return

    _print_budget_anomalies(report)


def _budget_limit_text(limit: int | float, remaining: int | float | None, *, money: bool = False) -> str:
    if limit <= 0:
        return "unlimited"
    if money:
        return f"${limit:.4f} (${remaining or 0.0:.4f} remaining)"
    return f"{int(limit):,} ({int(remaining or 0):,} remaining)"


def _print_budget_usage(usage: dict[str, object]) -> None:
    total_input = int(usage["total_input"])
    total_output = int(usage["total_output"])
    total_tokens = int(usage["total_tokens"])
    total_cost = float(usage["total_cost_usd"])
    token_budget = int(usage["token_budget"])
    cost_budget = float(usage["cost_budget_usd"])

    click.echo(f"LLM budget usage ({usage['run_count']} runs)")
    click.echo(f"Tokens: {total_input:,} in / {total_output:,} out / {total_tokens:,} total")
    click.echo(f"Cost:   ${total_cost:.4f}")
    click.echo(
        "Limits: "
        f"tokens {_budget_limit_text(token_budget, usage['remaining_tokens'])}; "
        f"cost {_budget_limit_text(cost_budget, usage['remaining_cost_usd'], money=True)}"
    )

    stages = usage.get("stages") or []
    if stages:
        click.echo()
        click.echo(f"{'Stage':<24s} {'Tokens':>12s} {'Cost':>10s}")
        click.echo("-" * 48)
        for stage in stages:
            if not isinstance(stage, dict):
                continue
            click.echo(
                f"{str(stage['stage'])[:24]:<24s} "
                f"{int(stage['total_tokens']):>12,} "
                f"${float(stage['estimated_cost_usd']):>9.4f}"
            )


def _print_budget_anomalies(report: dict[str, object]) -> None:
    click.echo(
        f"LLM cost anomalies ({report['anomaly_count']} of {report['run_count']} runs, "
        f"z>={float(report['z_threshold']):.2f})"
    )

    anomalies = report.get("anomalies") or []
    if not anomalies:
        click.echo("No anomalies found.")
        return

    for anomaly in anomalies:
        if not isinstance(anomaly, dict):
            continue
        click.echo()
        click.echo(
            f"{anomaly['run_id']}  tokens={int(anomaly['total_tokens']):,}  "
            f"cost=${float(anomaly['estimated_cost_usd']):.4f}"
        )
        profile = anomaly.get("profile")
        if profile:
            click.echo(f"Profile: {profile}")

        run_anomalies = anomaly.get("run_anomalies") or []
        for item in run_anomalies:
            if not isinstance(item, dict):
                continue
            metric = str(item["metric"])
            observed = float(item["observed"])
            baseline = float(item["baseline"])
            ratio = float(item["ratio"])
            if metric == "estimated_cost_usd":
                click.echo(f"  Run {metric}: ${observed:.4f} vs ${baseline:.4f} ({ratio:.2f}x)")
            else:
                click.echo(f"  Run {metric}: {observed:,.0f} vs {baseline:,.0f} ({ratio:.2f}x)")

        stage_anomalies = anomaly.get("stage_anomalies") or []
        for item in stage_anomalies:
            if not isinstance(item, dict):
                continue
            metric = str(item["metric"])
            observed = float(item["observed"])
            baseline = float(item["baseline"])
            ratio = float(item["ratio"])
            if metric == "estimated_cost_usd":
                values = f"${observed:.4f} vs ${baseline:.4f}"
            else:
                values = f"{observed:,.0f} vs {baseline:,.0f}"
            click.echo(f"  Stage {item['stage']} {metric}: {values} ({ratio:.2f}x)")
            click.echo(f"    {item['recommendation']}")


@main.group(invoke_without_command=True)
@click.pass_context
def profiles(ctx: click.Context) -> None:
    """List available pipeline profiles."""
    if ctx.invoked_subcommand is not None:
        return

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


@profiles.command(name="validate")
@click.option("--profile", "-p", type=str, default=None, help="Validate one profile by name")
def profiles_validate(profile: str | None) -> None:
    """Validate profile YAML files against schema and semantic checks."""
    from max.profiles.loader import validate_profile_files

    try:
        results = validate_profile_files(profile=profile)
    except FileNotFoundError as e:
        raise click.ClickException(str(e)) from e

    has_errors = False
    for result in results:
        if result.ok and not result.warnings:
            click.echo(f"{result.name}: OK")
            continue

        if result.errors:
            has_errors = True
            click.echo(f"{result.name}: ERROR - {'; '.join(result.errors)}")
        if result.warnings:
            click.echo(f"{result.name}: WARNING - {'; '.join(result.warnings)}")

    if has_errors:
        raise click.exceptions.Exit(1)


@profiles.command(name="architecture-enforcement")
@click.argument("profile")
@click.option(
    "--unit-limit",
    type=int,
    default=100,
    show_default=True,
    help="Maximum recent buildable units to include",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON")
def profiles_architecture_enforcement(
    profile: str,
    unit_limit: int,
    fmt: str,
    as_json: bool,
) -> None:
    """Check generated ideas against profile architecture expectations."""
    from max.analysis.architecture_enforcement import build_architecture_enforcement_report
    from max.profiles.loader import load_profile
    from max.store.db import Store

    if unit_limit < 1:
        raise click.ClickException("--unit-limit must be at least 1")

    try:
        profile_config = load_profile(profile)
    except FileNotFoundError as e:
        raise click.ClickException(str(e)) from e

    with Store() as store:
        report = build_architecture_enforcement_report(
            profile_config,
            store,
            unit_limit=unit_limit,
        )

    if as_json or fmt == "json":
        click.echo(json.dumps(report.to_dict(), indent=2))
        return

    _render_architecture_enforcement(report)


def _render_architecture_enforcement(report) -> None:
    click.echo("Architecture enforcement")
    click.echo(
        f"Profile: {report.profile_name}  Domain: {report.domain}  "
        f"Status: {report.status}  Units: {report.units_analyzed}"
    )
    click.echo(f"Constraints configured: {'yes' if report.constraints_configured else 'no'}")
    click.echo()

    if not report.findings:
        click.echo("No architecture findings.")
    else:
        click.echo(f"{'Severity':<9s} {'Code':<36s} {'Idea':<24s} Field")
        click.echo("-" * 92)
        for finding in report.findings:
            click.echo(
                f"{finding.severity:<9s} "
                f"{finding.code:<36s} "
                f"{finding.title[:24]:<24s} "
                f"{finding.field}"
            )
            click.echo(f"  {finding.message}")
            if finding.observed:
                click.echo(f"  observed: {', '.join(finding.observed)}")
            if finding.expected:
                click.echo(f"  expected: {', '.join(finding.expected)}")
        click.echo()

    if report.recommended_constraint_additions:
        click.echo("Recommended profile constraint additions:")
        for recommendation in report.recommended_constraint_additions:
            click.echo(f"  - {recommendation}")


@profiles.command(name="coverage-matrix")
@click.argument("profile")
@click.option(
    "--threshold",
    type=int,
    default=1,
    show_default=True,
    help="Minimum total active signals required for a term to be covered",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json", "csv"]),
    default="table",
    show_default=True,
)
def profiles_coverage_matrix(profile: str, threshold: int, fmt: str) -> None:
    """Show full signal coverage for a profile's configured terms."""
    from max.analysis.profile_coverage import compute_profile_coverage_matrix
    from max.profiles.loader import load_profile
    from max.store.db import Store

    if threshold < 1:
        raise click.ClickException("--threshold must be at least 1")

    try:
        pipeline_profile = load_profile(profile)
    except FileNotFoundError as e:
        raise click.ClickException(str(e)) from e

    store = Store()
    try:
        matrix = compute_profile_coverage_matrix(
            pipeline_profile,
            store,
            low_coverage_threshold=threshold,
        )
    finally:
        store.close()

    click.echo(_render_profile_coverage_matrix(matrix, fmt=fmt), nl=False)


@main.group(name="sources")
def sources_group() -> None:
    """Inspect source adapter configuration."""


@sources_group.command(name="list")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json"]),
    default="table",
    show_default=True,
)
def sources_list(fmt: str) -> None:
    """List source adapters and supported configuration keys."""
    from max.sources.registry import list_adapter_metadata

    metadata = list_adapter_metadata()

    if fmt == "json":
        payload = [
            {
                "name": item.name,
                "config_keys": item.config_keys,
                "required_keys": item.required_keys,
                "description": item.description,
            }
            for item in metadata
        ]
        click.echo(json.dumps(payload, indent=2))
        return

    if not metadata:
        click.echo("No source adapters found.")
        return

    click.echo("Available source adapters:")
    click.echo()
    for item in metadata:
        config_keys = ", ".join(item.config_keys) if item.config_keys else "(none)"
        required_keys = ", ".join(item.required_keys) if item.required_keys else "(none)"
        click.echo(f"  {item.name}")
        click.echo(f"    Description: {item.description}")
        click.echo(f"    Config keys: {config_keys}")
        click.echo(f"    Required:    {required_keys}")


@sources_group.command(name="simulate")
@click.option(
    "--profile",
    "-p",
    type=str,
    default=None,
    help="Pipeline profile name (defaults to MAX_PROFILE or devtools)",
)
@click.option(
    "--budget",
    type=int,
    default=None,
    help="Total fetch signal budget (defaults to profile signal_limit)",
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON")
def sources_simulate(profile: str | None, budget: int | None, as_json: bool) -> None:
    """Simulate profile source allocation before a run."""
    from max.analysis.source_simulation import simulate_source_allocation
    from max.config import MAX_PROFILE
    from max.profiles.loader import get_default_profile, load_profile
    from max.store.db import Store

    if budget is not None and budget < 1:
        raise click.ClickException("--budget must be at least 1")

    profile_name = profile or MAX_PROFILE or None
    try:
        p = load_profile(profile_name) if profile_name else get_default_profile()
    except FileNotFoundError as e:
        raise click.ClickException(str(e)) from e

    with Store() as store:
        report = simulate_source_allocation(p, store, budget=budget)

    if as_json:
        click.echo(json.dumps(report.to_dict(), indent=2))
        return

    _render_source_simulation(report)


def _render_source_simulation(report) -> None:
    """Render source allocation simulation as a compact table."""
    click.echo("Source allocation simulation")
    click.echo(
        f"Profile: {report.profile}  "
        f"Domain: {report.domain}  "
        f"Budget: {report.total_budget}"
    )
    click.echo()
    click.echo(
        f"{'Adapter':<22s} {'On':<3s} {'Weight':>6s} {'Signals':>7s} "
        f"{'Ins%':>6s} {'Idea%':>6s} {'Fb':>4s} {'Appr%':>6s} "
        f"{'CB':<9s} {'Alloc':>6s} Params"
    )
    click.echo("-" * 116)
    for source in report.sources:
        params = _format_source_params(source.params)
        approval = _format_rate(source.approval_rate)
        click.echo(
            f"{source.adapter[:22]:<22s} "
            f"{'yes' if source.enabled else 'no':<3s} "
            f"{source.configured_weight:>6.2f} "
            f"{source.total_signals:>7d} "
            f"{_format_rate(source.insight_hit_rate):>6s} "
            f"{_format_rate(source.idea_hit_rate):>6s} "
            f"{source.total_feedbacked:>4d} "
            f"{approval:>6s} "
            f"{source.circuit_state:<9s} "
            f"{source.allocated_limit:>6d} "
            f"{params}"
        )
    click.echo("-" * 116)
    click.echo(f"Total allocated: {sum(report.allocation.values())}")


def _format_rate(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.0%}"


def _format_source_params(params: dict) -> str:
    if not params:
        return "{}"
    encoded = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return encoded if len(encoded) <= 42 else f"{encoded[:39]}..."


@main.command(name="opportunity-heatmap")
@click.option("--domain", type=str, default=None, help="Limit analysis to one domain")
@click.option(
    "--min-signals",
    type=int,
    default=1,
    show_default=True,
    help="Minimum resolved evidence signals per bucket",
)
@click.option(
    "--limit",
    type=int,
    default=1000,
    show_default=True,
    help="Maximum ideas to scan",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def opportunity_heatmap(domain: str | None, min_signals: int, limit: int, fmt: str) -> None:
    """Analyze opportunity density by domain and idea category."""
    from max.analysis.opportunity_heatmap import build_opportunity_heatmap
    from max.store.db import Store

    if min_signals < 0:
        raise click.ClickException("--min-signals must be non-negative")
    if limit < 1:
        raise click.ClickException("--limit must be at least 1")

    store = Store()
    try:
        buckets = build_opportunity_heatmap(
            store,
            domain=domain,
            min_signals=min_signals,
            limit=limit,
        )
    finally:
        store.close()

    if fmt == "json":
        click.echo(json.dumps(buckets, indent=2))
        return

    _render_opportunity_heatmap(buckets, domain=domain, min_signals=min_signals)


def _render_opportunity_heatmap(
    buckets: list[dict],
    *,
    domain: str | None,
    min_signals: int,
) -> None:
    click.echo("Opportunity heatmap")
    if domain:
        click.echo(f"Domain: {domain}")
    click.echo(f"Minimum signals: {min_signals}")
    click.echo()

    if not buckets:
        click.echo("No opportunity heatmap buckets found.")
        return

    click.echo(
        f"{'Domain':<18s} {'Category':<16s} {'Sig':>4s} {'Ins':>4s} "
        f"{'Ideas':>5s} {'Eval':>5s} {'Appr':>5s} {'Avg':>6s} "
        f"{'Dens':>6s} {'Fresh':>6s} {'Score':>6s}"
    )
    click.echo("-" * 96)
    for bucket in buckets:
        average_score = bucket["average_score"]
        avg_text = "-" if average_score is None else f"{float(average_score):.1f}"
        click.echo(
            f"{str(bucket['domain'])[:18]:<18s} "
            f"{str(bucket['idea_category'])[:16]:<16s} "
            f"{int(bucket['signal_count']):>4d} "
            f"{int(bucket['insight_count']):>4d} "
            f"{int(bucket['idea_count']):>5d} "
            f"{int(bucket['evaluated_count']):>5d} "
            f"{int(bucket['approved_count']):>5d} "
            f"{avg_text:>6s} "
            f"{float(bucket['evidence_density']):>6.1f} "
            f"{float(bucket['freshness_signal']):>6.1f} "
            f"{float(bucket['opportunity_score']):>6.1f}"
        )
        reasons = bucket.get("reasons") or []
        if reasons:
            click.echo(f"  - {reasons[0]}")
    click.echo("-" * 96)


@main.group(name="signals")
def signals_group() -> None:
    """Inspect ingested signals."""


@signals_group.command(name="freshness")
@click.option(
    "--max-age-days",
    type=int,
    default=30,
    show_default=True,
    help="Age threshold for stale signals",
)
@click.option("--source-adapter", multiple=True, help="Limit analysis to one or more source adapters")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json"]),
    default="table",
    show_default=True,
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON")
def signals_freshness(
    max_age_days: int,
    source_adapter: tuple[str, ...],
    fmt: str,
    as_json: bool,
) -> None:
    """Report signal age and stale source recommendations."""
    from max.analysis.signal_freshness import build_signal_freshness_report
    from max.store.db import Store

    if max_age_days < 1:
        raise click.ClickException("--max-age-days must be at least 1")

    store = Store()
    try:
        report = build_signal_freshness_report(
            store,
            max_age_days=max_age_days,
            source_adapters=list(source_adapter) or None,
        )
    finally:
        store.close()

    if as_json or fmt == "json":
        click.echo(json.dumps(report.to_dict(), indent=2))
        return

    _render_signal_freshness(report)


def _render_signal_freshness(report) -> None:
    click.echo("Signal freshness")
    click.echo(
        f"Signals: {report.total_signals}  "
        f"Stale: {report.stale_signals}  "
        f"Max age: {report.max_age_days} days"
    )
    if report.source_adapter_filters:
        click.echo(f"Adapters: {', '.join(report.source_adapter_filters)}")

    _render_freshness_group("By source adapter", report.by_source_adapter)
    _render_freshness_group("By source type", report.by_source_type)
    _render_freshness_group("By domain tag", report.by_domain_tag)
    _render_freshness_group("By signal role", report.by_signal_role)

    click.echo()
    click.echo("Recommendations")
    if not report.recommendations:
        click.echo("  No stale source adapters detected.")
        return
    for rec in report.recommendations:
        click.echo(f"  {rec.source_adapter}: {rec.reason} {rec.action}")


def _render_freshness_group(title: str, groups) -> None:
    click.echo()
    click.echo(title)
    if not groups:
        click.echo("  (none)")
        return
    click.echo(
        f"  {'Key':<24s} {'Count':>6s} {'Stale':>6s} "
        f"{'Median':>8s} {'Newest':<20s} {'Oldest':<20s}"
    )
    click.echo("  " + "-" * 92)
    for group in groups:
        median_age = "-" if group.median_age_days is None else f"{group.median_age_days:.2f}"
        click.echo(
            f"  {group.key[:24]:<24s} "
            f"{group.total_count:>6d} "
            f"{group.stale_count:>6d} "
            f"{median_age:>8s} "
            f"{_short_timestamp(group.newest_timestamp):<20s} "
            f"{_short_timestamp(group.oldest_timestamp):<20s}"
        )


def _short_timestamp(value: str | None) -> str:
    if not value:
        return "-"
    return value.replace("+00:00", "Z")[:19]


@main.command(name="source-reliability")
@click.option(
    "--signal-limit",
    type=int,
    default=500,
    show_default=True,
    help="Maximum active signals to include",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json"]),
    default="table",
    show_default=True,
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON")
def source_reliability(signal_limit: int, fmt: str, as_json: bool) -> None:
    """Analyze source reliability by source type."""
    from max.analysis.source_reliability import build_source_reliability_report
    from max.store.db import Store

    if signal_limit < 1:
        raise click.ClickException("--signal-limit must be at least 1")

    store = Store()
    try:
        report = build_source_reliability_report(store, signal_limit=signal_limit)
    finally:
        store.close()

    if as_json or fmt == "json":
        click.echo(json.dumps(report.to_dict(), indent=2))
        return

    _render_source_reliability(report)


def _render_source_reliability(report) -> None:
    click.echo("Source reliability")
    click.echo(f"Signals analyzed: {report.total_signals}  Limit: {report.signal_limit}")
    click.echo()
    if not report.source_types:
        click.echo("No active signals found.")
        return

    click.echo(
        f"{'Source type':<18s} {'Signals':>7s} {'Adapters':>8s} "
        f"{'Health':>7s} {'Useful':>7s} {'Corr':>7s} {'Ideas':>7s} {'Score':>7s}"
    )
    click.echo("-" * 78)
    for row in report.source_types:
        click.echo(
            f"{row.source_type[:18]:<18s} "
            f"{row.total_signals:>7d} "
            f"{len(row.source_adapters):>8d} "
            f"{_format_rate(row.adapter_health_score):>7s} "
            f"{_format_rate(row.signal_usefulness_score):>7s} "
            f"{_format_rate(row.corroboration_rate):>7s} "
            f"{_format_rate(row.downstream_idea_conversion_rate):>7s} "
            f"{_format_rate(row.reliability_score):>7s}"
        )
        click.echo(f"  Adapters: {', '.join(row.source_adapters)}")
        for reason in row.reasons:
            click.echo(f"  - {reason}")
    click.echo("-" * 78)


@main.command(name="profile-source-recommendations")
@click.argument("profile")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def profile_source_recommendations(profile: str, fmt: str) -> None:
    """Recommend source configuration changes for a profile."""
    from max.analysis.profile_source_recommendations import (
        build_profile_source_recommendations,
    )
    from max.store.db import Store

    store = Store()
    try:
        report = build_profile_source_recommendations(profile, store)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    finally:
        store.close()

    if fmt == "json":
        click.echo(json.dumps(report.to_dict(), indent=2))
        return

    _render_profile_source_recommendations(report)


def _render_profile_source_recommendations(report) -> None:
    click.echo("Profile source recommendations")
    click.echo(f"Profile: {report.profile_name}  Domain: {report.domain}")
    click.echo()
    if not report.recommendations:
        click.echo("No source adapters found.")
        return

    click.echo(
        f"{'Adapter':<24s} {'Action':<16s} {'Severity':<8s} "
        f"{'Enabled':<7s} {'Weight':>8s} {'Suggested':>9s}"
    )
    click.echo("-" * 78)
    for rec in report.recommendations:
        click.echo(
            f"{rec.adapter[:24]:<24s} "
            f"{rec.action:<16s} "
            f"{rec.severity:<8s} "
            f"{str(rec.enabled):<7s} "
            f"{rec.current_weight:>8.3f} "
            f"{rec.suggested_weight:>9.3f}"
        )
        for reason in rec.reasons:
            click.echo(f"  - {reason}")
        quality = rec.evidence.get("quality", {})
        approval = rec.evidence.get("approval", {})
        freshness = rec.evidence.get("freshness", {})
        approval_rate = approval.get("approval_rate")
        approval_text = "-" if approval_rate is None else _format_rate(approval_rate)
        click.echo(
            "  evidence: "
            f"signals={quality.get('total_signals', 0)} "
            f"quality={_format_rate(quality.get('quality_score', 0.0))} "
            f"approval={approval_text} "
            f"stale={freshness.get('stale_count', 0)}/{freshness.get('total_count', 0)} "
            f"registered={rec.registered}"
        )
    click.echo("-" * 78)


@main.command(name="profile-drift")
@click.argument("profile")
@click.option(
    "--signal-limit",
    type=int,
    default=500,
    show_default=True,
    help="Maximum recent signals to include",
)
@click.option(
    "--unit-limit",
    type=int,
    default=100,
    show_default=True,
    help="Maximum recent buildable units to include",
)
@click.option(
    "--insight-limit",
    type=int,
    default=500,
    show_default=True,
    help="Maximum recent insights to include",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json"]),
    default="table",
    show_default=True,
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON")
def profile_drift(
    profile: str,
    signal_limit: int,
    unit_limit: int,
    insight_limit: int,
    fmt: str,
    as_json: bool,
) -> None:
    """Analyze drift between recent outputs and a domain profile."""
    from max.analysis.profile_drift import build_profile_drift_report
    from max.profiles.loader import load_profile
    from max.store.db import Store

    if signal_limit < 1:
        raise click.ClickException("--signal-limit must be at least 1")
    if unit_limit < 1:
        raise click.ClickException("--unit-limit must be at least 1")
    if insight_limit < 1:
        raise click.ClickException("--insight-limit must be at least 1")

    try:
        profile_config = load_profile(profile)
    except FileNotFoundError as e:
        raise click.ClickException(str(e)) from e

    with Store() as store:
        report = build_profile_drift_report(
            profile_config,
            store,
            signal_limit=signal_limit,
            unit_limit=unit_limit,
            insight_limit=insight_limit,
        )

    if as_json or fmt == "json":
        click.echo(json.dumps(report.to_dict(), indent=2))
        return

    _render_profile_drift(report)


def _render_profile_drift(report) -> None:
    click.echo("Profile drift")
    click.echo(
        f"Profile: {report.profile_name}  Domain: {report.domain}  "
        f"Status: {report.status}  Score: {_format_rate(report.overall_drift_score)}"
    )
    click.echo(
        f"Signals: {report.signals_analyzed}  Insights: {report.insights_analyzed}  "
        f"Units: {report.units_analyzed}  Evaluations: {report.evaluations_analyzed}"
    )
    click.echo()
    click.echo(
        f"{'Metric':<24s} {'Samples':>7s} {'Drift':>7s} {'Status':>8s} "
        f"{'Unexpected':<24s} Missing expected"
    )
    click.echo("-" * 104)
    for metric in (
        report.category_drift,
        report.source_mix_drift,
        report.target_user_drift,
    ):
        click.echo(
            f"{metric.metric:<24s} "
            f"{metric.sample_count:>7d} "
            f"{_format_rate(metric.drift_score):>7s} "
            f"{metric.status:>8s} "
            f"{', '.join(metric.unexpected)[:24]:<24s} "
            f"{', '.join(metric.missing_expected)[:32]}"
        )
    weight = report.evaluation_weight_mismatch
    click.echo(
        f"{'evaluation_weight_mismatch':<24s} "
        f"{weight.sample_count:>7d} "
        f"{_format_rate(weight.average_absolute_delta):>7s} "
        f"{weight.status:>8s} "
        f"{str(weight.mismatched_evaluation_count) + ' mismatched':<24s} "
        f"{weight.missing_weights_count} missing weights"
    )
    click.echo("-" * 104)

    if report.warnings:
        click.echo()
        click.echo("Warnings")
        for warning in report.warnings:
            click.echo(f"  - {warning}")


def _known_profile_domains() -> dict[str, str]:
    """Return {domain_name: profile_name} for all valid profiles."""
    from max.profiles.loader import list_profiles, load_profile

    mapping: dict[str, str] = {}
    for name in list_profiles():
        try:
            p = load_profile(name)
        except Exception:
            continue
        mapping[p.domain.name] = name
    return mapping


def _validate_focus_domains(domains: list[str]) -> list[str]:
    """Validate domain names against known profile domains.

    Raises click.ClickException on invalid names. Returns the (possibly
    deduplicated) list in original order.
    """
    known = _known_profile_domains()
    seen: set[str] = set()
    clean: list[str] = []
    invalid: list[str] = []
    for d in domains:
        d = d.strip()
        if not d or d in seen:
            continue
        seen.add(d)
        if d not in known:
            invalid.append(d)
        clean.append(d)
    if invalid:
        available = ", ".join(sorted(known.keys()))
        raise click.ClickException(
            f"Unknown domain(s): {', '.join(invalid)}. Available: {available}"
        )
    return clean


@main.group(name="focus")
def focus() -> None:
    """Manage reviewer focus domains.

    When focus is set, `max run --profile all` skips out-of-focus profiles
    and `max archive-ideas` moves pending out-of-focus ideas to archived.
    """


@focus.command(name="list")
def focus_list() -> None:
    """Show current focus domains and available profile domains."""
    from max.focus import get_focus_config_path, load_focus_domains

    current = load_focus_domains()
    known = _known_profile_domains()

    if current is None:
        click.echo("Focus: (not configured — all domains included)")
    else:
        click.echo(f"Focus domains ({len(current)}):")
        for d in current:
            marker = "" if d in known else "  (UNKNOWN — no matching profile)"
            click.echo(f"  {d}{marker}")

    click.echo()
    click.echo("Available profile domains:")
    for domain in sorted(known.keys()):
        in_focus_marker = "  [focused]" if current and domain in current else ""
        click.echo(f"  {domain:22s}  (profile: {known[domain]}){in_focus_marker}")

    click.echo()
    click.echo(f"Config: {get_focus_config_path()}")


@focus.command(name="set")
@click.argument("domains", nargs=-1, required=True)
def focus_set(domains: tuple[str, ...]) -> None:
    """Replace focus domains with the given list."""
    from max.focus import save_focus_domains

    clean = _validate_focus_domains(list(domains))
    save_focus_domains(clean)
    click.echo(f"Focus set to: {', '.join(clean)}")


@focus.command(name="add")
@click.argument("domain")
def focus_add(domain: str) -> None:
    """Add a domain to the focus list."""
    from max.focus import load_focus_domains, save_focus_domains

    current = load_focus_domains() or []
    if domain in current:
        click.echo(f"Already focused: {domain}")
        return
    clean = _validate_focus_domains([*current, domain])
    save_focus_domains(clean)
    click.echo(f"Added: {domain}. Focus: {', '.join(clean)}")


@focus.command(name="remove")
@click.argument("domain")
def focus_remove(domain: str) -> None:
    """Remove a domain from the focus list."""
    from max.focus import load_focus_domains, save_focus_domains

    current = load_focus_domains()
    if not current or domain not in current:
        click.echo(f"Not in focus: {domain}")
        return
    updated = [d for d in current if d != domain]
    save_focus_domains(updated if updated else None)
    if updated:
        click.echo(f"Removed: {domain}. Focus: {', '.join(updated)}")
    else:
        click.echo(f"Removed: {domain}. Focus cleared (all domains included).")


@focus.command(name="clear")
def focus_clear() -> None:
    """Clear the focus filter (include all domains)."""
    from max.focus import load_focus_domains, save_focus_domains

    if load_focus_domains() is None:
        click.echo("Focus is already cleared.")
        return
    save_focus_domains(None)
    click.echo("Focus cleared. All domains included.")


@main.command(name="import-signals")
@click.argument("input_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--source-adapter", type=str, default=None, help="Source adapter to assign to imported signals")
@click.option("--source-type", type=str, default=None, help="Source type to assign to imported signals")
@click.option("--tag", "tags", multiple=True, help="Tag to add to every imported signal")
@click.option("--dry-run", is_flag=True, help="Validate and report counts without inserting signals")
@click.option("--fail-fast", is_flag=True, help="Stop at the first invalid or failed row")
def import_signals(
    input_path: Path,
    source_adapter: str | None,
    source_type: str | None,
    tags: tuple[str, ...],
    dry_run: bool,
    fail_fast: bool,
) -> None:
    """Import signals from a JSONL or CSV file."""
    from max.store.db import Store

    store = Store()
    try:
        counts = _import_signals_from_file(
            store,
            input_path,
            source_adapter=source_adapter,
            source_type=source_type,
            tags=list(tags),
            dry_run=dry_run,
            fail_fast=fail_fast,
        )
    finally:
        store.close()

    click.echo("Import signals summary")
    click.echo(f"  created:   {counts['created']}")
    click.echo(f"  duplicate: {counts['duplicate']}")
    click.echo(f"  invalid:   {counts['invalid']}")
    click.echo(f"  failed:    {counts['failed']}")
    if dry_run:
        click.echo("Dry run: no changes applied.")


def _import_signals_from_file(
    store,
    input_path: Path,
    *,
    source_adapter: str | None,
    source_type: str | None,
    tags: list[str],
    dry_run: bool,
    fail_fast: bool,
) -> dict[str, int]:
    counts = {"created": 0, "duplicate": 0, "invalid": 0, "failed": 0}
    seen_urls: set[str] = set()
    for line_no, raw in _read_signal_import_rows(input_path):
        try:
            signal = _signal_from_import_row(
                raw,
                source_adapter=source_adapter,
                source_type=source_type,
                tags=tags,
            )
        except (TypeError, ValueError) as e:
            counts["invalid"] += 1
            click.echo(f"Invalid row {line_no}: {e}", err=True)
            if fail_fast:
                raise click.ClickException(f"Invalid row {line_no}: {e}") from e
            continue

        try:
            if signal.url in seen_urls or store.get_signal_by_url(signal.url) is not None:
                counts["duplicate"] += 1
                seen_urls.add(signal.url)
                continue

            if dry_run:
                counts["created"] += 1
                seen_urls.add(signal.url)
                continue

            store.insert_signal(signal)
            if store.get_signal(signal.id) is not None:
                counts["created"] += 1
            else:
                counts["duplicate"] += 1
            seen_urls.add(signal.url)
        except Exception as e:
            counts["failed"] += 1
            click.echo(f"Failed row {line_no}: {e}", err=True)
            if fail_fast:
                raise click.ClickException(f"Failed row {line_no}: {e}") from e

    return counts


def _read_signal_import_rows(input_path: Path) -> list[tuple[int, dict]]:
    suffix = input_path.suffix.lower()
    if suffix == ".jsonl":
        rows = []
        with input_path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as e:
                    rows.append((line_no, {"__invalid_json__": str(e)}))
                    continue
                rows.append((line_no, row))
        return rows

    if suffix == ".csv":
        with input_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return [(line_no, row) for line_no, row in enumerate(reader, 2)]

    raise click.ClickException("Input file must be .jsonl or .csv")


def _signal_from_import_row(
    row: dict,
    *,
    source_adapter: str | None,
    source_type: str | None,
    tags: list[str],
):
    from max.types.signal import Signal

    if not isinstance(row, dict):
        raise ValueError("row must be an object")
    if "__invalid_json__" in row:
        raise ValueError(f"invalid JSON: {row['__invalid_json__']}")

    clean = {str(k): v for k, v in row.items() if v not in (None, "")}
    missing = [field for field in ("title", "content", "url") if not str(clean.get(field, "")).strip()]
    if missing:
        raise ValueError(f"missing required field(s): {', '.join(missing)}")

    metadata = _parse_import_metadata(clean.get("metadata"))
    if clean.get("signal_role"):
        metadata["signal_role"] = clean["signal_role"]

    signal_kwargs = dict(
        id=str(clean.get("id", "")),
        source_type=str(source_type or clean.get("source_type") or "forum"),
        source_adapter=str(source_adapter or clean.get("source_adapter") or "import"),
        title=str(clean["title"]).strip(),
        content=str(clean["content"]).strip(),
        url=str(clean["url"]).strip(),
        author=str(clean["author"]).strip() if clean.get("author") else None,
        published_at=clean.get("published_at"),
        tags=_merge_import_tags(tags, clean.get("tags")),
        credibility=float(clean.get("credibility", 0.5)),
        metadata=metadata,
    )
    if clean.get("fetched_at"):
        signal_kwargs["fetched_at"] = clean["fetched_at"]
    return Signal(**signal_kwargs)


def _parse_import_metadata(value) -> dict:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError("metadata must be a JSON object")
        return parsed
    raise ValueError("metadata must be an object")


def _merge_import_tags(global_tags: list[str], row_tags) -> list[str]:
    parsed: list[str] = []
    if isinstance(row_tags, list):
        parsed = [str(tag).strip() for tag in row_tags]
    elif isinstance(row_tags, str) and row_tags.strip():
        text = row_tags.strip()
        if text.startswith("["):
            loaded = json.loads(text)
            if not isinstance(loaded, list):
                raise ValueError("tags must be a list")
            parsed = [str(tag).strip() for tag in loaded]
        else:
            parsed = [tag.strip() for tag in text.split(",")]

    merged: list[str] = []
    for tag in [*global_tags, *parsed]:
        if tag and tag not in merged:
            merged.append(tag)
    return merged


@main.command(name="archive-ideas")
@click.option("--dry-run", is_flag=True, help="Show what would be archived without modifying data")
@click.option("--limit", type=int, default=10000, help="Max ideas to consider")
def archive_ideas(dry_run: bool, limit: int) -> None:
    """Archive pending ideas in out-of-focus domains.

    Only ideas with status='evaluated' and no existing feedback are archived.
    Approved/rejected/duplicate/synthesized ideas are preserved. Run
    `max focus set <domains>` first to configure focus.
    """
    from max.focus import load_focus_domains
    from max.analysis.status import can_transition_buildable_unit_status
    from max.store.db import Store

    focus_domains = load_focus_domains()
    if focus_domains is None:
        raise click.ClickException(
            "No focus domains configured. Run `max focus set <domain1> <domain2> ...` first."
        )

    store = Store()
    try:
        units = store.get_buildable_units(limit=limit)

        # Filter: out-of-focus, evaluated, no feedback
        candidates = []
        for unit in units:
            if not unit.domain or unit.domain in focus_domains:
                continue
            if unit.status != "evaluated":
                continue
            if not can_transition_buildable_unit_status(unit.status, "archived"):
                continue
            if store.has_feedback(unit.id):
                continue
            candidates.append(unit)

        if not candidates:
            click.echo(f"No pending ideas to archive. Focus: {', '.join(focus_domains)}")
            return

        # Group by domain for reporting
        by_domain: dict[str, list] = {}
        for unit in candidates:
            by_domain.setdefault(unit.domain, []).append(unit)

        click.echo(f"Focus: {', '.join(focus_domains)}")
        click.echo(f"Candidates to archive: {len(candidates)} ideas across {len(by_domain)} domain(s)")
        for domain in sorted(by_domain.keys()):
            click.echo(f"  [{domain}] {len(by_domain[domain])} ideas")

        if dry_run:
            click.echo("\nDRY RUN: No changes applied.")
            return

        archived = 0
        for unit in candidates:
            store.insert_feedback(unit.id, "archived", "out-of-focus domain")
            store.update_buildable_unit_status(unit.id, "archived")
            archived += 1

        click.echo(f"\nArchived {archived} ideas.")
    finally:
        store.close()


@main.command()
@click.option("--status", type=str, default=None, help="Filter by status")
@click.option("--domain", "-d", type=str, default=None, help="Filter by domain (e.g. 'healthcare', 'fintech')")
@click.option("--limit", type=int, default=20, help="Max results")
@click.option("--include-archived", is_flag=True, help="Include archived out-of-focus ideas")
@click.option("--show-critique", is_flag=True, help="Show latest quality-loop critique summary")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table", show_default=True)
@click.option("--output", "-o", type=click.Path(dir_okay=False), default=None, help="Write JSON output to file")
def ideas(
    status: str | None,
    domain: str | None,
    limit: int,
    include_archived: bool,
    show_critique: bool,
    fmt: str,
    output: str | None,
) -> None:
    """List generated ideas with scores."""
    from max.store.db import Store

    store = Store()
    try:
        units = store.get_buildable_units(limit=limit, status=status, domain=domain)
        if not include_archived and status != "archived":
            units = [u for u in units if u.status != "archived"]
        if not units:
            click.echo("No ideas found.")
            return

        if fmt == "json" or output:
            payload = [
                _idea_summary_json(
                    unit,
                    store.get_evaluation(unit.id),
                    _get_latest_feedback(store, unit.id),
                    _get_idea_critiques(store, unit.id),
                )
                for unit in units
            ]
            rendered = json.dumps(payload, indent=2)
            if output:
                output_path = Path(output)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(rendered + "\n", encoding="utf-8")
                click.echo(f"Wrote {len(payload)} idea(s) to {output_path}")
            else:
                click.echo(rendered)
            return

        for unit in units:
            evaluation = store.get_evaluation(unit.id)
            score = evaluation.overall_score if evaluation else 0.0
            rec = evaluation.recommendation if evaluation else "-"
            domain_label = f"[{unit.domain}]" if unit.domain else ""
            click.echo(f"  {score:5.1f}  [{unit.status:10s}]  {domain_label:16s}  {unit.title}  ({rec})  {unit.id}")
            if show_critique:
                critiques = store.get_idea_critiques(unit.id)
                if critiques:
                    dims = critiques[0]["dimensions"]
                    click.echo(
                        f"        critique q={dims.get('quality_score', 0.0):.1f} "
                        f"novelty={dims.get('novelty', 0.0):.1f} "
                        f"usefulness={dims.get('usefulness', 0.0):.1f} "
                        f"tags={', '.join(critiques[0]['rejection_tags']) or '-'}"
                    )
    finally:
        store.close()


def _get_latest_feedback(store, unit_id: str) -> dict | None:
    latest_feedback = store.get_latest_feedback(unit_id)
    return latest_feedback if isinstance(latest_feedback, dict) else None


def _get_idea_critiques(store, unit_id: str) -> list[dict]:
    critiques = store.get_idea_critiques(unit_id)
    return critiques if isinstance(critiques, list) else []


def _idea_review_metadata(unit: BuildableUnit, latest_feedback: dict | None = None) -> dict:
    outcome = latest_feedback["outcome"] if latest_feedback else None
    state = outcome or unit.status or "pending"
    if state == "evaluated":
        state = "pending_review"
    elif state == "draft":
        state = "draft"
    graph_state = "".join(part.capitalize() for part in state.replace("-", "_").split("_"))
    return {
        "review_state": state,
        "feedback_outcome": outcome,
        "feedback_reason": latest_feedback["reason"] if latest_feedback else "",
        "reviewed_at": latest_feedback["created_at"] if latest_feedback else None,
        "graph_labels": ["Idea", f"Review{graph_state}"],
        "is_approved": state in ("approved", "published"),
    }


def _idea_summary_json(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
    latest_feedback: dict | None = None,
    critiques: list[dict] | None = None,
) -> dict:
    summary = {
        "id": unit.id,
        "title": unit.title,
        "one_liner": unit.one_liner,
        "category": str(unit.category),
        "domain": unit.domain,
        "status": unit.status,
        **_idea_review_metadata(unit, latest_feedback),
        "quality_score": unit.quality_score,
        "novelty_score": unit.novelty_score,
        "usefulness_score": unit.usefulness_score,
        "rejection_tags": unit.rejection_tags,
        "score": evaluation.overall_score if evaluation else None,
        "recommendation": evaluation.recommendation if evaluation else None,
    }
    if critiques:
        summary["latest_critique"] = _idea_critique_json(critiques[0])
    return summary


def _idea_critique_json(row: dict) -> dict:
    return {
        "id": row["id"],
        "buildable_unit_id": row["buildable_unit_id"],
        "pipeline_run_id": row.get("pipeline_run_id"),
        "stage": row["stage"],
        "dimensions": row["dimensions"],
        "reasoning": row["reasoning"],
        "rejection_tags": row["rejection_tags"],
        "created_at": row["created_at"],
    }


@main.group(name="validation-experiments")
def validation_experiments() -> None:
    """Create, list, and update validation experiments."""


@validation_experiments.command(name="list")
@click.argument("idea_id")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table", show_default=True)
def validation_experiments_list(idea_id: str, fmt: str) -> None:
    """List validation experiments for an idea."""
    from max.store.db import Store

    with Store() as store:
        experiments = store.list_validation_experiments(idea_id)

    if experiments is None:
        raise click.ClickException(f"Idea not found: {idea_id}")

    if fmt == "json":
        click.echo(json.dumps(experiments, indent=2))
        return

    if not experiments:
        click.echo("No validation experiments found.")
        return

    click.echo(f"{'Status':<14s} {'Sample':>7s} {'Confidence':>10s}  Hypothesis  ID")
    click.echo("-" * 96)
    for experiment in experiments:
        sample = experiment["target_sample_size"]
        confidence = experiment["confidence_delta"]
        click.echo(
            f"{experiment['status'][:14]:<14s} "
            f"{str(sample) if sample is not None else '-':>7s} "
            f"{f'{confidence:+.2f}' if confidence is not None else '-':>10s}  "
            f"{experiment['hypothesis']}  {experiment['id']}"
        )


@validation_experiments.command(name="create")
@click.argument("idea_id")
@click.option("--hypothesis", required=True, help="Experiment hypothesis")
@click.option("--method", "method_", required=True, help="Experiment method")
@click.option("--target-sample-size", type=int, default=None, help="Target sample size")
@click.option("--success-metric", required=True, help="Success metric")
@click.option("--status", default="planned", show_default=True, help="Experiment status")
@click.option("--started-at", default=None, help="ISO timestamp when started")
@click.option("--completed-at", default=None, help="ISO timestamp when completed")
@click.option("--result-summary", default="", help="Result summary")
@click.option("--evidence-url", "evidence_urls", multiple=True, help="Evidence URL")
@click.option("--confidence-delta", type=float, default=None, help="Confidence delta from -1 to 1")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table", show_default=True)
def validation_experiments_create(
    idea_id: str,
    hypothesis: str,
    method_: str,
    target_sample_size: int | None,
    success_metric: str,
    status: str,
    started_at: str | None,
    completed_at: str | None,
    result_summary: str,
    evidence_urls: tuple[str, ...],
    confidence_delta: float | None,
    fmt: str,
) -> None:
    """Create a validation experiment for an idea."""
    from max.store.db import Store

    if target_sample_size is not None and target_sample_size < 1:
        raise click.ClickException("--target-sample-size must be at least 1")
    if confidence_delta is not None and not -1.0 <= confidence_delta <= 1.0:
        raise click.ClickException("--confidence-delta must be between -1 and 1")

    with Store() as store:
        experiment = store.create_validation_experiment(
            idea_id,
            hypothesis=hypothesis,
            method=method_,
            target_sample_size=target_sample_size,
            success_metric=success_metric,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            result_summary=result_summary,
            evidence_urls=list(evidence_urls),
            confidence_delta=confidence_delta,
        )

    if experiment is None:
        raise click.ClickException(f"Idea not found: {idea_id}")

    if fmt == "json":
        click.echo(json.dumps(experiment, indent=2))
        return

    click.echo(f"Created validation experiment {experiment['id']} for {idea_id}")


@validation_experiments.command(name="update")
@click.argument("experiment_id")
@click.option("--hypothesis", default=None, help="Experiment hypothesis")
@click.option("--method", "method_", default=None, help="Experiment method")
@click.option("--target-sample-size", type=int, default=None, help="Target sample size")
@click.option("--success-metric", default=None, help="Success metric")
@click.option("--status", default=None, help="Experiment status")
@click.option("--started-at", default=None, help="ISO timestamp when started")
@click.option("--completed-at", default=None, help="ISO timestamp when completed")
@click.option("--result-summary", default=None, help="Result summary")
@click.option("--evidence-url", "evidence_urls", multiple=True, help="Replace evidence URLs")
@click.option("--confidence-delta", type=float, default=None, help="Confidence delta from -1 to 1")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table", show_default=True)
def validation_experiments_update(
    experiment_id: str,
    hypothesis: str | None,
    method_: str | None,
    target_sample_size: int | None,
    success_metric: str | None,
    status: str | None,
    started_at: str | None,
    completed_at: str | None,
    result_summary: str | None,
    evidence_urls: tuple[str, ...],
    confidence_delta: float | None,
    fmt: str,
) -> None:
    """Update a validation experiment."""
    from max.store.db import Store

    if target_sample_size is not None and target_sample_size < 1:
        raise click.ClickException("--target-sample-size must be at least 1")
    if confidence_delta is not None and not -1.0 <= confidence_delta <= 1.0:
        raise click.ClickException("--confidence-delta must be between -1 and 1")

    updates = {
        "hypothesis": hypothesis,
        "method": method_,
        "target_sample_size": target_sample_size,
        "success_metric": success_metric,
        "status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "result_summary": result_summary,
        "confidence_delta": confidence_delta,
    }
    updates = {key: value for key, value in updates.items() if value is not None}
    if evidence_urls:
        updates["evidence_urls"] = list(evidence_urls)

    with Store() as store:
        experiment = store.update_validation_experiment(experiment_id, **updates)

    if experiment is None:
        raise click.ClickException(f"Validation experiment not found: {experiment_id}")

    if fmt == "json":
        click.echo(json.dumps(experiment, indent=2))
        return

    click.echo(f"Updated validation experiment {experiment['id']} ({experiment['status']})")


@main.group(name="export")
def export_group() -> None:
    """Export Max data for downstream analysis."""


@export_group.command(name="ideas")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["jsonl", "csv"]),
    default="jsonl",
    show_default=True,
)
@click.option("--status", type=str, default=None, help="Filter by status")
@click.option("--domain", "-d", type=str, default=None, help="Filter by domain")
@click.option("--min-score", type=float, default=None, help="Minimum evaluation score")
@click.option("--limit", type=int, default=100, help="Max ideas to scan")
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False),
    default=None,
    help="Write export to file",
)
def export_ideas(
    fmt: str,
    status: str | None,
    domain: str | None,
    min_score: float | None,
    limit: int,
    output: str | None,
) -> None:
    """Export idea summaries as JSON Lines or CSV."""
    from max.analysis.export import idea_export_records, render_idea_export, write_idea_export
    from max.store.db import Store

    store = Store()
    try:
        units = store.get_buildable_units(limit=limit, status=status, domain=domain)
        records = idea_export_records(
            units,
            get_evaluation=store.get_evaluation,
            get_latest_feedback=lambda unit_id: _get_latest_feedback(store, unit_id),
            min_score=min_score,
        )
        if not records:
            click.echo("No ideas found.")
            return
        if output:
            output_path = Path(output)
            write_idea_export(output_path, records, fmt=fmt)
            click.echo(f"Wrote {len(records)} idea(s) to {output_path}")
            return
        click.echo(render_idea_export(records, fmt=fmt), nl=False)
    finally:
        store.close()


@main.command()
@click.argument("unit_id")
@click.option("--evidence-pack", is_flag=True, help="Show persisted or reconstructed evidence pack")
def inspect(unit_id: str, evidence_pack: bool) -> None:
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
        if unit.specific_user or unit.buyer or unit.workflow_context:
            click.echo(f"User:        {unit.specific_user or '-'}")
            click.echo(f"Buyer:       {unit.buyer or '-'}")
            click.echo(f"Workflow:    {unit.workflow_context or '-'}")
        if unit.validation_plan:
            click.echo(f"Validation:  {unit.validation_plan}")
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

        critiques = store.get_idea_critiques(unit.id)
        if critiques:
            critique = critiques[0]
            dims = critique["dimensions"]
            click.echo()
            click.echo("Latest Critique:")
            for name in [
                "urgency", "buyer_clarity", "specificity", "evidence_support",
                "feasibility", "differentiation", "distribution_path",
                "domain_risk", "novelty", "usefulness", "quality_score",
            ]:
                if name in dims:
                    click.echo(f"  {name:20s} {dims[name]:4.1f}")
            if critique["rejection_tags"]:
                click.echo(f"  tags: {', '.join(critique['rejection_tags'])}")
            if critique["reasoning"]:
                click.echo(f"  reasoning: {critique['reasoning']}")

        if evidence_pack:
            click.echo()
            click.echo("Evidence Pack:")
            if critiques and critiques[0].get("evidence_pack"):
                import json

                click.echo(json.dumps(critiques[0]["evidence_pack"], indent=2))
            else:
                from max.ideation.evidence import build_evidence_pack

                insights = [
                    insight
                    for insight_id in unit.inspiring_insights
                    if (insight := store.get_insight(insight_id))
                ]
                click.echo(build_evidence_pack(insights=insights, store=store).to_json())
    finally:
        store.close()


@main.command(name="publish")
@click.argument("entity_id")
@click.option(
    "--target",
    type=click.Choice(["webhook", "github-issue", "discord", "azure-devops"]),
    default="webhook",
    show_default=True,
    help="Publishing target",
)
@click.option("--webhook-url", default=None, help="Webhook URL to POST the generated payload to")
@click.option(
    "--discord-username",
    default=None,
    help="Discord webhook username override (defaults to DISCORD_WEBHOOK_USERNAME)",
)
@click.option(
    "--github-repository",
    default=None,
    help="GitHub repository in owner/repo format (defaults to GITHUB_REPOSITORY)",
)
@click.option(
    "--github-token",
    default=None,
    help="GitHub token for live issue creation (defaults to GITHUB_TOKEN)",
)
@click.option(
    "--azure-devops-organization",
    default=None,
    help="Azure DevOps organization (defaults to AZURE_DEVOPS_ORGANIZATION)",
)
@click.option(
    "--azure-devops-project",
    default=None,
    help="Azure DevOps project (defaults to AZURE_DEVOPS_PROJECT)",
)
@click.option(
    "--azure-devops-work-item-type",
    default=None,
    help="Azure DevOps work item type (defaults to AZURE_DEVOPS_WORK_ITEM_TYPE or User Story)",
)
@click.option(
    "--azure-devops-area-path",
    default=None,
    help="Azure DevOps area path (defaults to AZURE_DEVOPS_AREA_PATH)",
)
@click.option(
    "--azure-devops-iteration-path",
    default=None,
    help="Azure DevOps iteration path (defaults to AZURE_DEVOPS_ITERATION_PATH)",
)
@click.option(
    "--azure-devops-tag",
    "azure_devops_tags",
    multiple=True,
    help="Additional Azure DevOps tag; repeat for multiple tags",
)
@click.option(
    "--payload",
    "payload_type",
    type=click.Choice(["tact-spec", "blueprint"]),
    default="tact-spec",
    show_default=True,
    help="Generated payload type to publish",
)
@click.option("--timeout", type=float, default=10.0, show_default=True, help="Webhook timeout in seconds")
@click.option("--retries", type=int, default=2, show_default=True, help="Retry count for transient failures")
@click.option("--dry-run", is_flag=True, help="Build and print the publish payload without network calls")
def publish(
    entity_id: str,
    target: str,
    webhook_url: str | None,
    discord_username: str | None,
    github_repository: str | None,
    github_token: str | None,
    azure_devops_organization: str | None,
    azure_devops_project: str | None,
    azure_devops_work_item_type: str | None,
    azure_devops_area_path: str | None,
    azure_devops_iteration_path: str | None,
    azure_devops_tags: tuple[str, ...],
    payload_type: str,
    timeout: float,
    retries: int,
    dry_run: bool,
) -> None:
    """Publish a generated tact spec or Blueprint source brief."""
    from max.analysis.blueprint_export import build_blueprint_source_brief
    from max.publisher.azure_devops_work_items import (
        AzureDevOpsWorkItemPublishError,
        AzureDevOpsWorkItemPublisher,
    )
    from max.publisher.discord_webhook import DiscordWebhookPublishError, DiscordWebhookPublisher
    from max.publisher.github_issues import GitHubIssuePublishError, GitHubIssuePublisher
    from max.publisher.webhook import WebhookPublishError, WebhookPublisher
    from max.spec.generator import generate_spec_preview
    from max.store.db import Store

    if target == "webhook" and not webhook_url:
        raise click.ClickException("--webhook-url is required when --target webhook")
    if target == "discord" and payload_type not in {"tact-spec", "blueprint"}:
        raise click.ClickException("--target discord supports --payload tact-spec or blueprint")
    if target == "github-issue" and payload_type != "tact-spec":
        raise click.ClickException("--target github-issue only supports --payload tact-spec")
    if target == "azure-devops" and payload_type != "tact-spec":
        raise click.ClickException("--target azure-devops only supports --payload tact-spec")

    store = Store()
    try:
        publication_idea_id = entity_id
        if payload_type == "tact-spec":
            unit = store.get_buildable_unit(entity_id)
            if not unit:
                raise click.ClickException(f"Idea not found: {entity_id}")
            payload = generate_spec_preview(unit, store.get_evaluation(entity_id))
            subject = unit.title
        else:
            brief = store.get_design_brief(entity_id)
            if not brief:
                raise click.ClickException(f"Design brief not found: {entity_id}")
            payload = build_blueprint_source_brief(store, brief)
            subject = brief["title"]
            publication_idea_id = brief["lead_idea_id"]

        if target == "github-issue":
            try:
                publisher = GitHubIssuePublisher.from_env(
                    repository=github_repository,
                    token=github_token,
                    timeout=timeout,
                )
                result = publisher.publish(payload, dry_run=dry_run)
            except (ValueError, GitHubIssuePublishError) as exc:
                if not dry_run:
                    store.insert_publication_attempt(
                        idea_id=publication_idea_id,
                        target_type="github_issue",
                        target_url=github_repository or "",
                        status="failure",
                        error=str(exc),
                    )
                raise click.ClickException(str(exc)) from exc

            if dry_run:
                click.echo(json.dumps(result.payload, indent=2))
                return

            store.insert_publication_attempt(
                idea_id=publication_idea_id,
                target_type="github_issue",
                target_url=result.issue_url or result.repository,
                status="success",
                response_status=result.status_code,
            )
            click.echo(
                f"Published GitHub issue for {entity_id} ({subject}) to "
                f"{result.issue_url or result.repository} [{result.status_code}]"
            )
            return

        if target == "azure-devops":
            publisher: AzureDevOpsWorkItemPublisher | None = None
            try:
                publisher = AzureDevOpsWorkItemPublisher.from_env(
                    organization=azure_devops_organization,
                    project=azure_devops_project,
                    work_item_type=azure_devops_work_item_type,
                    area_path=azure_devops_area_path,
                    iteration_path=azure_devops_iteration_path,
                    tags=list(azure_devops_tags) if azure_devops_tags else None,
                    timeout=timeout,
                    max_retries=retries,
                )
                result = publisher.publish(payload, dry_run=dry_run)
            except AzureDevOpsWorkItemPublishError as exc:
                if not dry_run:
                    store.insert_publication_attempt(
                        idea_id=publication_idea_id,
                        target_type="azure_devops_work_item",
                        target_url=publisher.work_item_endpoint if publisher else "",
                        status="failure",
                        response_status=exc.status_code,
                        error=str(exc),
                    )
                raise click.ClickException(str(exc)) from exc

            if dry_run:
                click.echo(json.dumps(result.payload, indent=2))
                return

            store.insert_publication_attempt(
                idea_id=publication_idea_id,
                target_type="azure_devops_work_item",
                target_url=result.work_item_url or "",
                status="success",
                response_status=result.status_code,
            )
            click.echo(
                f"Published Azure DevOps work item for {entity_id} ({subject}) to "
                f"{result.work_item_url or result.project} [{result.status_code}]"
            )
            return

        if target == "discord":
            publisher: DiscordWebhookPublisher | None = None
            try:
                publisher = DiscordWebhookPublisher.from_env(
                    webhook_url=webhook_url,
                    username=discord_username,
                    timeout=timeout,
                )
                result = publisher.publish(payload, dry_run=dry_run)
            except DiscordWebhookPublishError as exc:
                if not dry_run:
                    store.insert_publication_attempt(
                        idea_id=publication_idea_id,
                        target_type="discord_webhook",
                        target_url=publisher.redacted_url if publisher else "",
                        status="failure",
                        response_status=exc.status_code,
                        error=str(exc),
                    )
                raise click.ClickException(str(exc)) from exc

            if dry_run:
                click.echo(json.dumps(result.payload, indent=2))
                return

            store.insert_publication_attempt(
                idea_id=publication_idea_id,
                target_type="discord_webhook",
                target_url=result.url,
                status="success",
                response_status=result.status_code,
            )
            click.echo(
                f"Published Discord {payload_type} for {entity_id} ({subject}) to "
                f"{result.url} [{result.status_code}]"
            )
            return

        assert webhook_url is not None
        if dry_run:
            click.echo(json.dumps(payload, indent=2))
            return

        publisher = WebhookPublisher(
            webhook_url,
            timeout=timeout,
            retries=retries,
        )
        try:
            result = publisher.publish(payload, payload_type=payload_type)
        except (ValueError, WebhookPublishError) as exc:
            store.insert_publication_attempt(
                idea_id=publication_idea_id,
                target_type="webhook",
                target_url=publisher.redacted_url,
                status="failure",
                error=str(exc),
            )
            raise click.ClickException(str(exc)) from exc

        store.insert_publication_attempt(
            idea_id=publication_idea_id,
            target_type="webhook",
            target_url=result.url,
            status="success",
            response_status=result.status_code,
        )
        click.echo(
            f"Published {payload_type} for {entity_id} ({subject}) to "
            f"{result.url} [{result.status_code}] in {result.attempts} attempt(s)"
        )
    finally:
        store.close()


@main.command(name="spec-preview")
@click.argument("idea_id")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "yaml"]),
    default="json",
    show_default=True,
    help="Output format",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False),
    default=None,
    help="Write preview to file",
)
def spec_preview(idea_id: str, fmt: str, output: str | None) -> None:
    """Preview a tact project spec without publishing."""
    from max.spec.generator import generate_spec_preview
    from max.store.db import Store

    store = Store()
    try:
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            raise click.ClickException(f"Idea not found: {idea_id}")

        preview = generate_spec_preview(unit, store.get_evaluation(idea_id))
        rendered = _render_spec_preview(preview, fmt=fmt)
        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8")
            return
        click.echo(rendered, nl=False)
    finally:
        store.close()


def _render_spec_preview(preview: dict, *, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(preview, indent=2) + "\n"
    if fmt == "yaml":
        import yaml

        return yaml.safe_dump(preview, sort_keys=False, allow_unicode=True)
    raise click.ClickException(f"Unsupported format: {fmt}")


@main.command(name="spec-bundle")
@click.argument("idea_id")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "markdown", "yaml"]),
    default="json",
    show_default=True,
    help="Output format",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False),
    default=None,
    help="Write bundle to file",
)
def spec_bundle(idea_id: str, fmt: str, output: str | None) -> None:
    """Export a complete implementation spec bundle for one idea."""
    from max.spec.bundle import (
        generate_spec_bundle,
        render_spec_bundle_markdown,
        render_spec_bundle_yaml,
    )
    from max.store.db import Store

    store = Store()
    try:
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            raise click.ClickException(f"Idea not found: {idea_id}")

        bundle = generate_spec_bundle(unit, store.get_evaluation(idea_id), store)
        if fmt == "json":
            rendered = json.dumps(bundle, indent=2) + "\n"
        elif fmt == "markdown":
            rendered = render_spec_bundle_markdown(bundle)
        elif fmt == "yaml":
            rendered = render_spec_bundle_yaml(bundle)
        else:
            raise click.ClickException(f"Unsupported format: {fmt}")

        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8")
            return
        click.echo(rendered, nl=False)
    finally:
        store.close()


@main.command(name="spec-readiness")
@click.argument("idea_id")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "yaml"]),
    default="json",
    show_default=True,
    help="Output format",
)
def spec_readiness(idea_id: str, fmt: str) -> None:
    """Evaluate whether an idea is ready for tact spec generation."""
    from max.spec.readiness import evaluate_spec_readiness
    from max.store.db import Store

    store = Store()
    try:
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            raise click.ClickException(f"Idea not found: {idea_id}")

        readiness = evaluate_spec_readiness(unit, store.get_evaluation(idea_id))
        click.echo(_render_spec_preview(readiness, fmt=fmt), nl=False)
    finally:
        store.close()


@main.command(name="blast-radius")
@click.argument("idea_id")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format",
)
def blast_radius(idea_id: str, fmt: str) -> None:
    """Estimate implementation blast radius for one idea."""
    from max.analysis.blast_radius import estimate_idea_blast_radius
    from max.store.db import Store

    store = Store()
    try:
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            raise click.ClickException(f"Idea not found: {idea_id}")

        estimate = estimate_idea_blast_radius(unit, store.get_evaluation(idea_id))
        click.echo(_render_blast_radius(asdict(estimate), fmt=fmt), nl=False)
    finally:
        store.close()


def _render_blast_radius(estimate: dict, *, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(estimate, indent=2) + "\n"
    if fmt != "text":
        raise click.ClickException(f"Unsupported format: {fmt}")

    lines = [
        f"Blast radius: {estimate['title']}",
        f"Idea: {estimate['idea_id']}",
        f"Level: {estimate['level']} ({estimate['score']:.1f})",
        f"Confidence: {estimate['confidence']:.2f}",
    ]
    if estimate["affected_surfaces"]:
        lines.append("\nAffected surfaces:")
        for surface in estimate["affected_surfaces"]:
            lines.append(f"- {surface['name']}: {surface['level']} ({surface['score']:.1f})")
            if surface["drivers"]:
                lines.append(f"  Drivers: {surface['drivers'][0]}")
    if estimate["drivers"]:
        lines.append("\nDrivers:")
        for driver in estimate["drivers"]:
            lines.append(f"- {driver}")
    if estimate["mitigations"]:
        lines.append("\nMitigations:")
        for mitigation in estimate["mitigations"]:
            lines.append(f"- {mitigation}")
    return "\n".join(lines) + "\n"


@main.command(name="implementation-plan")
@click.argument("idea_id")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format",
)
def implementation_plan(idea_id: str, fmt: str) -> None:
    """Generate an autonomous-agent implementation plan for an idea."""
    from max.spec.generator import generate_spec_preview
    from max.spec.implementation_plan import generate_implementation_plan
    from max.store.db import Store

    store = Store()
    try:
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            raise click.ClickException(f"Idea not found: {idea_id}")

        evaluation = store.get_evaluation(idea_id)
        spec_preview = generate_spec_preview(unit, evaluation)
        plan = generate_implementation_plan(unit, evaluation, spec_preview)
        click.echo(_render_implementation_plan(plan, fmt=fmt), nl=False)
    finally:
        store.close()


@main.command(name="revision-brief")
@click.argument("idea_id")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format",
)
def revision_brief(idea_id: str, fmt: str) -> None:
    """Build an actionable revision brief for an idea."""
    from max.analysis.revision_brief import build_revision_brief
    from max.store.db import Store

    store = Store()
    try:
        try:
            brief = build_revision_brief(store, idea_id)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        if fmt == "json":
            click.echo(json.dumps(brief, indent=2))
            return
        click.echo(_render_revision_brief(brief), nl=False)
    finally:
        store.close()


def _render_revision_brief(brief: dict) -> str:
    state = brief["current_state"]
    lines = [
        f"Revision brief: {state['title']}",
        f"Idea:           {brief['idea_id']}",
        f"Status:         {state['status']}",
        f"Prior art:      {state['prior_art_status']} ({state['prior_art_match_count']} match(es))",
    ]
    evaluation = state.get("evaluation")
    if evaluation:
        lines.append(
            f"Evaluation:     {evaluation['overall_score']:.1f} ({evaluation['recommendation']})"
        )
    feedback = brief.get("latest_feedback")
    if feedback:
        suffix = f" - {feedback['reason']}" if feedback.get("reason") else ""
        lines.append(f"Feedback:       {feedback['outcome']}{suffix}")
    lines.append("")

    lines.append("Key defects:")
    if brief["key_defects"]:
        for defect in brief["key_defects"]:
            lines.append(f"  - [{defect['severity']}] {defect['field']}: {defect['issue']}")
    else:
        lines.append("  - None detected")

    lines.append("")
    lines.append("Recommended changes:")
    for change in brief["recommended_changes"]:
        lines.append(f"  {change['priority']}. {change['field']}: {change['instruction']}")

    lines.append("")
    lines.append("Evidence to collect:")
    for item in brief["evidence_to_collect"]:
        lines.append(f"  {item['priority']}. {item['question']}")
        lines.append(f"     Method: {item['method']}")

    lines.extend(["", "Agent prompt:", brief["agent_prompt"]])
    return "\n".join(lines) + "\n"


def _render_implementation_plan(plan: dict, *, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(plan, indent=2) + "\n"
    if fmt != "text":
        raise click.ClickException(f"Unsupported format: {fmt}")

    lines = [
        f"Implementation plan: {plan['summary']['title']}",
        f"Idea: {plan['idea_id']}",
        (
            "Readiness: "
            f"{plan['summary']['readiness_status']} "
            f"({plan['summary']['readiness_score']:.1f})"
        ),
    ]
    recommendation = plan["summary"].get("recommendation")
    if recommendation:
        lines.append(
            f"Evaluation: {recommendation} ({plan['summary'].get('overall_score', 0.0):.1f})"
        )

    lines.append("\nMilestones:")
    for milestone in plan["milestones"]:
        lines.append(f"- {milestone['id']} {milestone['title']}: {milestone['goal']}")
        for task in milestone["tasks"]:
            lines.append(f"  - {task['id']}: {task['description']}")

    lines.append("\nValidation:")
    for step in plan["validation_steps"]:
        lines.append(f"- {step['id']}: {step['description']}")

    lines.append("\nExpected files/modules:")
    for item in plan["expected_files_modules"]:
        lines.append(f"- {item['path']} ({item['role']}): {item['reason']}")

    if plan["risks"]:
        lines.append("\nRisks:")
        for risk in plan["risks"]:
            lines.append(f"- [{risk['source']}] {risk['description']}")

    if plan["open_questions"]:
        lines.append("\nOpen questions:")
        for question in plan["open_questions"]:
            lines.append(f"- {question}")

    return "\n".join(lines) + "\n"


@main.command(name="launch-checklist")
@click.argument("idea_id")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format",
)
def launch_checklist(idea_id: str, fmt: str) -> None:
    """Generate a launch checklist for an approved idea."""
    from max.spec.generator import generate_spec_preview
    from max.spec.launch_checklist import generate_launch_checklist
    from max.store.db import Store

    store = Store()
    try:
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            raise click.ClickException(f"Idea not found: {idea_id}")

        evaluation = store.get_evaluation(idea_id)
        tact_spec = generate_spec_preview(unit, evaluation)
        checklist = generate_launch_checklist(unit, evaluation, tact_spec)
        click.echo(_render_launch_checklist(checklist, fmt=fmt), nl=False)
    finally:
        store.close()


def _render_launch_checklist(checklist: dict, *, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(checklist, indent=2) + "\n"
    if fmt != "text":
        raise click.ClickException(f"Unsupported format: {fmt}")

    summary = checklist["summary"]
    lines = [
        f"Launch checklist: {summary['title']}",
        f"Idea: {checklist['idea_id']}",
        f"Gate: {summary['launch_gate']}",
    ]
    recommendation = summary.get("recommendation")
    if recommendation:
        lines.append(f"Evaluation: {recommendation} ({summary.get('overall_score', 0.0):.1f})")

    for section in checklist["sections"]:
        lines.append(f"\n{section['title']}:")
        for item in section["items"]:
            lines.append(f"- {item['id']}: {item['task']}")
            lines.append(f"  Evidence: {item['evidence']}")

    if checklist["risks"]:
        lines.append("\nRisks:")
        for risk in checklist["risks"]:
            lines.append(f"- [{risk['source']}] {risk['description']}")

    return "\n".join(lines) + "\n"


@main.command(name="experiment-card")
@click.argument("idea_id")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "markdown"]),
    default="markdown",
    show_default=True,
    help="Output format",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False),
    default=None,
    help="Write experiment card to file",
)
def experiment_card(idea_id: str, fmt: str, output: str | None) -> None:
    """Generate a deterministic experiment card for one buildable idea."""
    from max.spec.experiment_card import generate_experiment_card
    from max.store.db import Store

    store = Store()
    try:
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            raise click.ClickException(f"Idea not found: {idea_id}")

        card = generate_experiment_card(unit, store.get_evaluation(idea_id))
        rendered = _render_experiment_card(card, fmt=fmt)
        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8")
            return
        click.echo(rendered, nl=False)
    finally:
        store.close()


def _render_experiment_card(card: dict, *, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(card, indent=2) + "\n"
    if fmt != "markdown":
        raise click.ClickException(f"Unsupported format: {fmt}")

    summary = card["idea_summary"]
    lines = [
        f"# Experiment Card: {summary['title']}",
        "",
        f"**Idea:** {card['idea_id']}",
        f"**Target participant:** {card['target_participant']['persona']}",
        f"**Primary hypothesis:** {card['primary_hypothesis']}",
        "",
        "## Idea Summary",
        "",
        f"- Problem: {summary['problem']}",
        f"- Solution: {summary['solution']}",
        f"- Value proposition: {summary['value_proposition']}",
        f"- Workflow context: {summary['workflow_context'] or '-'}",
        "",
        "## Riskiest Assumptions",
        "",
    ]

    for assumption in card["riskiest_assumptions"]:
        lines.append(
            f"- **{assumption['id']}** ({assumption['source']}): {assumption['assumption']} "
            f"Test: {assumption['test_focus']}"
        )

    lines.extend(["", "## Recruitment Channels", ""])
    for channel in card["recruitment_channel_suggestions"]:
        lines.append(f"- **{channel['channel']}**: {channel['ask']}")

    test = card["minimum_viable_test"]
    lines.extend(
        [
            "",
            "## Minimum Viable Test",
            "",
            f"Type: {test['type']}",
            f"Duration: {test['duration_days']} days",
            f"Description: {test['description']}",
            "",
            "Steps:",
        ]
    )
    for step in test["steps"]:
        lines.append(f"- {step}")

    lines.extend(["", "## Success Metrics", ""])
    for metric in card["success_metrics"]:
        lines.append(f"- **{metric['metric']}**: {metric['target']}")

    lines.extend(["", "## Failure Signals", ""])
    for signal in card["failure_signals"]:
        lines.append(f"- **{signal['signal']}**: {signal['threshold']}")

    lines.extend(["", "## 7-Day Execution Plan", ""])
    for item in card["seven_day_execution_plan"]:
        lines.append(f"- **{item['day']} - {item['focus']}**: {item['actions']} Deliverable: {item['deliverable']}")

    lines.extend(["", "## Instrumentation Notes", ""])
    for note in card["instrumentation_notes"]:
        lines.append(f"- {note}")

    lines.extend(["", "## Decision Rules", ""])
    for decision, rule in card["decision_rules"].items():
        lines.append(f"- **{decision}**: {rule}")

    return "\n".join(lines) + "\n"


@main.command(name="risk-register")
@click.argument("idea_id")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format",
)
def risk_register(idea_id: str, fmt: str) -> None:
    """Generate a risk register for one buildable idea."""
    from max.analysis.contradictions import build_idea_contradiction_report
    from max.analysis.evidence_density import build_evidence_density_report
    from max.spec.risk_register import generate_risk_register
    from max.store.db import Store

    store = Store()
    try:
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            raise click.ClickException(f"Idea not found: {idea_id}")

        register = generate_risk_register(
            unit,
            store.get_evaluation(idea_id),
            build_evidence_density_report(unit, store),
            build_idea_contradiction_report(unit, store),
        )
        click.echo(_render_risk_register(register, fmt=fmt), nl=False)
    finally:
        store.close()


def _render_risk_register(register: dict, *, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(register, indent=2) + "\n"
    if fmt != "text":
        raise click.ClickException(f"Unsupported format: {fmt}")

    summary = register["summary"]
    lines = [
        f"Risk register: {summary['title']}",
        f"Idea: {register['idea_id']}",
        f"Risks: {summary['risk_count']} (critical: {summary['critical_risk_count']}, high: {summary['high_risk_count']})",
    ]
    recommendation = summary.get("recommendation")
    if recommendation:
        lines.append(f"Evaluation: {recommendation} ({summary.get('overall_score', 0.0):.1f})")

    if register["risks"]:
        lines.append("\nPrioritized risks:")
        for risk in register["risks"]:
            lines.append(
                f"{risk['priority']}. [{risk['severity']}/{risk['likelihood']}] "
                f"{risk['title']}: {risk['description']}"
            )
            if risk["evidence_links"]:
                lines.append(f"   Evidence: {', '.join(risk['evidence_links'])}")
            if risk["mitigations"]:
                lines.append(f"   Mitigation: {risk['mitigations'][0]}")
            lines.append(f"   Owner: {risk['owner_suggestion']}")
            lines.append(f"   Trigger: {risk['validation_trigger']}")
    else:
        lines.append("\nNo deterministic risks found.")

    return "\n".join(lines) + "\n"


@main.command(name="evidence-density")
@click.argument("idea_id")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format",
)
def evidence_density(idea_id: str, fmt: str) -> None:
    """Show evidence density for one idea."""
    from max.analysis.evidence_density import build_evidence_density_report
    from max.store.db import Store

    store = Store()
    try:
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            raise click.ClickException(f"Idea not found: {idea_id}")

        report = build_evidence_density_report(unit, store)
        if fmt == "json":
            click.echo(json.dumps(report, indent=2))
            return
        click.echo(_render_evidence_density(report), nl=False)
    finally:
        store.close()


def _render_evidence_density(report: dict) -> str:
    lines = [
        f"Evidence density: {report['idea_id']}",
        f"Density score:    {report['density_score']:.1f}",
        f"Signals:          {report['signal_count']}",
        f"Insights:         {report['insight_count']}",
        f"Avg credibility:  {_format_optional_float(report['average_credibility'])}",
        f"Newest evidence:  {report['newest_evidence_timestamp'] or '-'}",
        f"Oldest evidence:  {report['oldest_evidence_timestamp'] or '-'}",
        "",
        "By source adapter:",
        *_format_count_lines(report["counts_by_source_adapter"]),
        "",
        "By source type:",
        *_format_count_lines(report["counts_by_source_type"]),
        "",
        "By signal role:",
        *_format_count_lines(report["counts_by_signal_role"]),
    ]
    if report["missing_evidence_warnings"]:
        lines.extend(["", "Warnings:"])
        lines.extend(f"  - {warning}" for warning in report["missing_evidence_warnings"])
    return "\n".join(lines) + "\n"


@main.command(name="contradictions")
@click.argument("entity_id")
@click.option(
    "--entity-type",
    type=click.Choice(["auto", "idea", "insight"]),
    default="auto",
    show_default=True,
    help="Evidence entity type",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format",
)
def contradictions(entity_id: str, entity_type: str, fmt: str) -> None:
    """Show contradictory evidence for an idea or insight."""
    from max.analysis.contradictions import (
        build_idea_contradiction_report,
        build_insight_contradiction_report,
    )
    from max.store.db import Store

    store = Store()
    try:
        report: dict | None = None
        if entity_type in ("auto", "idea"):
            unit = store.get_buildable_unit(entity_id)
            if unit:
                report = build_idea_contradiction_report(unit, store)
            elif entity_type == "idea":
                raise click.ClickException(f"Idea not found: {entity_id}")

        if report is None and entity_type in ("auto", "insight"):
            insight = store.get_insight(entity_id)
            if insight:
                report = build_insight_contradiction_report(insight, store)
            elif entity_type == "insight":
                raise click.ClickException(f"Insight not found: {entity_id}")

        if report is None:
            raise click.ClickException(f"Idea or insight not found: {entity_id}")

        if fmt == "json":
            click.echo(json.dumps(report, indent=2))
            return
        click.echo(_render_contradictions(report), nl=False)
    finally:
        store.close()


def _render_contradictions(report: dict) -> str:
    lines = [
        f"Contradictions: {report['entity_type']} {report['entity_id']}",
        f"Signals:        {report['signal_count']}",
        f"Conflicts:      {report['contradiction_count']}",
    ]
    contradictions = report["contradictions"]
    if not contradictions:
        lines.extend(["", "No contradictions detected."])
        return "\n".join(lines) + "\n"

    for item in contradictions:
        lines.extend(
            [
                "",
                f"- {item['severity'].upper()} {item['group_type']}: {item['claim']}",
                f"  Signals: {', '.join(item['involved_signal_ids'])}",
                f"  Sources: {', '.join(item['sources'])}",
                f"  Note: {item['suggested_review_note']}",
            ]
        )
    return "\n".join(lines) + "\n"


def _format_count_lines(counts: dict[str, int]) -> list[str]:
    if not counts:
        return ["  - none: 0"]
    return [f"  - {key}: {value}" for key, value in counts.items()]


def _format_optional_float(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


@main.command(name="roi-forecast")
@click.option("--domain", "-d", type=str, default=None, help="Filter by domain")
@click.option("--status", type=str, default=None, help="Filter by idea status")
@click.option("--profile", "-p", type=str, default=None, help="Use a pipeline profile's evaluation weights")
@click.option("--weight-profile", type=str, default=None, help="Use a named evaluation weight profile")
@click.option("--limit", type=int, default=100, show_default=True, help="Maximum ideas to rank")
@click.option("--json", "as_json", is_flag=True, help="Print report as JSON")
def roi_forecast(
    domain: str | None,
    status: str | None,
    profile: str | None,
    weight_profile: str | None,
    limit: int,
    as_json: bool,
) -> None:
    """Rank ideas by rough return on implementation effort."""
    from dataclasses import asdict

    from max.analysis.roi_forecast import generate_roi_forecast
    from max.evaluation.weights import WEIGHT_PROFILES
    from max.profiles.loader import load_profile
    from max.store.db import Store

    if limit < 1:
        raise click.ClickException("--limit must be at least 1")
    if profile and weight_profile:
        raise click.ClickException("Use either --profile or --weight-profile, not both")

    profile_input = None
    if profile:
        try:
            profile_input = load_profile(profile)
        except FileNotFoundError as e:
            raise click.ClickException(str(e)) from e
    elif weight_profile:
        if weight_profile not in WEIGHT_PROFILES:
            available = ", ".join(sorted(WEIGHT_PROFILES))
            raise click.ClickException(
                f"Unknown weight profile: {weight_profile}. Available: {available}"
            )
        profile_input = weight_profile

    store = Store()
    try:
        units = store.get_buildable_units(limit=limit, status=status, domain=domain)
        evaluations = {unit.id: store.get_evaluation(unit.id) for unit in units}
        report = generate_roi_forecast(units, evaluations, profile=profile_input)
    finally:
        store.close()

    if as_json:
        click.echo(json.dumps(asdict(report), indent=2))
        return

    if not report.results:
        click.echo("No ideas found for ROI forecast.")
        return

    click.echo(
        f"ROI forecast ({report.total_units} ideas, {report.evaluated_units} evaluated, "
        f"weights: {report.weight_profile})"
    )
    click.echo(
        f"{'#':>3s} {'ROI':>6s} {'Eval':>6s} {'Evid':>5s} {'Cx':>4s} "
        f"{'Conf':>5s} {'Rec':<10s} Title"
    )
    click.echo("-" * 88)
    for item in report.results:
        eval_score = "-" if item.evaluation_score is None else f"{item.evaluation_score:.1f}"
        recommendation = item.recommendation or "-"
        click.echo(
            f"{item.rank:>3d} "
            f"{item.roi_score:>6.1f} "
            f"{eval_score:>6s} "
            f"{item.evidence_count:>5d} "
            f"{item.estimated_complexity:>4.1f} "
            f"{item.confidence:>5.2f} "
            f"{recommendation:<10.10s} "
            f"{item.title}"
        )


@main.command()
@click.argument("unit_id")
@click.argument("outcome", type=click.Choice(["approved", "rejected", "abandoned"]))
@click.option("--reason", "-r", type=str, default="", help="Reason for the feedback")
@click.option("--score", "-s", type=int, default=None, help="Approval score 1-10 (only for approved)")
def feedback(unit_id: str, outcome: str, reason: str, score: int | None) -> None:
    """Record feedback on a buildable unit (approved/rejected/abandoned)."""
    from max.store.db import Store

    if score is not None:
        if outcome != "approved":
            click.echo("Error: --score is only valid for 'approved' outcome.")
            return
        if not 1 <= score <= 10:
            click.echo("Error: --score must be between 1 and 10.")
            return

    store = Store()
    try:
        unit = store.get_buildable_unit(unit_id)
        if not unit:
            click.echo(f"Not found: {unit_id}")
            return

        if score is None:
            store.insert_feedback(unit_id, outcome, reason)
        else:
            store.insert_feedback(unit_id, outcome, reason, approval_score=score)
        store.update_buildable_unit_status(unit_id, outcome)
        score_label = f" ({score}/10)" if score is not None else ""
        click.echo(f"Recorded: {unit.title} → {outcome}{score_label}")
    finally:
        store.close()


@main.command(name="review-thresholds")
@click.option("--domain", "-d", type=str, default=None, help="Filter by domain")
@click.option("--min-samples", type=int, default=None, help="Minimum feedback samples before adapting")
@click.option("--json", "as_json", is_flag=True, help="Print recommendations as JSON")
def review_thresholds(domain: str | None, min_samples: int | None, as_json: bool) -> None:
    """Recommend review thresholds from historical feedback."""
    from max.analysis.thresholds import (
        DEFAULT_APPROVE_THRESHOLD,
        DEFAULT_MIN_SAMPLES,
        DEFAULT_REJECT_THRESHOLD,
        recommend_review_thresholds,
    )
    from max.store.db import Store

    effective_min_samples = min_samples or DEFAULT_MIN_SAMPLES
    if effective_min_samples < 1:
        raise click.ClickException("--min-samples must be at least 1")

    store = Store()
    try:
        recommendations = recommend_review_thresholds(
            store,
            domain=domain,
            min_samples=effective_min_samples,
        )
        payload = {
            "min_samples": effective_min_samples,
            "default_approve_threshold": DEFAULT_APPROVE_THRESHOLD,
            "default_reject_threshold": DEFAULT_REJECT_THRESHOLD,
            "recommendations": [item.__dict__ for item in recommendations],
        }
        if as_json:
            click.echo(json.dumps(payload, indent=2))
            return

        if not recommendations:
            click.echo("No reviewed evaluations found.")
            return

        click.echo(
            f"{'Domain':<20s} {'Approve':>8s} {'Reject':>8s} "
            f"{'Samples':>8s} {'Approved':>8s} {'Rejected':>8s} {'Source'}"
        )
        click.echo("-" * 88)
        for item in recommendations:
            source = "fallback" if item.fallback_used else "history"
            if not item.sufficient_samples:
                source = "insufficient"
            click.echo(
                f"{(item.domain or '-'):20.20s} "
                f"{item.approve_threshold:8.1f} "
                f"{item.reject_threshold:8.1f} "
                f"{item.sample_count:8d} "
                f"{item.approved_count:8d} "
                f"{item.rejected_count:8d} "
                f"{source}"
            )
        click.echo(
            f"\nDefaults: approve >= {DEFAULT_APPROVE_THRESHOLD:.1f}, "
            f"reject < {DEFAULT_REJECT_THRESHOLD:.1f}; min samples: {effective_min_samples}"
        )
    finally:
        store.close()


@main.command(name="review-gate")
@click.argument("idea_id")
@click.option("--json", "as_json", is_flag=True, help="Print decision as JSON")
def review_gate(idea_id: str, as_json: bool) -> None:
    """Recommend approve, revision, hold, or reject for one idea."""
    from max.analysis.review_gate import build_review_gate_decision
    from max.store.db import Store

    store = Store()
    try:
        try:
            decision = asdict(build_review_gate_decision(store, idea_id))
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc

        click.echo(_render_review_gate(decision, as_json=as_json), nl=False)
    finally:
        store.close()


def _render_review_gate(decision: dict, *, as_json: bool) -> str:
    if as_json:
        return json.dumps(decision, indent=2) + "\n"

    lines = [
        f"Review gate: {decision['title']}",
        f"Idea: {decision['idea_id']}",
        f"Decision: {decision['decision']}",
        f"Confidence: {decision['confidence']:.2f}",
    ]
    if decision["blocking_reasons"]:
        lines.append("\nBlocking reasons:")
        for reason in decision["blocking_reasons"]:
            lines.append(f"- {reason}")
    if decision["warnings"]:
        lines.append("\nWarnings:")
        for warning in decision["warnings"]:
            lines.append(f"- {warning}")
    if decision["required_remediations"]:
        lines.append("\nRequired remediations:")
        for remediation in decision["required_remediations"]:
            lines.append(f"- {remediation}")
    if decision["evidence_used"]:
        lines.append("\nEvidence used:")
        for evidence in decision["evidence_used"]:
            score = "" if evidence["score"] is None else f" ({evidence['score']:.1f})"
            lines.append(f"- {evidence['source']}: {evidence['status']}{score}")
    return "\n".join(lines) + "\n"


@main.command(name="evaluation-calibration")
@click.option("--domain", "-d", type=str, default=None, help="Filter by domain")
@click.option("--min-samples", type=int, default=1, help="Minimum samples per group")
@click.option("--limit", type=int, default=50, help="Maximum groups to show")
@click.option("--json", "as_json", is_flag=True, help="Print report as JSON")
def evaluation_calibration(
    domain: str | None,
    min_samples: int,
    limit: int,
    as_json: bool,
) -> None:
    """Compare evaluation scores against feedback outcomes."""
    from max.analysis.evaluation_calibration import build_evaluation_calibration_report
    from max.store.db import Store

    if min_samples < 1:
        raise click.ClickException("--min-samples must be at least 1")
    if limit < 1:
        raise click.ClickException("--limit must be at least 1")

    store = Store()
    try:
        report = build_evaluation_calibration_report(
            store,
            domain=domain,
            min_samples=min_samples,
            limit=limit,
        )
        if as_json:
            click.echo(json.dumps(asdict(report), indent=2))
            return

        _render_evaluation_calibration(report)
    finally:
        store.close()


@main.command(name="diagnostics")
@click.option("--profile", "-p", type=str, default=None, help="Profile name for coverage analysis")
@click.option("--domain", "-d", type=str, default=None, help="Domain filter for calibration")
@click.option("--limit", type=int, default=20, show_default=True, help="Rows to include per section")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json"]),
    default="table",
    show_default=True,
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON")
def diagnostics(profile: str | None, domain: str | None, limit: int, fmt: str, as_json: bool) -> None:
    """Show combined feedback, coverage, and calibration diagnostics."""
    from max.analysis.evaluation_calibration import build_evaluation_calibration_report
    from max.analysis.profile_coverage import compute_profile_coverage_gaps
    from max.config import MAX_PROFILE
    from max.profiles.loader import get_default_profile, load_profile
    from max.store.db import Store

    if limit < 1:
        raise click.ClickException("--limit must be at least 1")

    profile_name = profile or MAX_PROFILE or None
    try:
        pipeline_profile = load_profile(profile_name) if profile_name else get_default_profile()
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    store = Store()
    try:
        feedback_log = store.get_feedback_log(limit=limit)
        coverage_report = compute_profile_coverage_gaps(pipeline_profile, store)
        calibration_report = build_evaluation_calibration_report(
            store,
            domain=domain,
            limit=limit,
        )
        payload = {
            "selectors": {
                "profile": pipeline_profile.name,
                "domain": domain,
                "limit": limit,
            },
            "feedback_history": {
                "limit": limit,
                "count": len(feedback_log),
                "records": feedback_log,
            },
            "profile_coverage": asdict(coverage_report),
            "evaluation_calibration": asdict(calibration_report),
        }
        if as_json or fmt == "json":
            click.echo(json.dumps(payload, indent=2))
            return

        _render_diagnostics_report(
            pipeline_profile,
            domain=domain,
            limit=limit,
            feedback_log=feedback_log,
            coverage_report=coverage_report,
            calibration_report=calibration_report,
        )
    finally:
        store.close()


@main.command()
@click.option("--domain", "-d", type=str, default=None, help="Filter by domain")
@click.option("--approve-threshold", type=float, default=68.0, help="Auto-approve score threshold (default: 68)")
@click.option("--reject-threshold", type=float, default=50.0, help="Auto-reject score threshold (default: 50)")
@click.option("--dry-run", is_flag=True, help="Show what would be triaged without applying changes")
@click.option("--limit", type=int, default=500, help="Max ideas to consider")
@click.option("--include-archived", is_flag=True, help="Include archived out-of-focus ideas")
def triage(domain: str | None, approve_threshold: float, reject_threshold: float, dry_run: bool, limit: int, include_archived: bool) -> None:
    """Auto-approve/reject ideas by score thresholds.

    Default thresholds: auto-approve >= 68 with rec=yes, auto-reject < 50 or rec=no.
    Remaining ideas are left for human review.
    """
    from max.analysis.status import can_transition_buildable_unit_status
    from max.store.db import Store

    store = Store()
    try:
        units = store.get_buildable_units(limit=limit, domain=domain)
        if not include_archived:
            units = [u for u in units if u.status != "archived"]
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
                if can_transition_buildable_unit_status(unit.status, "approved"):
                    auto_approved.append((unit, ev))
            elif ev.overall_score < reject_threshold or ev.recommendation == "no":
                if can_transition_buildable_unit_status(unit.status, "rejected"):
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
@click.option("--include-archived", is_flag=True, help="Include archived out-of-focus ideas")
def dedup(threshold: float, domain: str | None, dry_run: bool, limit: int, include_archived: bool) -> None:
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
        skip_statuses = {"duplicate"} if include_archived else {"duplicate", "archived"}
        for unit in units:
            if unit.status in skip_statuses:
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
            rep_tag = f" ({rep.status})" if rep.status in ("approved", "rejected") else ""
            click.echo(f"  Cluster {i} ({cluster.size} ideas, domains: {', '.join(sorted(cluster.domains))})")
            click.echo(f"    KEEP: {rep_score:5.1f}  [{rep.domain}]  {rep.title}{rep_tag}")
            for unit, ev in cluster.duplicates:
                score = ev.overall_score if ev else 0.0
                # Show whether this duplicate's existing status will be preserved
                if unit.status in ("approved", "rejected"):
                    marker = f"SKIP({unit.status})"
                else:
                    marker = "DUP "
                click.echo(f"    {marker}: {score:5.1f}  [{unit.domain}]  {unit.title}")
            click.echo()

        if dry_run:
            click.echo("DRY RUN: No changes applied.")
            return

        # Mark duplicates — preserve prior user decisions (approved/rejected)
        marked = 0
        preserved = 0
        for cluster in dup_clusters:
            for unit, ev in cluster.duplicates:
                if unit.status in ("approved", "rejected"):
                    preserved += 1
                    continue
                reason = f"duplicate of {cluster.representative.id} ({cluster.representative.title[:50]})"
                store.insert_feedback(unit.id, "rejected", f"auto-dedup: {reason}")
                store.update_buildable_unit_status(unit.id, "duplicate")
                marked += 1

        msg = f"Marked {marked} ideas as duplicate."
        if preserved:
            msg += f" Preserved {preserved} with existing user feedback."
        click.echo(msg)
    finally:
        store.close()


@main.command()
@click.option("--incremental", is_flag=True, help="Only embed new or changed ideas (skip unchanged)")
@click.option("--entity-type", type=str, default="buildable_unit", help="Entity type to embed (default: buildable_unit)")
def embed(incremental: bool, entity_type: str) -> None:
    """Build or update the semantic embedding index.

    By default, re-embeds all entities. With --incremental, only processes
    new or changed entities based on content hash comparison.
    """
    from max.embeddings.engine import SemanticIndex
    from max.store.db import Store

    store = Store()
    try:
        idx = SemanticIndex(store)

        if incremental:
            click.echo("Running incremental embedding update...")
            result = idx.embed_incremental(entity_type=entity_type)
            click.echo(f"  Embedded: {result['embedded']} (new/changed)")
            click.echo(f"  Skipped:  {result['skipped']} (unchanged)")
            click.echo(f"  Removed:  {result['removed']} (deleted)")
        else:
            click.echo("Running full embedding rebuild...")
            result = idx.embed_full(entity_type=entity_type)
            click.echo(f"  Embedded: {result['embedded']}")
    finally:
        store.close()


@main.command()
@click.option("--threshold", type=float, default=0.85, help="Similarity threshold for clustering (default: 0.85)")
@click.option("--domain", "-d", type=str, default=None, help="Filter by domain")
@click.option("--cross-cluster", is_flag=True, help="Also find and merge complementary ideas across clusters (more LLM calls)")
@click.option("--max-cross-groups", type=int, default=5, help="Maximum cross-cluster groups to synthesize (default: 5)")
@click.option("--dry-run", is_flag=True, help="Show clusters without LLM calls")
@click.option("--limit", type=int, default=500, help="Max ideas to consider")
@click.option("--include-archived", is_flag=True, help="Include archived out-of-focus ideas")
def synthesize(threshold: float, domain: str | None, cross_cluster: bool, max_cross_groups: int, dry_run: bool, limit: int, include_archived: bool) -> None:
    """Synthesize clustered ideas into superior combined ideas.

    For each cluster with multiple similar ideas, uses LLM to merge them
    into one superior idea. With --cross-cluster, also identifies complementary
    ideas across clusters and merges those.

    Cadence: dedup -> synthesize -> prior-art -> review
    """
    from max.analysis.dedup import cluster_ideas
    from max.analysis.synthesize_ideas import run_synthesis
    from max.store.db import Store

    store = Store()
    try:
        units = store.get_buildable_units(limit=limit, domain=domain)
        # Only consider evaluated ideas that aren't rejected/duplicate/synthesized
        skip_statuses = {"rejected", "duplicate", "synthesized"}
        if not include_archived:
            skip_statuses.add("archived")
        active = [
            u for u in units
            if u.status not in skip_statuses
        ]

        if not active:
            click.echo("No ideas to synthesize.")
            return

        # Build (unit, eval) pairs
        pairs = []
        for u in active:
            ev = store.get_evaluation(u.id)
            if ev:
                pairs.append((u, ev))

        if not pairs:
            click.echo("No evaluated ideas to synthesize.")
            return

        clusters = cluster_ideas(pairs, similarity_threshold=threshold)
        multi_clusters = [c for c in clusters if c.size > 1]

        if not multi_clusters and not cross_cluster:
            click.echo(f"No multi-member clusters found at threshold {threshold}. Nothing to synthesize.")
            return

        click.echo(f"Found {len(multi_clusters)} multi-member clusters ({sum(c.size for c in multi_clusters)} ideas).")

        if dry_run:
            for i, cluster in enumerate(multi_clusters, 1):
                click.echo(f"\n  Cluster {i} ({cluster.size} ideas):")
                for unit, ev in cluster.members:
                    score = ev.overall_score if ev else 0.0
                    click.echo(f"    {score:5.1f}  [{unit.domain}] {unit.title}")
            if cross_cluster:
                singletons = [c.representative for c in clusters if c.size == 1]
                click.echo(f"\n  Cross-cluster: would analyze {len(singletons)} singletons for complementary groups")
            click.echo("\nDry run — no LLM calls made.")
            return

        click.echo("Synthesizing...")
        result = run_synthesis(
            clusters,
            cross_cluster=cross_cluster,
            max_cross_groups=max_cross_groups,
        )

        # Store intra-cluster synthesized ideas and update source statuses
        for new_unit in result.intra_synthesized:
            stored = store.insert_buildable_unit(new_unit)
            click.echo(f"\n  Synthesized: \"{stored.title}\"")
            for src_id in new_unit.source_idea_ids:
                src_unit = store.get_buildable_unit(src_id)
                src_title = src_unit.title[:40] if src_unit else src_id
                ev = store.get_evaluation(src_id)
                score = ev.overall_score if ev else 0.0
                click.echo(f"    <- {score:5.1f}  {src_title}")
                store.insert_feedback(src_id, "synthesized", f"merged into {stored.id}")
                store.update_buildable_unit_status(src_id, "synthesized")

        # Store cross-cluster synthesized ideas
        for new_unit in result.cross_synthesized:
            stored = store.insert_buildable_unit(new_unit)
            click.echo(f"\n  Cross-synthesized: \"{stored.title}\"")
            for src_id in new_unit.source_idea_ids:
                src_unit = store.get_buildable_unit(src_id)
                src_title = src_unit.title[:40] if src_unit else src_id
                click.echo(f"    <- {src_title}")
                store.insert_feedback(src_id, "synthesized", f"cross-merged into {stored.id}")
                store.update_buildable_unit_status(src_id, "synthesized")

        total = len(result.intra_synthesized) + len(result.cross_synthesized)
        click.echo(f"\nSummary: {total} synthesized ideas from {len(result.source_idea_ids)} source ideas")
        if result.intra_synthesized:
            click.echo(f"  Intra-cluster: {len(result.intra_synthesized)}")
        if result.cross_synthesized:
            click.echo(f"  Cross-cluster: {len(result.cross_synthesized)} (from {result.complementary_groups_found} groups)")
    finally:
        store.close()


@main.command(name="design-candidates")
@click.option("--domain", "-d", type=str, default=None, help="Filter by domain")
@click.option("--limit", type=int, default=500, help="Max reviewed ideas to consider")
@click.option("--top", type=int, default=8, help="Number of project briefs to output")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown", help="Output format")
@click.option("--output", "-o", type=click.Path(), default=None, help="Write report to file")
@click.option("--persist/--no-persist", default=True, help="Persist generated briefs to max.db")
def design_candidates(
    domain: str | None,
    limit: int,
    top: int,
    fmt: str,
    output: str | None,
    persist: bool,
) -> None:
    """Synthesize approved ideas into implementation-ready design candidates."""
    from max.analysis.portfolio_synthesis import (
        build_candidates,
        render_json,
        render_markdown,
        synthesize_project_briefs,
        write_briefs,
    )
    from max.store.db import Store

    store = Store()
    try:
        units = store.get_buildable_units(limit=limit, domain=domain)
        evaluations = {unit.id: store.get_evaluation(unit.id) for unit in units}
        feedback = {unit.id: store.get_latest_feedback(unit.id) for unit in units}

        candidates = build_candidates(
            units,
            evaluations=evaluations,
            feedback=feedback,
        )
        if not candidates:
            click.echo("No approved or published ideas found.")
            return

        briefs = synthesize_project_briefs(candidates, top=top)
        persisted_ids = []
        if persist:
            persisted_ids = [store.insert_design_brief(brief) for brief in briefs]
        if output:
            write_briefs(Path(output), briefs, fmt=fmt)
            message = f"Wrote {len(briefs)} design candidate brief(s) to {output}"
            if persisted_ids:
                message += f" and persisted {len(persisted_ids)} to max.db"
            click.echo(message)
            return

        rendered = render_json(briefs) if fmt == "json" else render_markdown(briefs)
        click.echo(rendered)
        if persisted_ids:
            click.echo()
            click.echo("Persisted design brief IDs:")
            for brief_id in persisted_ids:
                click.echo(f"  {brief_id}")
    finally:
        store.close()


@main.group(name="design-briefs", invoke_without_command=True)
@click.pass_context
@click.option("--domain", "-d", type=str, default=None, help="Filter by domain")
@click.option("--status", type=str, default=None, help="Filter by design status")
@click.option("--limit", type=int, default=20, help="Max briefs to list")
def design_briefs(ctx: click.Context, domain: str | None, status: str | None, limit: int) -> None:
    """Inspect and export persisted design briefs."""
    if ctx.invoked_subcommand is not None:
        return
    _list_design_briefs(domain=domain, status=status, limit=limit)


@design_briefs.command(name="list")
@click.option("--domain", "-d", type=str, default=None, help="Filter by domain")
@click.option("--status", type=str, default=None, help="Filter by design status")
@click.option("--limit", type=int, default=20, help="Max briefs to list")
def design_briefs_list(domain: str | None, status: str | None, limit: int) -> None:
    """List persisted design briefs."""
    _list_design_briefs(domain=domain, status=status, limit=limit)


def _list_design_briefs(domain: str | None, status: str | None, limit: int) -> None:
    """List persisted design briefs."""
    from max.store.db import Store

    store = Store()
    try:
        briefs = store.get_design_briefs(domain=domain, status=status, limit=limit)
        if not briefs:
            click.echo("No design briefs found.")
            return
        for brief in briefs:
            click.echo(
                f"{brief['id']}  {brief['readiness_score']:5.1f}  "
                f"[{brief['design_status']}] [{brief['domain']}] {brief['title']}"
            )
            click.echo(f"  Lead: {brief['lead_idea_id']} | Sources: {len(brief['source_idea_ids'])}")
    finally:
        store.close()


@design_briefs.command(name="show")
@click.argument("design_brief_id")
def design_briefs_show(design_brief_id: str) -> None:
    """Show a persisted design brief."""
    from max.store.db import Store

    store = Store()
    try:
        brief = store.get_design_brief(design_brief_id)
        if not brief:
            raise click.ClickException(f"Design brief not found: {design_brief_id}")

        click.echo(f"ID:          {brief['id']}")
        click.echo(f"Title:       {brief['title']}")
        click.echo(f"Domain:      {brief['domain']}")
        click.echo(f"Theme:       {brief['theme']}")
        click.echo(f"Status:      {brief['design_status']}")
        click.echo(f"Readiness:   {brief['readiness_score']:.1f}")
        click.echo(f"Lead idea:   {brief['lead_idea_id']}")
        click.echo(f"Buyer:       {brief['buyer'] or '-'}")
        click.echo(f"User:        {brief['specific_user'] or '-'}")
        click.echo(f"Workflow:    {brief['workflow_context'] or '-'}")
        click.echo()
        click.echo(f"Why now:     {brief['why_this_now']}")
        click.echo(f"Concept:     {brief['merged_product_concept']}")
        click.echo(f"Rationale:   {brief['synthesis_rationale']}")
        click.echo(f"Validation:  {brief['validation_plan']}")

        if brief["mvp_scope"]:
            click.echo()
            click.echo("MVP scope:")
            for item in brief["mvp_scope"]:
                click.echo(f"  - {item}")
        if brief["first_milestones"]:
            click.echo("First milestones:")
            for item in brief["first_milestones"]:
                click.echo(f"  - {item}")
        if brief["risks"]:
            click.echo("Risks:")
            for item in brief["risks"]:
                click.echo(f"  - {item}")

        click.echo()
        click.echo(f"Source ideas ({len(brief['source_idea_ids'])}):")
        for source_id in brief["source_idea_ids"]:
            click.echo(f"  {source_id}")
    finally:
        store.close()


@design_briefs.command(name="status")
@click.argument("design_brief_id")
@click.argument("status")
def design_briefs_status(design_brief_id: str, status: str) -> None:
    """Update design workflow status for a brief."""
    from max.store.db import Store

    store = Store()
    try:
        brief = store.get_design_brief(design_brief_id)
        if not brief:
            raise click.ClickException(f"Design brief not found: {design_brief_id}")
        store.update_design_brief_status(design_brief_id, status)
        click.echo(f"Updated {design_brief_id}: {brief['design_status']} -> {status}")
    finally:
        store.close()


@design_briefs.command(name="blueprint")
@click.argument("design_brief_id")
@click.option(
    "--output",
    "-o",
    type=click.Path(file_okay=False),
    default=None,
    help="Write JSON packet to this directory",
)
def design_briefs_blueprint(design_brief_id: str, output: str | None) -> None:
    """Export one design brief as Blueprint JSON."""
    from max.analysis.blueprint_export import (
        blueprint_filename,
        build_blueprint_source_brief,
        render_blueprint_packet,
        write_blueprint_packet,
    )
    from max.store.db import Store

    store = Store()
    try:
        brief = store.get_design_brief(design_brief_id)
        if not brief:
            raise click.ClickException(f"Design brief not found: {design_brief_id}")
        packet = build_blueprint_source_brief(store, brief)
        if output:
            output_dir = Path(output)
            path = output_dir / blueprint_filename(brief, fmt="json")
            write_blueprint_packet(path, packet, fmt="json")
            click.echo(f"Wrote Blueprint source brief to {path}")
            return
        click.echo(render_blueprint_packet(packet, fmt="json"), nl=False)
    finally:
        store.close()


@design_briefs.command(name="validation-plan")
@click.argument("design_brief_id")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
    help="Output format",
)
@click.option("--output", "-o", type=click.Path(), default=None, help="Write plan to file")
def design_briefs_validation_plan(
    design_brief_id: str,
    fmt: str,
    output: str | None,
) -> None:
    """Export a deterministic validation plan for a design brief."""
    from max.analysis.design_validation import (
        build_validation_plan,
        render_validation_plan,
        write_validation_plan,
    )
    from max.store.db import Store

    store = Store()
    try:
        brief = store.get_design_brief(design_brief_id)
        if not brief:
            raise click.ClickException(f"Design brief not found: {design_brief_id}")
        plan = build_validation_plan(store, brief)
        if output:
            write_validation_plan(Path(output), plan, fmt=fmt)
            click.echo(f"Wrote validation plan to {output}")
            return
        click.echo(render_validation_plan(plan, fmt=fmt), nl=False)
    finally:
        store.close()


@design_briefs.command(name="market-sizing")
@click.argument("design_brief_id")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
    help="Output format",
)
@click.option("--output", "-o", type=click.Path(), default=None, help="Write report to file")
def design_briefs_market_sizing(
    design_brief_id: str,
    fmt: str,
    output: str | None,
) -> None:
    """Export a deterministic market-sizing report for a design brief."""
    from max.analysis.market_sizing import (
        build_market_sizing_report,
        render_market_sizing_report,
        write_market_sizing_report,
    )
    from max.store.db import Store

    store = Store()
    try:
        brief = store.get_design_brief(design_brief_id)
        if not brief:
            raise click.ClickException(f"Design brief not found: {design_brief_id}")
        report = build_market_sizing_report(store, brief)
        if output:
            write_market_sizing_report(Path(output), report, fmt=fmt)
            click.echo(f"Wrote market-sizing report to {output}")
            return
        click.echo(render_market_sizing_report(report, fmt=fmt), nl=False)
    finally:
        store.close()


@design_briefs.command(name="outreach-pack")
@click.argument("design_brief_id")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
    help="Output format",
)
@click.option("--output", "-o", type=click.Path(), default=None, help="Write outreach pack to file")
def design_briefs_outreach_pack(
    design_brief_id: str,
    fmt: str,
    output: str | None,
) -> None:
    """Export a deterministic pilot outreach pack for a design brief."""
    from max.analysis.design_brief_outreach_pack import (
        build_design_brief_outreach_pack,
        render_design_brief_outreach_pack,
        write_design_brief_outreach_pack,
    )
    from max.store.db import Store

    store = Store()
    try:
        pack = build_design_brief_outreach_pack(store, design_brief_id)
        if not pack:
            raise click.ClickException(f"Design brief not found: {design_brief_id}")
        if output:
            write_design_brief_outreach_pack(Path(output), pack, fmt=fmt)
            click.echo(f"Wrote outreach pack to {output}")
            return
        click.echo(render_design_brief_outreach_pack(pack, fmt=fmt), nl=False)
    finally:
        store.close()


@main.command(name="export-design-brief")
@click.argument("design_brief_id")
@click.option("--format", "fmt", type=click.Choice(["json", "yaml"]), default="json")
@click.option("--output", "-o", type=click.Path(), default=None, help="Write packet to file")
def export_design_brief(design_brief_id: str, fmt: str, output: str | None) -> None:
    """Export one design brief as a Blueprint source-brief packet."""
    from max.analysis.blueprint_export import (
        build_blueprint_source_brief,
        render_blueprint_packet,
        write_blueprint_packet,
    )
    from max.store.db import Store

    store = Store()
    try:
        brief = store.get_design_brief(design_brief_id)
        if not brief:
            raise click.ClickException(f"Design brief not found: {design_brief_id}")
        packet = build_blueprint_source_brief(store, brief)
        if output:
            write_blueprint_packet(Path(output), packet, fmt=fmt)
            click.echo(f"Wrote Blueprint source brief to {output}")
            return
        click.echo(render_blueprint_packet(packet, fmt=fmt), nl=False)
    finally:
        store.close()


@main.command(name="export-design-briefs")
@click.option("--domain", "-d", type=str, default=None, help="Filter by domain")
@click.option("--status", type=str, default=None, help="Filter by design status")
@click.option("--limit", type=int, default=20, help="Max briefs to export")
@click.option("--format", "fmt", type=click.Choice(["json", "yaml"]), default="json")
@click.option("--output", "-o", type=click.Path(file_okay=False), required=True, help="Output directory")
def export_design_briefs(
    domain: str | None,
    status: str | None,
    limit: int,
    fmt: str,
    output: str,
) -> None:
    """Export multiple design briefs as Blueprint source-brief packets."""
    from max.analysis.blueprint_export import (
        blueprint_filename,
        build_blueprint_source_brief,
        write_blueprint_packet,
    )
    from max.store.db import Store

    store = Store()
    try:
        briefs = store.get_design_briefs(domain=domain, status=status, limit=limit)
        if not briefs:
            click.echo("No design briefs found.")
            return
        output_dir = Path(output)
        for brief in briefs:
            packet = build_blueprint_source_brief(store, brief)
            write_blueprint_packet(output_dir / blueprint_filename(brief, fmt=fmt), packet, fmt=fmt)
        click.echo(f"Wrote {len(briefs)} Blueprint source brief(s) to {output_dir}")
    finally:
        store.close()


@main.group(name="domain-quality")
def domain_quality() -> None:
    """Inspect domain quality scores and memory."""


@domain_quality.command(name="score")
@click.argument("idea_id")
def domain_quality_score(idea_id: str) -> None:
    """Show domain quality scores for one idea."""
    from max.store.db import Store

    store = Store()
    try:
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            raise click.ClickException(f"Idea not found: {idea_id}")
        scores = store.get_domain_quality_scores(idea_id)
        if not scores:
            click.echo("No domain quality scores found.")
            return
        for score in scores:
            passed = "passed" if score["passed_gate"] else "rejected"
            click.echo(
                f"{score['created_at']}  {score['overall_score']:.1f}  "
                f"[{passed}] [{score['domain']}] {unit.title}"
            )
            if score["rejection_tags"]:
                click.echo(f"  Tags: {', '.join(score['rejection_tags'])}")
            click.echo(f"  {score['reasoning']}")
    finally:
        store.close()


@domain_quality.command(name="memory")
@click.option("--domain", "-d", type=str, default=None, help="Filter by domain")
@click.option("--outcome", type=click.Choice(["approved", "rejected"]), default=None)
@click.option("--limit", type=int, default=20)
def domain_quality_memory(domain: str | None, outcome: str | None, limit: int) -> None:
    """List domain quality memory patterns."""
    from max.store.db import Store

    store = Store()
    try:
        rows = store.get_domain_quality_memory(domain=domain, outcome=outcome, limit=limit)
        if not rows:
            click.echo("No domain quality memory found.")
            return
        for row in rows:
            click.echo(
                f"{row['created_at']}  [{row['outcome']}] "
                f"[{row['domain']}] {row['pattern']}"
            )
            if row["tags"]:
                click.echo(f"  Tags: {', '.join(row['tags'])}")
    finally:
        store.close()


@domain_quality.command(name="eval")
@click.option("--profile", "-p", type=str, required=True, help="Profile to evaluate")
@click.option("--signal-limit", type=int, default=None, help="Override profile signal limit")
@click.option("--draft-count", type=int, default=None, help="Override profile draft count")
@click.option("--quality-loop/--no-quality-loop", default=True, help="Run existing critique/revision loop")
@click.option("--stages", type=str, default="ideate,evaluate", help="Comma-separated pipeline stages")
@click.option("--notes", type=str, default="", help="Notes to store on the eval run")
def domain_quality_eval(
    profile: str,
    signal_limit: int | None,
    draft_count: int | None,
    quality_loop: bool,
    stages: str,
    notes: str,
) -> None:
    """Run baseline and rubric cohorts and persist a domain quality eval."""
    from datetime import datetime, timezone

    from max.pipeline.runner import run_pipeline
    from max.profiles.loader import load_profile
    from max.store.db import Store

    base_profile = load_profile(profile)
    if signal_limit is not None:
        base_profile.signal_limit = signal_limit
    if draft_count is not None:
        base_profile.draft_count = draft_count
    base_profile.quality_loop_enabled = quality_loop
    active_stages = [stage.strip() for stage in stages.split(",") if stage.strip()]
    domain_name = base_profile.domain.name
    started_at = datetime.now(timezone.utc).isoformat()

    baseline_profile = base_profile.model_copy(deep=True)
    baseline_profile.domain_quality.enabled = False
    rubric_profile = base_profile.model_copy(deep=True)
    rubric_profile.domain_quality.enabled = True

    before = _domain_idea_ids(domain_name)
    click.echo(f"Running baseline cohort for {profile} ({domain_name})...")
    baseline_result = run_pipeline(profile=baseline_profile, stages=active_stages)
    after_baseline = _domain_idea_ids(domain_name)
    baseline_ids = sorted(after_baseline - before)

    click.echo(f"Running rubric cohort for {profile} ({domain_name})...")
    rubric_result = run_pipeline(profile=rubric_profile, stages=active_stages)
    after_rubric = _domain_idea_ids(domain_name)
    rubric_ids = sorted(after_rubric - after_baseline)

    completed_at = datetime.now(timezone.utc).isoformat()
    store = Store()
    try:
        eval_run_id = store.insert_domain_quality_eval_run(
            profile_name=profile,
            domain=domain_name,
            rubric_version=rubric_profile.domain_quality.rubric_version,
            baseline_pipeline_run_id=baseline_result.run_id,
            rubric_pipeline_run_id=rubric_result.run_id,
            baseline_ideas=len(baseline_ids),
            rubric_ideas=len(rubric_ids),
            started_at=started_at,
            completed_at=completed_at,
            notes=notes,
        )
        baseline_items = _persist_domain_quality_eval_items(
            store,
            eval_run_id=eval_run_id,
            cohort="baseline",
            idea_ids=baseline_ids,
        )
        rubric_items = _persist_domain_quality_eval_items(
            store,
            eval_run_id=eval_run_id,
            cohort="rubric",
            idea_ids=rubric_ids,
        )
    finally:
        store.close()

    click.echo()
    click.echo(f"Domain quality eval: {eval_run_id}")
    click.echo(f"Profile: {profile} | Domain: {domain_name}")
    click.echo()
    click.echo(f"{'Metric':<34s} {'baseline':>10s} {'rubric':>10s}")
    click.echo("-" * 58)
    click.echo(f"{'Draft ideas':<34s} {baseline_result.draft_ideas_generated:>10d} {rubric_result.draft_ideas_generated:>10d}")
    click.echo(f"{'Ideas stored':<34s} {len(baseline_ids):>10d} {len(rubric_ids):>10d}")
    click.echo(f"{'Domain quality rejects':<34s} {0:>10d} {rubric_result.ideas_rejected_by_domain_quality:>10d}")
    click.echo(f"{'Avg domain quality':<34s} {'n/a':>10s} {rubric_result.avg_domain_quality_score:>10.1f}")
    click.echo(f"{'Ideas evaluated':<34s} {baseline_result.ideas_evaluated:>10d} {rubric_result.ideas_evaluated:>10d}")
    click.echo(f"{'Avg eval score':<34s} {baseline_result.avg_idea_score:>10.1f} {rubric_result.avg_idea_score:>10.1f}")
    click.echo(f"{'Stored eval items':<34s} {len(baseline_items):>10d} {len(rubric_items):>10d}")
    click.echo()
    click.echo("Review both cohorts, then compare approval rate and design brief readiness.")


def _domain_idea_ids(domain: str) -> set[str]:
    from max.store.db import Store

    store = Store()
    try:
        return {unit.id for unit in store.get_buildable_units(limit=10000, domain=domain)}
    finally:
        store.close()


def _persist_domain_quality_eval_items(
    store,
    *,
    eval_run_id: str,
    cohort: str,
    idea_ids: list[str],
) -> list[str]:
    item_ids: list[str] = []
    for idea_id in idea_ids:
        evaluation = store.get_evaluation(idea_id)
        feedback = store.get_latest_feedback(idea_id)
        quality_scores = store.get_domain_quality_scores(idea_id)
        latest_quality = quality_scores[0] if quality_scores else None
        item_ids.append(
            store.insert_domain_quality_eval_item(
                eval_run_id=eval_run_id,
                buildable_unit_id=idea_id,
                cohort=cohort,
                domain_quality_score=latest_quality["overall_score"] if latest_quality else None,
                passed_gate=latest_quality["passed_gate"] if latest_quality else None,
                evaluation_score=evaluation.overall_score if evaluation else None,
                review_outcome=feedback["outcome"] if feedback else None,
                approval_score=feedback["approval_score"] if feedback else None,
            )
        )
    return item_ids


@main.command(name="prior-art")
@click.option("--domain", "-d", type=str, default=None, help="Filter by domain")
@click.option("--limit", type=int, default=80, help="Max ideas to check")
@click.option("--re-scan", is_flag=True, help="Re-check ideas that already have results")
@click.option("--auto-reject", is_flag=True, help="Auto-reject ideas with strong matches")
@click.option("--dry-run", is_flag=True, help="Show queries without making API calls")
@click.option("--include-archived", is_flag=True, help="Include archived out-of-focus ideas")
def prior_art(domain: str | None, limit: int, re_scan: bool, auto_reject: bool, dry_run: bool, include_archived: bool) -> None:
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

        # Filter to evaluated/approved (not rejected/duplicate/archived)
        skip_statuses = {"rejected", "duplicate"}
        if not include_archived:
            skip_statuses.add("archived")
        units = [u for u in units if u.status not in skip_statuses]

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
@click.option(
    "--auto-approve-score",
    type=float,
    default=None,
    help="Automatically approve ideas at or above this score",
)
@click.option(
    "--auto-reject-score",
    type=float,
    default=None,
    help="Automatically reject ideas at or below this score",
)
@click.option("--threshold", type=float, default=0.85, help="Similarity threshold for clustering (default: 0.85)")
@click.option("--include-archived", is_flag=True, help="Include archived out-of-focus ideas")
def review(
    domain: str | None,
    min_score: float,
    limit: int,
    auto_approve_score: float | None,
    auto_reject_score: float | None,
    threshold: float,
    include_archived: bool,
) -> None:
    """Interactively review ideas in clusters.

    Similar ideas are grouped together for batch review. For each cluster:
    [a] approve best idea, reject rest  [A] approve all in cluster
    [r] reject entire cluster  [p] pick individually  [s] skip  [q] quit
    """
    from max.analysis.dedup import cluster_ideas
    from max.evaluation.weights import adapt_weights as do_adapt, get_weights
    from max.store.db import Store

    if limit < 1:
        click.echo("Error: --limit must be at least 1.")
        return
    if (
        auto_approve_score is not None
        and auto_reject_score is not None
        and auto_reject_score >= auto_approve_score
    ):
        click.echo("Error: --auto-reject-score must be lower than --auto-approve-score.")
        return

    store = Store()
    try:
        queue = _get_review_queue(
            store,
            domain=domain,
            min_score=min_score,
            limit=limit,
            include_archived=include_archived,
        )
        if queue is None:
            click.echo("No ideas found.")
            return

        auto_approved = 0
        auto_rejected = 0
        manual_queue = []
        for unit, ev in queue:
            score = ev.overall_score if ev else 0.0
            if auto_approve_score is not None and score >= auto_approve_score:
                reason = f"auto-review: score {score:.1f} >= {auto_approve_score:.1f}"
                store.insert_feedback(unit.id, "approved", reason)
                store.update_buildable_unit_status(unit.id, "approved")
                auto_approved += 1
            elif auto_reject_score is not None and score <= auto_reject_score:
                reason = f"auto-review: score {score:.1f} <= {auto_reject_score:.1f}"
                store.insert_feedback(unit.id, "rejected", reason)
                store.update_buildable_unit_status(unit.id, "rejected")
                auto_rejected += 1
            else:
                manual_queue.append((unit, ev))

        queue = manual_queue

        if not queue:
            if auto_approved or auto_rejected:
                click.echo(
                    "Review summary: "
                    f"reviewed=0, skipped=0, auto-approved={auto_approved}, auto-rejected={auto_rejected}"
                )
            else:
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
                        score = click.prompt("  Score (1-10, 10=highest conviction)", type=int)
                        while not 1 <= score <= 10:
                            score = click.prompt("  Must be 1-10", type=int)
                        reason = click.prompt("  Reason (optional)", default="", show_default=False)
                        store.insert_feedback(rep.id, "approved", reason, approval_score=score)
                        store.update_buildable_unit_status(rep.id, "approved")
                        approved += 1
                        for unit, ev in cluster.duplicates:
                            store.insert_feedback(unit.id, "rejected", f"cluster-review: kept {rep.id}")
                            store.update_buildable_unit_status(unit.id, "rejected")
                            rejected += 1
                        click.echo(f"  -> approved best ({score}/10), rejected {len(cluster.duplicates)} others")
                        break
                    elif choice == "A":
                        # Approve all in cluster
                        score = click.prompt("  Score (1-10, 10=highest conviction)", type=int)
                        while not 1 <= score <= 10:
                            score = click.prompt("  Must be 1-10", type=int)
                        reason = click.prompt("  Reason (optional)", default="", show_default=False)
                        for unit, ev in cluster.members:
                            store.insert_feedback(unit.id, "approved", reason, approval_score=score)
                            store.update_buildable_unit_status(unit.id, "approved")
                            approved += 1
                        click.echo(f"  -> approved all {cluster.size} ideas ({score}/10)")
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
        reviewed = approved + rejected
        click.echo(
            "Review summary: "
            f"reviewed={reviewed}, skipped={skipped}, "
            f"auto-approved={auto_approved}, auto-rejected={auto_rejected}"
        )
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


def _get_review_queue(
    store,
    *,
    domain: str | None,
    min_score: float,
    limit: int,
    include_archived: bool,
) -> list[tuple[BuildableUnit, UtilityEvaluation | None]] | None:
    """Return pending review items, preferring Store.get_review_queue when usable."""
    get_review_queue = getattr(store, "get_review_queue", None)
    if callable(get_review_queue) and not include_archived:
        rows = get_review_queue(domain=domain, min_score=min_score, limit=limit)
        if isinstance(rows, list):
            return [(row["unit"], row.get("evaluation")) for row in rows]

    units = store.get_buildable_units(limit=limit * 3, domain=domain)
    if not units:
        return None

    queue = []
    for unit in units:
        if not include_archived and unit.status == "archived":
            continue
        if unit.status != "evaluated" and not include_archived:
            continue
        ev = store.get_evaluation(unit.id)
        if not ev:
            continue
        if ev.overall_score < min_score:
            continue
        if store.has_feedback(unit.id):
            continue
        queue.append((unit, ev))

    queue.sort(key=lambda x: x[1].overall_score if x[1] else 0.0, reverse=True)
    return queue[:limit]


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
            score = click.prompt("  Score (1-10, 10=highest conviction)", type=int)
            while not 1 <= score <= 10:
                score = click.prompt("  Must be 1-10", type=int)
            reason = click.prompt("  Reason (optional)", default="", show_default=False)
            store.insert_feedback(unit.id, "approved", reason, approval_score=score)
            store.update_buildable_unit_status(unit.id, "approved")
            click.echo(f"  -> approved ({score}/10)")
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
        _render_feedback_history(records)
    finally:
        store.close()


def _render_diagnostics_report(
    profile,
    *,
    domain: str | None,
    limit: int,
    feedback_log: list[dict],
    coverage_report,
    calibration_report,
) -> None:
    click.echo("Diagnostics")
    click.echo(f"Profile: {profile.name}  Domain: {profile.domain.name}")
    if domain:
        click.echo(f"Calibration domain: {domain}")
    click.echo(f"Section limit: {limit}")

    click.echo()
    _render_feedback_history(feedback_log)

    click.echo()
    _render_profile_coverage_gaps(coverage_report)

    click.echo()
    _render_evaluation_calibration(calibration_report)


def _render_feedback_history(records: list[dict]) -> None:
    click.echo("Feedback history")
    if not records:
        click.echo("No feedback recorded yet.")
        return

    click.echo(f"{'Outcome':<10s} {'Score':>5s} {'Appr':>4s} {'Domain':<16s} {'Title':<48s} {'Reason'}")
    click.echo("-" * 115)
    for r in records:
        score = f"{r['score']:.1f}" if r["score"] else "  -"
        approval_score = r.get("approval_score")
        appr = f"{approval_score:>2d}" if approval_score is not None else "  -"
        domain = f"[{r['domain']}]" if r["domain"] else ""
        reason = r["reason"][:28] if r["reason"] else ""
        click.echo(f"{r['outcome']:<10s} {score:>5s} {appr:>4s} {domain:<16s} {r['title'][:48]:<48s} {reason}")

    approved = sum(1 for r in records if r["outcome"] == "approved")
    rejected = sum(1 for r in records if r["outcome"] in ("rejected", "abandoned"))
    click.echo(f"\n{len(records)} records: {approved} approved, {rejected} rejected")


def _render_profile_coverage_gaps(report) -> None:
    click.echo("Profile coverage gaps")
    click.echo(f"Profile: {report.profile_name}  Domain: {report.domain}")
    click.echo(f"Threshold: {report.low_coverage_threshold}")
    enabled_adapters = ", ".join(report.enabled_adapters) if report.enabled_adapters else "(none)"
    click.echo(f"Enabled adapters: {enabled_adapters}")
    click.echo()

    if not report.terms:
        click.echo("No profile coverage gaps found.")
        return

    click.echo(f"{'Term':<24s} {'Type':<16s} {'Count':>5s} {'Adapter counts':<32s} {'Suggested'}")
    click.echo("-" * 100)
    for term in report.terms:
        adapter_counts = ", ".join(f"{adapter}={count}" for adapter, count in term.adapter_counts.items())
        suggested = ", ".join(term.suggested_source_adapters) if term.suggested_source_adapters else "-"
        click.echo(
            f"{term.term[:24]:<24s} "
            f"{term.term_type[:16]:<16s} "
            f"{term.total_count:>5d} "
            f"{adapter_counts[:32]:<32s} "
            f"{suggested}"
        )


def _render_profile_coverage_matrix(matrix, *, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(asdict(matrix), indent=2) + "\n"

    if fmt == "csv":
        adapter_headers = [f"count_{adapter}" for adapter in matrix.enabled_adapters]
        headers = [
            "profile",
            "domain",
            "term",
            "term_type",
            "total_count",
            "status",
            "recommended_adapters",
            *adapter_headers,
        ]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        for row in matrix.rows:
            record = {
                "profile": matrix.profile_name,
                "domain": matrix.domain,
                "term": row.term,
                "term_type": row.term_type,
                "total_count": row.total_count,
                "status": row.status,
                "recommended_adapters": ",".join(row.recommended_adapters),
            }
            for adapter in matrix.enabled_adapters:
                record[f"count_{adapter}"] = row.adapter_counts.get(adapter, 0)
            writer.writerow(record)
        return buffer.getvalue()

    if fmt != "table":
        raise click.ClickException(f"Unsupported format: {fmt}")

    lines = [
        "Profile coverage matrix",
        f"Profile: {matrix.profile_name}  Domain: {matrix.domain}",
        f"Threshold: {matrix.low_coverage_threshold}",
        "Enabled adapters: "
        + (", ".join(matrix.enabled_adapters) if matrix.enabled_adapters else "(none)"),
        "",
    ]
    if not matrix.rows:
        lines.append("No profile coverage terms found.")
        return "\n".join(lines) + "\n"

    adapter_label = "Adapter counts"
    lines.append(
        f"{'Term':<24s} {'Type':<16s} {'Count':>5s} {'Status':<12s} "
        f"{adapter_label:<32s} Recommended"
    )
    lines.append("-" * 112)
    for row in matrix.rows:
        adapter_counts = ", ".join(
            f"{adapter}={row.adapter_counts.get(adapter, 0)}"
            for adapter in matrix.enabled_adapters
        )
        recommended = ", ".join(row.recommended_adapters) if row.recommended_adapters else "-"
        lines.append(
            f"{row.term[:24]:<24s} "
            f"{row.term_type[:16]:<16s} "
            f"{row.total_count:>5d} "
            f"{row.status:<12s} "
            f"{adapter_counts[:32]:<32s} "
            f"{recommended}"
        )
    return "\n".join(lines) + "\n"


def _render_evaluation_calibration(report) -> None:
    click.echo("Evaluation calibration")
    click.echo(
        f"Domain filter: {report.domain or '(none)'}  Min samples: {report.min_samples}  "
        f"Limit: {report.limit}"
    )
    if not report.groups:
        click.echo("No reviewed evaluations found.")
        return

    click.echo(
        f"{'Domain':<18s} {'Rec':<10s} {'Samples':>7s} {'Appr%':>7s} "
        f"{'Rej%':>7s} {'Avg':>6s} {'High Rej%':>10s} {'Low Appr%':>10s}"
    )
    click.echo("-" * 88)
    for group in report.groups:
        click.echo(
            f"{(group.domain or '-'):18.18s} "
            f"{(group.recommendation or '-'):10.10s} "
            f"{group.sample_count:7d} "
            f"{group.approval_rate * 100:6.1f}% "
            f"{group.rejection_rate * 100:6.1f}% "
            f"{group.average_overall_score:6.1f} "
            f"{group.high_score_rejection_rate * 100:9.1f}% "
            f"{group.low_score_approval_rate * 100:9.1f}%"
        )
    click.echo(
        f"\nGroups: {report.total_groups}; samples: {report.total_samples}; "
        f"high score >= {report.high_score_threshold:.1f}; "
        f"low score < {report.low_score_threshold:.1f}"
    )


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
@click.option("--entity", type=click.Choice(["signal", "insight", "idea"]), default=None, help="Entity type to restore")
@click.option("--id", "ids", multiple=True, help="Restore a specific entity ID; repeat for multiple IDs")
@click.option("--before", type=str, default=None, help="Only restore records archived before this ISO timestamp or YYYY-MM-DD date")
@click.option("--dry-run", is_flag=True, help="Show what would be restored without modifying data")
@click.option("--limit", type=int, default=100, show_default=True, help="Maximum records to restore")
def restore(
    entity: str | None,
    ids: tuple[str, ...],
    before: str | None,
    dry_run: bool,
    limit: int,
) -> None:
    """Restore archived signals, insights, and ideas."""
    from max.store.db import Store

    if limit < 1:
        raise click.ClickException("--limit must be at least 1")

    before_value = _normalize_restore_before(before)
    entity_types = [entity] if entity else ["signal", "insight", "idea"]
    requested_ids = list(ids)

    store = Store()
    try:
        candidates: dict[str, list[str]] = {}
        remaining = limit
        for entity_type in entity_types:
            if remaining <= 0:
                candidates[entity_type] = []
                continue
            candidates[entity_type] = _restore_candidates(
                store,
                entity_type,
                before=before_value,
                ids=requested_ids or None,
                limit=remaining,
            )
            remaining -= len(candidates[entity_type])

        total = sum(len(entity_ids) for entity_ids in candidates.values())
        if total > limit:
            raise click.ClickException(f"Refusing to restore {total} records; limit is {limit}")

        action = "Would restore" if dry_run else "Restored"
        if total == 0:
            click.echo("No archived records matched.")
            return

        if dry_run:
            click.echo("DRY RUN: No changes applied.")

        restored: dict[str, int] = dict.fromkeys(entity_types, 0)
        if not dry_run:
            for entity_type, entity_ids in candidates.items():
                restore_one = _restore_one(store, entity_type)
                for entity_id in entity_ids:
                    if restore_one(entity_id):
                        restored[entity_type] += 1
        else:
            restored = {entity_type: len(entity_ids) for entity_type, entity_ids in candidates.items()}

        click.echo(f"{action} {sum(restored.values())} archived record(s):")
        for entity_type in entity_types:
            click.echo(f"  {entity_type}s: {restored.get(entity_type, 0):6d}")
    finally:
        store.close()


def _normalize_restore_before(before: str | None) -> str | None:
    if not before:
        return None
    from datetime import datetime, timezone

    value = before.strip()
    if not value:
        return None
    if len(value) == 10:
        try:
            return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        raise click.ClickException("--before must be an ISO timestamp or YYYY-MM-DD date")


def _restore_candidates(
    store,
    entity_type: str,
    *,
    before: str | None,
    ids: list[str] | None,
    limit: int,
) -> list[str]:
    if entity_type == "signal":
        return store.get_archived_signal_ids(before=before, ids=ids, limit=limit)
    if entity_type == "insight":
        return store.get_archived_insight_ids(before=before, ids=ids, limit=limit)
    return store.get_archived_idea_ids(before=before, ids=ids, limit=limit)


def _restore_one(store, entity_type: str):
    if entity_type == "signal":
        return store.restore_signal
    if entity_type == "insight":
        return store.restore_insight
    return store.restore_archived_idea


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
