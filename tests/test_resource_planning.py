"""Tests for resource planning export module."""

import pytest

from max.exports.resource_planning import (
    build_resource_planning_report,
    render_resource_planning_markdown,
    _calculate_team_capacity,
    _calculate_allocations,
    _calculate_utilization_rates,
    _identify_skill_gaps,
    _identify_over_under_allocation,
    _generate_capacity_forecasts,
)


@pytest.fixture
def team_members():
    return [
        {"name": "Alice", "skills": ["python", "ml"], "availability_hours": 40},
        {"name": "Bob", "skills": ["python", "frontend"], "availability_hours": 40},
        {"name": "Carol", "skills": ["devops", "python"], "availability_hours": 30},
    ]


@pytest.fixture
def tasks():
    return [
        {
            "name": "Build ML pipeline",
            "required_skills": ["python", "ml"],
            "estimate_hours": 20,
            "assignee": "Alice",
            "sprint": "Sprint 1",
        },
        {
            "name": "Create dashboard",
            "required_skills": ["frontend"],
            "estimate_hours": 30,
            "assignee": "Bob",
            "sprint": "Sprint 1",
        },
        {
            "name": "Setup CI/CD",
            "required_skills": ["devops"],
            "estimate_hours": 15,
            "assignee": "Carol",
            "sprint": "Sprint 1",
        },
        {
            "name": "Data processing",
            "required_skills": ["python", "ml"],
            "estimate_hours": 25,
            "assignee": "Alice",
            "sprint": "Sprint 2",
        },
        {
            "name": "Mobile app",
            "required_skills": ["mobile"],
            "estimate_hours": 40,
            "assignee": None,
            "sprint": "Sprint 2",
        },
    ]


@pytest.fixture
def sprints():
    return [
        {"name": "Sprint 1", "capacity_hours": 110},
        {"name": "Sprint 2", "capacity_hours": 110},
    ]


class TestCalculateTeamCapacity:
    def test_total_members(self, team_members):
        result = _calculate_team_capacity(team_members)
        assert result["total_members"] == 3

    def test_total_available_hours(self, team_members):
        result = _calculate_team_capacity(team_members)
        assert result["total_available_hours"] == 110

    def test_all_skills(self, team_members):
        result = _calculate_team_capacity(team_members)
        assert set(result["all_skills"]) == {"python", "ml", "frontend", "devops"}

    def test_empty_team(self):
        result = _calculate_team_capacity([])
        assert result["total_members"] == 0
        assert result["total_available_hours"] == 0
        assert result["all_skills"] == []


class TestCalculateAllocations:
    def test_basic_allocation(self, team_members, tasks):
        result = _calculate_allocations(team_members, tasks)
        assert result["Alice"] == 45  # 20 + 25
        assert result["Bob"] == 30
        assert result["Carol"] == 15

    def test_unassigned_tasks_ignored(self, team_members, tasks):
        result = _calculate_allocations(team_members, tasks)
        # Mobile app (40h) is unassigned, shouldn't appear
        total_allocated = sum(result.values())
        assert total_allocated == 90  # 45 + 30 + 15

    def test_empty_tasks(self, team_members):
        result = _calculate_allocations(team_members, [])
        assert all(v == 0 for v in result.values())


class TestCalculateUtilizationRates:
    def test_utilization_calculation(self, team_members, tasks):
        capacity = _calculate_team_capacity(team_members)
        allocations = _calculate_allocations(team_members, tasks)
        rates = _calculate_utilization_rates(capacity, allocations)

        assert len(rates) == 3
        # Each member has ~36.67h available (110/3)
        alice = next(r for r in rates if r["member"] == "Alice")
        assert alice["allocated_hours"] == 45
        assert alice["utilization_pct"] > 100  # Over-allocated

    def test_empty_team(self):
        capacity = {"total_available_hours": 0, "total_members": 0, "all_skills": []}
        rates = _calculate_utilization_rates(capacity, {})
        assert rates == []


class TestIdentifySkillGaps:
    def test_critical_gap(self, team_members, tasks):
        gaps = _identify_skill_gaps(team_members, tasks)
        # "mobile" is required but no one has it
        mobile_gap = next((g for g in gaps if g["skill"] == "mobile"), None)
        assert mobile_gap is not None
        assert mobile_gap["severity"] == "critical"
        assert mobile_gap["supply_count"] == 0

    def test_no_gap_when_covered(self, team_members, tasks):
        gaps = _identify_skill_gaps(team_members, tasks)
        # "python" is well covered (3 members, 3 tasks)
        python_gap = next((g for g in gaps if g["skill"] == "python"), None)
        assert python_gap is None

    def test_high_severity_gap(self):
        members = [{"name": "X", "skills": ["go"], "availability_hours": 40}]
        tasks = [
            {"name": f"Task {i}", "required_skills": ["go"], "estimate_hours": 5, "assignee": None, "sprint": None}
            for i in range(5)
        ]
        gaps = _identify_skill_gaps(members, tasks)
        go_gap = next((g for g in gaps if g["skill"] == "go"), None)
        assert go_gap is not None
        assert go_gap["severity"] == "high"

    def test_empty_inputs(self):
        gaps = _identify_skill_gaps([], [])
        assert gaps == []


class TestIdentifyOverUnderAllocation:
    def test_over_allocated(self):
        rates = [
            {"member": "Alice", "available_hours": 40, "allocated_hours": 60, "utilization_pct": 150},
        ]
        result = _identify_over_under_allocation(rates)
        assert len(result["over_allocated"]) == 1
        assert result["over_allocated"][0]["member"] == "Alice"
        assert result["over_allocated"][0]["over_hours"] == 20

    def test_under_allocated(self):
        rates = [
            {"member": "Bob", "available_hours": 40, "allocated_hours": 10, "utilization_pct": 25},
        ]
        result = _identify_over_under_allocation(rates)
        assert len(result["under_allocated"]) == 1
        assert result["under_allocated"][0]["member"] == "Bob"
        assert result["under_allocated"][0]["spare_hours"] == 30

    def test_normal_allocation(self):
        rates = [
            {"member": "Carol", "available_hours": 40, "allocated_hours": 30, "utilization_pct": 75},
        ]
        result = _identify_over_under_allocation(rates)
        assert result["over_allocated"] == []
        assert result["under_allocated"] == []


class TestGenerateCapacityForecasts:
    def test_sprint_forecasts(self, team_members, tasks, sprints):
        forecasts = _generate_capacity_forecasts(team_members, tasks, sprints)
        assert len(forecasts) == 2

        sprint1 = forecasts[0]
        assert sprint1["sprint"] == "Sprint 1"
        assert sprint1["demand_hours"] == 65  # 20 + 30 + 15
        assert sprint1["capacity_hours"] == 110
        assert sprint1["delta_hours"] == 45
        assert sprint1["status"] == "under_capacity"

    def test_over_capacity(self, team_members):
        tasks = [
            {"name": "Big task", "required_skills": [], "estimate_hours": 200, "assignee": None, "sprint": "S1"},
        ]
        sprints = [{"name": "S1", "capacity_hours": 100}]
        forecasts = _generate_capacity_forecasts(team_members, tasks, sprints)
        assert forecasts[0]["status"] == "over_capacity"
        assert forecasts[0]["delta_hours"] == -100

    def test_no_sprints(self, team_members, tasks):
        forecasts = _generate_capacity_forecasts(team_members, tasks, None)
        assert forecasts == []


class TestBuildResourcePlanningReport:
    def test_report_structure(self, team_members, tasks, sprints):
        report = build_resource_planning_report(team_members, tasks, sprints)
        assert report["schema_version"] == "max.resource_planning.v1"
        assert report["kind"] == "max.resource_planning"
        assert "team_capacity" in report
        assert "allocations" in report
        assert "utilization_rates" in report
        assert "skill_gaps" in report
        assert "allocation_issues" in report
        assert "capacity_forecasts" in report

    def test_capacity_and_utilization(self, team_members, tasks, sprints):
        report = build_resource_planning_report(team_members, tasks, sprints)
        assert report["team_capacity"]["total_members"] == 3
        assert report["team_capacity"]["total_available_hours"] == 110
        assert len(report["utilization_rates"]) == 3

    def test_skill_gaps_detected(self, team_members, tasks, sprints):
        report = build_resource_planning_report(team_members, tasks, sprints)
        # "mobile" skill should be flagged
        mobile_gap = next(
            (g for g in report["skill_gaps"] if g["skill"] == "mobile"), None
        )
        assert mobile_gap is not None


class TestRenderMarkdown:
    def test_renders_without_error(self, team_members, tasks, sprints):
        report = build_resource_planning_report(team_members, tasks, sprints)
        md = render_resource_planning_markdown(report)
        assert "# Resource Planning Report" in md
        assert "## Team Capacity" in md
        assert "## Utilization Rates" in md

    def test_contains_member_data(self, team_members, tasks, sprints):
        report = build_resource_planning_report(team_members, tasks, sprints)
        md = render_resource_planning_markdown(report)
        assert "Alice" in md
        assert "Bob" in md
        assert "Carol" in md

    def test_contains_forecasts(self, team_members, tasks, sprints):
        report = build_resource_planning_report(team_members, tasks, sprints)
        md = render_resource_planning_markdown(report)
        assert "Sprint 1" in md
        assert "Sprint 2" in md
