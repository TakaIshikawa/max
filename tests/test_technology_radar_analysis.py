"""Tests for technology radar analysis."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from max.analysis.technology_radar import (
    TechnologyRadarAnalyzer,
    render_radar_markdown,
)


def _signal(
    idx: int,
    *,
    title: str,
    content: str = "",
    tags: list[str] | None = None,
    age_days: int = 1,
) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "id": f"sig-radar-{idx:03d}",
        "title": title,
        "content": content,
        "tags": tags or [],
        "published_at": now - timedelta(days=age_days),
    }


def test_extract_technologies_from_text() -> None:
    analyzer = TechnologyRadarAnalyzer()

    technologies = analyzer._extract_technologies(
        "React teams are adopting TypeScript, FastAPI, Docker, and AWS."
    )

    assert ("React", "frameworks") in technologies
    assert ("TypeScript", "languages") in technologies
    assert ("FastAPI", "frameworks") in technologies
    assert ("Docker", "tools") in technologies
    assert ("AWS", "platforms") in technologies


def test_momentum_calculation_increasing_decreasing_and_stable() -> None:
    analyzer = TechnologyRadarAnalyzer(signal_window_days=30)
    now = datetime(2026, 4, 23, tzinfo=timezone.utc)

    increasing = [
        now - timedelta(days=2),
        now - timedelta(days=3),
        now - timedelta(days=20),
    ]
    decreasing = [
        now - timedelta(days=2),
        now - timedelta(days=20),
        now - timedelta(days=21),
    ]
    stable = [
        now - timedelta(days=2),
        now - timedelta(days=3),
        now - timedelta(days=20),
        now - timedelta(days=21),
    ]

    assert analyzer._calculate_momentum(increasing) > 0
    assert analyzer._calculate_momentum(decreasing) < 0
    assert analyzer._calculate_momentum(stable) == 0


def test_ring_classification_thresholds() -> None:
    analyzer = TechnologyRadarAnalyzer(
        adopt_threshold=0.7,
        trial_threshold=0.4,
        assess_threshold=0.1,
    )

    assert analyzer._classify_ring(7, 0.1, 10) == "adopt"
    assert analyzer._classify_ring(4, 0.0, 10) == "trial"
    assert analyzer._classify_ring(1, -0.2, 10) == "assess"
    assert analyzer._classify_ring(0, 0.0, 10) == "hold"


def test_analyze_with_mixed_signals() -> None:
    analyzer = TechnologyRadarAnalyzer(signal_window_days=90)
    signals = [
        _signal(1, title="React and TypeScript frontend stack", tags=["react"]),
        _signal(2, title="React app deployment on Vercel", tags=["vercel"]),
        _signal(3, title="FastAPI service with Python and Docker", tags=["python"]),
        _signal(4, title="Rust CLI using Docker packaging", tags=["rust"], age_days=40),
        _signal(5, title="React design system with TypeScript", age_days=45),
        _signal(6, title="Legacy Rails notes", tags=["rails"], age_days=120),
    ]

    radar = analyzer.analyze(signals)
    by_name = {entry.name: entry for entry in radar.entries}

    assert "Rails" not in by_name
    assert by_name["React"].quadrant == "frameworks"
    assert by_name["React"].signal_count == 3
    assert by_name["React"].ring == "trial"
    assert by_name["TypeScript"].quadrant == "languages"
    assert by_name["Docker"].quadrant == "tools"
    assert by_name["Vercel"].quadrant == "platforms"
    assert by_name["React"].momentum > 0


def test_empty_signals_list() -> None:
    radar = TechnologyRadarAnalyzer().analyze([])

    assert radar.entries == []
    assert radar.signal_window_days == 90


def test_custom_thresholds() -> None:
    analyzer = TechnologyRadarAnalyzer(
        signal_window_days=90,
        adopt_threshold=0.5,
        trial_threshold=0.25,
        assess_threshold=0.1,
    )
    signals = [
        _signal(1, title="React signal"),
        _signal(2, title="React signal"),
        _signal(3, title="Python signal"),
        _signal(4, title="Docker signal"),
    ]

    radar = analyzer.analyze(signals)
    by_name = {entry.name: entry for entry in radar.entries}

    assert by_name["React"].ring == "adopt"
    assert by_name["Python"].ring == "trial"


def test_render_radar_markdown() -> None:
    radar = TechnologyRadarAnalyzer().analyze(
        [_signal(1, title="React teams use TypeScript on AWS")]
    )

    markdown = render_radar_markdown(radar)

    assert markdown.startswith("# Technology Radar")
    assert (
        "| Quadrant | Ring | Technology | Signals | Momentum | First seen | Last seen |"
        in markdown
    )
    assert "React" in markdown
    assert "TypeScript" in markdown
    assert "AWS" in markdown
