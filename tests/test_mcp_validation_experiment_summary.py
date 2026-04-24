"""Tests for MCP validation experiment summary exposure."""

from __future__ import annotations

import json

import pytest

from max.server.mcp_tools import (
    max_validation_experiment_summary,
    set_store_factory,
    validation_experiment_summary_detail,
    validation_experiment_summary_for_domain_detail,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


@pytest.fixture
def mcp_db(tmp_path):
    """Create temp DB and configure mcp_tools to use it."""
    db_path = str(tmp_path / "test_mcp_validation_experiment_summary.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


def _unit(unit_id: str, domain: str) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=f"{domain} validation idea",
        one_liner="Summarize validation experiments",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Experiment tracking is hard to prioritize",
        solution="Aggregate experiment outcomes",
        value_proposition="Make validation work portfolio-readable",
        domain=domain,
    )


def _seed_validation_experiments(db_path: str) -> None:
    with Store(db_path=db_path, wal_mode=True) as store:
        store.insert_buildable_unit(_unit("bu-mcp-summary-devtools", "devtools"))
        store.insert_buildable_unit(_unit("bu-mcp-summary-aiops", "aiops"))
        store.create_validation_experiment(
            "bu-mcp-summary-devtools",
            hypothesis="Developers will use the prototype",
            method="prototype",
            success_metric="7 of 10 activate",
            status="completed",
            due_date="2000-01-01",
            completed_at="2000-01-02T00:00:00+00:00",
            result_summary=json.dumps(
                {
                    "outcome": "validated",
                    "result_score": 0.8,
                    "confidence_score": 0.7,
                }
            ),
            confidence_delta=0.3,
        )
        store.create_validation_experiment(
            "bu-mcp-summary-devtools",
            hypothesis="Buyers will approve budget",
            method="interview",
            success_metric="3 budget owners commit",
            status="blocked",
            due_date="2000-01-01",
            result_summary=json.dumps(
                {
                    "outcome": "blocked",
                    "follow_up_actions": ["recruit budget owners", "tighten ICP"],
                }
            ),
        )
        store.create_validation_experiment(
            "bu-mcp-summary-aiops",
            hypothesis="Operators can complete setup",
            method="survey",
            success_metric="80 percent report confidence",
            status="running",
            due_date="2999-01-01",
            result_summary=json.dumps(
                {
                    "outcome": "inconclusive",
                    "result_score": 0.4,
                    "follow_up_action": "recruit budget owners",
                }
            ),
            confidence_delta=0.1,
        )


def _counts(items: list[dict]) -> dict[str, int]:
    return {item["key"]: item["count"] for item in items}


def test_max_validation_experiment_summary_returns_portfolio_health(mcp_db) -> None:
    _seed_validation_experiments(mcp_db)

    report = max_validation_experiment_summary()

    assert report["total_count"] == 3
    assert report["completed_count"] == 1
    assert report["overdue_count"] == 1
    assert report["completion_rate"] == 0.333
    assert report["average_confidence_delta"] == 0.4
    assert report["average_result_score"] == 0.6
    assert _counts(report["by_status"]) == {"blocked": 1, "completed": 1, "running": 1}
    assert _counts(report["by_domain"]) == {"devtools": 2, "aiops": 1}
    assert _counts(report["by_experiment_type"]) == {
        "interview": 1,
        "prototype": 1,
        "survey": 1,
    }
    assert _counts(report["by_outcome"]) == {
        "blocked": 1,
        "inconclusive": 1,
        "validated": 1,
    }
    assert report["top_follow_up_actions"] == [
        {"action": "recruit budget owners", "count": 2},
        {"action": "tighten ICP", "count": 1},
    ]


def test_max_validation_experiment_summary_filters_match_rest_behavior(mcp_db) -> None:
    _seed_validation_experiments(mcp_db)

    domain_report = max_validation_experiment_summary(domain="devtools")
    idea_report = max_validation_experiment_summary(idea_id="bu-mcp-summary-aiops")
    status_report = max_validation_experiment_summary(status="blocked")
    overdue_report = max_validation_experiment_summary(overdue_only=True)

    assert domain_report["total_count"] == 2
    assert _counts(domain_report["by_domain"]) == {"devtools": 2}
    assert idea_report["total_count"] == 1
    assert _counts(idea_report["by_status"]) == {"running": 1}
    assert status_report["total_count"] == 1
    assert _counts(status_report["by_status"]) == {"blocked": 1}
    assert overdue_report["total_count"] == 1
    assert overdue_report["overdue_count"] == 1
    assert _counts(overdue_report["by_status"]) == {"blocked": 1}


def test_validation_experiment_summary_resources_return_valid_json(mcp_db) -> None:
    _seed_validation_experiments(mcp_db)

    default_report = json.loads(validation_experiment_summary_detail())
    domain_report = json.loads(validation_experiment_summary_for_domain_detail("aiops"))

    assert default_report["total_count"] == 3
    assert default_report["filters"] == {
        "domain": None,
        "idea_id": None,
        "status": None,
        "overdue_only": False,
    }
    assert domain_report["total_count"] == 1
    assert _counts(domain_report["by_domain"]) == {"aiops": 1}
