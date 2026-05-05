from __future__ import annotations

import csv
import json
from io import StringIO

from max.spec.generator import generate_spec_preview
from max.spec.scaling_strategy import (
    SCALING_STRATEGY_CSV_COLUMNS,
    SCALING_STRATEGY_SCHEMA_VERSION,
    generate_scaling_strategy,
    render_scaling_strategy_csv,
    render_scaling_strategy_markdown,
)
from max.types.buildable_unit import BuildableCategory, BuildableUnit


def _scaling_unit() -> BuildableUnit:
    return BuildableUnit(
        id="bu-scaling",
        title="Real-Time Analytics Dashboard",
        one_liner="Provide real-time analytics for customer behavior.",
        category=BuildableCategory.FEATURE,
        problem="Teams need real-time insights into user behavior patterns.",
        solution="A scalable analytics dashboard with auto-scaling based on query load.",
        target_users="data analysts",
        value_proposition="Enable data-driven decisions with real-time insights.",
        specific_user="product analyst",
        buyer="head of product",
        workflow_context="query submission to insight delivery",
        current_workaround="batch processing with daily reports",
        validation_plan="run load tests with realistic query patterns",
        domain_risks=["Query performance degradation under high load."],
        tech_approach="FastAPI backend with Kubernetes orchestration and Redis caching.",
        suggested_stack={
            "backend": "FastAPI",
            "database": "PostgreSQL",
            "cache": "Redis",
            "orchestration": "Kubernetes",
        },
        composability_notes="Expose metrics API for downstream monitoring.",
        domain="analytics",
        status="approved",
    )


def _serverless_unit() -> BuildableUnit:
    return BuildableUnit(
        id="bu-serverless",
        title="Document Processing Pipeline",
        one_liner="Process documents with serverless functions.",
        category=BuildableCategory.AUTOMATION,
        problem="Document processing needs to scale elastically.",
        solution="Serverless document processing with automatic scaling.",
        target_users="operations team",
        value_proposition="Scale processing without infrastructure management.",
        specific_user="operations coordinator",
        buyer="operations director",
        workflow_context="document upload to processed output",
        validation_plan="test with various document sizes and volumes",
        tech_approach="AWS Lambda functions with S3 storage and DynamoDB.",
        suggested_stack={
            "compute": "AWS Lambda",
            "storage": "S3",
            "database": "DynamoDB",
        },
        domain="operations",
        status="approved",
    )


def test_generate_scaling_strategy_is_json_ready_and_has_capacity_thresholds(
    sample_evaluation,
) -> None:
    unit = _scaling_unit()
    spec = generate_spec_preview(unit, sample_evaluation)

    first = generate_scaling_strategy(unit, sample_evaluation, spec)
    second = generate_scaling_strategy(unit, sample_evaluation, spec)

    assert first == second
    assert json.loads(json.dumps(first)) == first
    assert first["schema_version"] == SCALING_STRATEGY_SCHEMA_VERSION
    assert first["kind"] == "max.scaling_strategy"
    assert first["idea_id"] == "bu-scaling"
    assert set(first) == {
        "schema_version",
        "kind",
        "idea_id",
        "source",
        "summary",
        "capacity_thresholds",
        "auto_scaling_rules",
        "horizontal_scaling",
        "vertical_scaling",
        "cost_projections",
    }

    assert len(first["capacity_thresholds"]) >= 3
    assert len(first["auto_scaling_rules"]) >= 2
    assert len(first["horizontal_scaling"]) >= 1
    assert len(first["cost_projections"]) >= 2

    by_id = {item["id"]: item for item in first["capacity_thresholds"]}
    assert "threshold_cpu" in by_id
    assert by_id["threshold_cpu"]["metric_name"] == "cpu_utilization"
    assert by_id["threshold_cpu"]["value"] == 70
    assert by_id["threshold_cpu"]["unit"] == "%"
    assert "solution.technical_approach" in by_id["threshold_cpu"]["source_fields"]


def test_generate_scaling_strategy_includes_vertical_scaling_for_database(
    sample_evaluation,
) -> None:
    unit = _scaling_unit()
    spec = generate_spec_preview(unit, sample_evaluation)

    strategy = generate_scaling_strategy(unit, sample_evaluation, spec)

    assert len(strategy["vertical_scaling"]) >= 1
    by_id = {item["id"]: item for item in strategy["vertical_scaling"]}
    assert "vertical_database" in by_id
    assert by_id["vertical_database"]["dimension"] == "database_tier"
    assert "solution.suggested_stack.database" in by_id["vertical_database"]["source_fields"]


def test_generate_scaling_strategy_serverless_approach_has_minimal_horizontal_config(
    sample_evaluation,
) -> None:
    unit = _serverless_unit()
    spec = generate_spec_preview(unit, sample_evaluation)

    strategy = generate_scaling_strategy(unit, sample_evaluation, spec)

    assert strategy["summary"]["scaling_approach"] == "serverless_auto_scaling"
    assert len(strategy["horizontal_scaling"]) == 1
    horizontal = strategy["horizontal_scaling"][0]
    assert horizontal["id"] == "horizontal_serverless"
    assert horizontal["dimension"] == "serverless_functions"
    assert horizontal["min_instances"] == 1
    assert horizontal["max_instances"] == 100


def test_generate_scaling_strategy_high_addressable_scale_adds_burst_rule(
    sample_evaluation,
) -> None:
    unit = _scaling_unit()
    sample_evaluation.addressable_scale.value = 8
    spec = generate_spec_preview(unit, sample_evaluation)

    strategy = generate_scaling_strategy(unit, sample_evaluation, spec)

    assert len(strategy["capacity_thresholds"]) >= 4
    assert len(strategy["auto_scaling_rules"]) >= 3

    threshold_ids = {item["id"] for item in strategy["capacity_thresholds"]}
    assert "threshold_request_rate" in threshold_ids

    rule_ids = {item["id"] for item in strategy["auto_scaling_rules"]}
    assert "rule_burst_capacity" in rule_ids

    by_id = {item["id"]: item for item in strategy["auto_scaling_rules"]}
    assert "evaluation.addressable_scale" in by_id["rule_burst_capacity"]["source_fields"]


def test_render_scaling_strategy_markdown_has_stable_sections(
    sample_evaluation,
) -> None:
    unit = _scaling_unit()
    strategy = generate_scaling_strategy(
        unit, sample_evaluation, generate_spec_preview(unit, sample_evaluation)
    )

    first = render_scaling_strategy_markdown(strategy)
    second = render_scaling_strategy_markdown(strategy)

    assert first == second
    assert first.startswith("# Real-Time Analytics Dashboard Scaling Strategy")
    assert f"- Schema version: {SCALING_STRATEGY_SCHEMA_VERSION}" in first
    assert "## Capacity Thresholds" in first
    assert "## Auto-Scaling Rules" in first
    assert "## Horizontal Scaling" in first
    assert "## Vertical Scaling" in first
    assert "## Cost Projections" in first
    assert "threshold_cpu: cpu_utilization" in first
    assert "rule_scale_up_cpu: scale_up" in first


def test_render_scaling_strategy_csv_has_headers_and_all_section_rows(
    sample_evaluation,
) -> None:
    unit = _scaling_unit()
    strategy = generate_scaling_strategy(
        unit, sample_evaluation, generate_spec_preview(unit, sample_evaluation)
    )

    first = render_scaling_strategy_csv(strategy)
    second = render_scaling_strategy_csv(strategy)
    reader = csv.DictReader(StringIO(first))
    rows = list(reader)

    assert first == second
    assert reader.fieldnames == list(SCALING_STRATEGY_CSV_COLUMNS)
    assert first.splitlines()[0] == ",".join(SCALING_STRATEGY_CSV_COLUMNS)

    threshold_count = len(strategy["capacity_thresholds"])
    rule_count = len(strategy["auto_scaling_rules"])
    horizontal_count = len(strategy["horizontal_scaling"])
    vertical_count = len(strategy["vertical_scaling"])
    projection_count = len(strategy["cost_projections"])
    expected_row_count = (
        threshold_count + rule_count + horizontal_count + vertical_count + projection_count
    )

    assert len(rows) == expected_row_count

    sections = {row["section"] for row in rows}
    assert "capacity_thresholds" in sections
    assert "auto_scaling_rules" in sections
    assert "horizontal_scaling" in sections
    assert "cost_projections" in sections

    threshold_rows = [row for row in rows if row["section"] == "capacity_thresholds"]
    assert len(threshold_rows) == threshold_count
    cpu_threshold = next(row for row in threshold_rows if row["item_id"] == "threshold_cpu")
    assert cpu_threshold["row_type"] == "threshold"
    assert cpu_threshold["metric_name"] == "cpu_utilization"
    assert cpu_threshold["threshold_type"] == "percentage"
    assert cpu_threshold["threshold_value"] == "70"
    assert cpu_threshold["threshold_unit"] == "%"
    assert "solution.technical_approach" in cpu_threshold["source_fields"]

    rule_rows = [row for row in rows if row["section"] == "auto_scaling_rules"]
    assert len(rule_rows) == rule_count
    scale_up_rule = next(row for row in rule_rows if row["item_id"] == "rule_scale_up_cpu")
    assert scale_up_rule["row_type"] == "scaling_rule"
    assert scale_up_rule["scaling_action"] == "scale_up"
    assert scale_up_rule["trigger_condition"] == "cpu_utilization > 70%"
    assert scale_up_rule["cooldown_period_seconds"] == "300"

    horizontal_rows = [row for row in rows if row["section"] == "horizontal_scaling"]
    assert len(horizontal_rows) == horizontal_count
    web_horizontal = next(row for row in horizontal_rows if row["item_id"] == "horizontal_web")
    assert web_horizontal["row_type"] == "horizontal_config"
    assert web_horizontal["scaling_type"] == "horizontal"
    assert web_horizontal["scaling_dimension"] == "web_tier"
    assert web_horizontal["min_instances"] == "2"
    assert web_horizontal["max_instances"] == "10"

    vertical_rows = [row for row in rows if row["section"] == "vertical_scaling"]
    assert len(vertical_rows) == vertical_count
    if vertical_count > 0:
        db_vertical = next(
            row for row in vertical_rows if row["item_id"] == "vertical_database"
        )
        assert db_vertical["row_type"] == "vertical_config"
        assert db_vertical["scaling_type"] == "vertical"
        assert db_vertical["scaling_dimension"] == "database_tier"

    projection_rows = [row for row in rows if row["section"] == "cost_projections"]
    assert len(projection_rows) == projection_count
    baseline = next(row for row in projection_rows if row["item_id"] == "cost_baseline")
    assert baseline["row_type"] == "cost_projection"
    assert float(baseline["projected_monthly_cost_usd"]) > 0


def test_render_scaling_strategy_csv_empty_sections_are_omitted() -> None:
    minimal_strategy = {
        "schema_version": SCALING_STRATEGY_SCHEMA_VERSION,
        "kind": "max.scaling_strategy",
        "idea_id": "bu-minimal",
        "summary": {"title": "Minimal Strategy"},
        "capacity_thresholds": [],
        "auto_scaling_rules": [],
        "horizontal_scaling": [],
        "vertical_scaling": [],
        "cost_projections": [],
    }

    csv_text = render_scaling_strategy_csv(minimal_strategy)

    assert csv_text == ",".join(SCALING_STRATEGY_CSV_COLUMNS) + "\n"
    assert list(csv.DictReader(StringIO(csv_text))) == []


def test_render_scaling_strategy_csv_handles_list_source_fields() -> None:
    strategy = {
        "schema_version": SCALING_STRATEGY_SCHEMA_VERSION,
        "kind": "max.scaling_strategy",
        "idea_id": "bu-csv",
        "summary": {"title": "CSV Test"},
        "capacity_thresholds": [
            {
                "id": "threshold_test",
                "metric_name": "test_metric",
                "threshold_type": "percentage",
                "value": 75,
                "unit": "%",
                "notes": "Test threshold",
                "source_fields": ["field_a", "field_b", "field_c"],
            }
        ],
        "auto_scaling_rules": [],
        "horizontal_scaling": [],
        "vertical_scaling": [],
        "cost_projections": [],
    }

    csv_text = render_scaling_strategy_csv(strategy)
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert len(rows) == 1
    assert rows[0]["source_fields"] == "field_a | field_b | field_c"


def test_cost_projections_scale_with_build_effort(sample_evaluation) -> None:
    unit = _scaling_unit()
    sample_evaluation.build_effort.value = 8
    spec = generate_spec_preview(unit, sample_evaluation)

    strategy = generate_scaling_strategy(unit, sample_evaluation, spec)

    baseline = next(
        item for item in strategy["cost_projections"] if item["id"] == "cost_baseline"
    )
    assert baseline["monthly_cost_usd"] > 100.0


def test_serverless_strategy_has_no_vertical_scaling() -> None:
    unit = _serverless_unit()
    strategy = generate_scaling_strategy(unit, None, None)

    assert strategy["summary"]["scaling_approach"] == "serverless_auto_scaling"
    assert len(strategy["vertical_scaling"]) == 0
