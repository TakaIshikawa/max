"""Tests for gap detection (validated unmet needs)."""

from __future__ import annotations

from max.analysis.gap_detector import Gap, detect_gaps, format_gaps_for_ideation
from max.store.db import Store
from max.types.signal import Signal, SignalSourceType


def _make_signal(
    adapter: str,
    title: str,
    *,
    signal_role: str = "problem",
    credibility: float = 0.7,
    content: str = "",
) -> Signal:
    return Signal(
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter,
        title=title,
        content=content or title,
        url=f"https://example.com/{hash(title) % 100000}",
        credibility=credibility,
        metadata={"signal_role": signal_role},
    )


def _seed_signals(store: Store, signals: list[Signal]) -> None:
    for sig in signals:
        store.insert_signal(sig)


# ── Gap dataclass properties ─────────────────────────────────────


def test_gap_problem_strength_empty() -> None:
    gap = Gap(topic="test", problem_signals=[], solution_signals=[])
    assert gap.problem_strength == 0.0


def test_gap_problem_strength_scales_with_diversity() -> None:
    """More diverse sources → higher problem strength."""
    signals_one = [_make_signal("hackernews", "Bug report", credibility=0.8)]
    signals_two = [
        _make_signal("hackernews", "Bug report", credibility=0.8),
        _make_signal("reddit", "Same bug", credibility=0.8),
    ]

    gap_one = Gap(topic="test", problem_signals=signals_one)
    gap_two = Gap(topic="test", problem_signals=signals_two)

    assert gap_two.problem_strength > gap_one.problem_strength


def test_gap_solution_coverage_empty() -> None:
    gap = Gap(topic="test", problem_signals=[], solution_signals=[])
    assert gap.solution_coverage == 0.0


def test_gap_solution_coverage_increases_with_solutions() -> None:
    no_sol = Gap(topic="test", problem_signals=[], solution_signals=[])
    with_sol = Gap(
        topic="test",
        problem_signals=[],
        solution_signals=[
            _make_signal("npm_registry", "Package A", signal_role="solution", credibility=0.8),
            _make_signal("pypi_registry", "Package B", signal_role="solution", credibility=0.8),
        ],
    )
    assert with_sol.solution_coverage > no_sol.solution_coverage


def test_gap_score_computation() -> None:
    """gap_score = problem_strength * (1 - solution_coverage)."""
    gap = Gap(
        topic="test",
        problem_signals=[
            _make_signal("hackernews", "Bug 1", credibility=0.9),
            _make_signal("reddit", "Bug 2", credibility=0.9),
            _make_signal("github_issues", "Bug 3", credibility=0.9),
        ],
        solution_signals=[],  # No solutions → coverage = 0
    )
    gap.gap_score = gap.problem_strength * (1.0 - gap.solution_coverage)
    assert gap.gap_score > 0.0
    # With strong problem and no solutions, gap_score should be high
    assert gap.gap_score == gap.problem_strength


def test_gap_score_decreases_with_solutions() -> None:
    problems = [
        _make_signal("hackernews", "Testing is hard", credibility=0.8),
        _make_signal("reddit", "Testing tools are lacking", credibility=0.8),
    ]
    gap_no_sol = Gap(topic="test", problem_signals=problems, solution_signals=[])
    gap_no_sol.gap_score = gap_no_sol.problem_strength * (1.0 - gap_no_sol.solution_coverage)

    gap_with_sol = Gap(
        topic="test",
        problem_signals=problems,
        solution_signals=[
            _make_signal("npm_registry", "Test tool", signal_role="solution", credibility=0.9),
            _make_signal("pypi_registry", "Test lib", signal_role="solution", credibility=0.9),
            _make_signal("github", "Test framework", signal_role="solution", credibility=0.9),
        ],
    )
    gap_with_sol.gap_score = (
        gap_with_sol.problem_strength * (1.0 - gap_with_sol.solution_coverage)
    )

    assert gap_with_sol.gap_score < gap_no_sol.gap_score


# ── detect_gaps with store ───────────────────────────────────────


def test_detect_gaps_no_signals(store: Store) -> None:
    gaps = detect_gaps(store)
    assert gaps == []


def test_detect_gaps_no_problems(store: Store) -> None:
    """Only solution signals → no gaps."""
    signals = [
        _make_signal("npm_registry", "Package A", signal_role="solution"),
        _make_signal("pypi_registry", "Package B", signal_role="solution"),
    ]
    _seed_signals(store, signals)
    gaps = detect_gaps(store)
    assert gaps == []


def test_detect_gaps_problems_only(store: Store) -> None:
    """Problem signals with no solutions should produce gaps."""
    signals = [
        _make_signal("hackernews", "MCP testing is broken", credibility=0.8),
        _make_signal("reddit", "MCP testing framework needed", credibility=0.8),
        _make_signal("github_issues", "Need MCP test tools", credibility=0.8),
    ]
    _seed_signals(store, signals)
    gaps = detect_gaps(store, min_gap_score=0.0)
    assert len(gaps) > 0


def test_detect_gaps_max_gaps_limit(store: Store) -> None:
    """Should respect max_gaps parameter."""
    signals = [
        _make_signal("hackernews", f"Unique problem number {i}", credibility=0.9)
        for i in range(20)
    ]
    _seed_signals(store, signals)
    gaps = detect_gaps(store, min_gap_score=0.0, max_gaps=3)
    assert len(gaps) <= 3


# ── format_gaps_for_ideation ─────────────────────────────────────


def test_format_gaps_empty() -> None:
    assert format_gaps_for_ideation([]) is None


def test_format_gaps_output_structure() -> None:
    gaps = [
        Gap(
            topic="MCP testing gap",
            problem_signals=[
                _make_signal("hackernews", "MCP testing is hard"),
                _make_signal("reddit", "Need MCP test tools"),
            ],
            solution_signals=[],
            gap_score=0.75,
            source_diversity=0.67,
        ),
    ]
    result = format_gaps_for_ideation(gaps)
    assert result is not None
    assert "VALIDATED UNMET NEEDS" in result
    assert "MCP testing gap" in result
    assert "Gap score: 0.75" in result
    assert "hackernews" in result
    assert "Prioritize ideas" in result


def test_format_gaps_max_gaps_limit() -> None:
    gaps = [
        Gap(
            topic=f"Gap {i}",
            problem_signals=[_make_signal("hackernews", f"Problem {i}")],
            solution_signals=[],
            gap_score=0.5,
        )
        for i in range(10)
    ]
    result = format_gaps_for_ideation(gaps, max_gaps=3)
    assert result is not None
    assert "Gap 0" in result
    assert "Gap 2" in result
    # Gap 3 should not be included
    assert "4." not in result
