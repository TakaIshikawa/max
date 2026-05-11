"""Tests for dependency health analysis."""

from __future__ import annotations

import json

from max.analysis import (
    HealthRating,
    assess_dependency_health,
    build_dependency_health_report,
    render_dependency_health_json,
    render_dependency_health_markdown,
)


def _signal(name: str, **overrides: object) -> dict:
    signal = {
        "dependency_name": name,
        "ecosystem": "npm",
        "last_release_days": 30,
        "open_issues": 24,
        "maintainer_count": 5,
        "known_vulnerabilities": 0,
        "community_score": 0.82,
        "title": f"{name} package health",
    }
    signal.update(overrides)
    return signal


def test_health_rating_classification_thresholds() -> None:
    healthy = assess_dependency_health("React", [_signal("React")])
    caution = assess_dependency_health(
        "FastAPI",
        [_signal("FastAPI", ecosystem="pypi", last_release_days=220, community_score=0.35)],
    )
    at_risk = assess_dependency_health(
        "LegacyLib",
        [
            _signal(
                "LegacyLib",
                last_release_days=500,
                open_issues=450,
                maintainer_count=1,
                community_score=0.25,
            )
        ],
    )
    critical = assess_dependency_health(
        "OldAuth",
        [
            _signal(
                "OldAuth",
                last_release_days=900,
                maintainer_count=0,
                known_vulnerabilities=5,
                title="OldAuth has a critical vulnerability and appears abandoned",
            )
        ],
    )

    assert healthy.health_rating == HealthRating.HEALTHY
    assert caution.health_rating == HealthRating.CAUTION
    assert at_risk.health_rating == HealthRating.AT_RISK
    assert critical.health_rating == HealthRating.CRITICAL


def test_build_report_with_mixed_health_dependencies() -> None:
    unit = {
        "title": "Workflow Console",
        "tech_stack": ["React", "FastAPI", "OldAuth"],
    }
    signals = [
        _signal("React", ecosystem="npm", community_score=0.9),
        _signal("FastAPI", ecosystem="pypi", last_release_days=260, community_score=0.5),
        _signal(
            "OldAuth",
            ecosystem="npm",
            last_release_days=880,
            open_issues=1200,
            maintainer_count=0,
            known_vulnerabilities=6,
            title="OldAuth package is unmaintained",
        ),
    ]

    report = build_dependency_health_report(unit, signals)
    by_name = {item.name: item for item in report.dependencies}

    assert [item.name for item in report.dependencies] == ["FastAPI", "OldAuth", "React"]
    assert by_name["React"].health_rating == HealthRating.HEALTHY
    assert by_name["FastAPI"].health_rating == HealthRating.CAUTION
    assert by_name["OldAuth"].health_rating == HealthRating.CRITICAL
    assert report.overall_risk == "critical"
    assert report.at_risk_count == 1
    assert report.healthy_count == 1


def test_handles_missing_signal_data_gracefully() -> None:
    report = build_dependency_health_report(
        {
            "suggested_stack": {
                "backend": "FastAPI",
                "database": "Postgres",
            }
        },
        [],
    )

    assert len(report.dependencies) == 2
    assert report.overall_risk == "moderate"
    assert all(item.health_rating == HealthRating.CAUTION for item in report.dependencies)
    assert all(item.last_release_days is None for item in report.dependencies)
    assert all(item.signals_analyzed == 0 for item in report.dependencies)


def test_signal_metadata_and_numeric_community_indicators_are_supported() -> None:
    health = assess_dependency_health(
        "serde",
        [
            {
                "metadata": {
                    "package_name": "serde",
                    "ecosystem": "crates",
                    "last_release_days": "18",
                    "open_issues": "42",
                    "maintainers": "4",
                    "stars": "9000",
                },
                "content": "serde release cadence remains stable",
            }
        ],
    )

    assert health.ecosystem == "crates"
    assert health.last_release_days == 18
    assert health.open_issues == 42
    assert health.maintainer_count == 4
    assert health.community_score > 0
    assert health.health_rating == HealthRating.HEALTHY


def test_markdown_and_json_renderers_produce_stable_output() -> None:
    report = build_dependency_health_report(
        {"tech_stack": ["React", {"name": "FastAPI"}]},
        [
            _signal("React", ecosystem="npm"),
            _signal("FastAPI", ecosystem="pypi", last_release_days=220, community_score=0.4),
        ],
    )

    markdown = render_dependency_health_markdown(report)
    rendered_json = render_dependency_health_json(report)
    payload = json.loads(rendered_json)

    assert markdown.startswith("# Dependency Health Report")
    assert "| Dependency | Ecosystem | Rating |" in markdown
    assert "[green] Healthy" in markdown
    assert payload["overall_risk"] == "moderate"
    assert payload["dependencies"][0]["health_rating"] == "caution"
    assert json.loads(json.dumps(payload)) == payload


def test_empty_report_rendering_is_stable() -> None:
    report = build_dependency_health_report({}, [])
    markdown = render_dependency_health_markdown(report)
    payload = json.loads(render_dependency_health_json(report))

    assert report.overall_risk == "unknown"
    assert "No dependencies identified" in markdown
    assert payload["dependencies"] == []
