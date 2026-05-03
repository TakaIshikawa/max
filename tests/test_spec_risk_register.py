"""Tests for risk register CSV rendering."""

from __future__ import annotations

import csv
from io import StringIO

from max.spec import generate_risk_register
from max.spec import render_risk_register_csv as exported_render_csv
from max.spec.risk_register import RISK_REGISTER_CSV_COLUMNS, render_risk_register_csv


def test_render_risk_register_csv_includes_traceability_and_risk_rows(
    sample_unit, sample_evaluation
) -> None:
    unit = sample_unit.model_copy(
        update={
            "specific_user": "",
            "buyer": "",
            "workflow_context": "",
            "domain_risks": ["protocol churn could break implementations"],
        }
    )
    evaluation = sample_evaluation.model_copy(
        update={
            "pain_severity": sample_evaluation.pain_severity.model_copy(update={"value": 4.5}),
        }
    )
    register = generate_risk_register(
        unit,
        evaluation,
        {"density_score": 24.0, "average_credibility": 0.4},
        None,
    )

    rendered = render_risk_register_csv(register)
    rows = list(csv.DictReader(StringIO(rendered)))
    summary_rows = [row for row in rows if row["section"] == "summary"]
    source_rows = [row for row in rows if row["section"] == "source_flags"]
    risk_rows = [row for row in rows if row["section"] == "risks"]

    assert exported_render_csv(register) == rendered
    assert rendered == render_risk_register_csv(register)
    assert rendered.splitlines()[0] == ",".join(RISK_REGISTER_CSV_COLUMNS)
    assert len(risk_rows) == register["summary"]["risk_count"]
    assert {"risk_count", "top_risk_id", "schema_version"} <= {
        row["key"] for row in summary_rows
    }
    assert {
        ("evaluation_available", "true"),
        ("evidence_density_available", "true"),
        ("contradictions_available", "false"),
    } <= {(row["key"], row["value"]) for row in source_rows}

    first_risk = risk_rows[0]
    first_register_risk = register["risks"][0]
    assert first_risk["priority"] == "1"
    assert first_risk["risk_id"] == first_register_risk["id"]
    assert first_risk["title"] == first_register_risk["title"]
    assert first_risk["severity"] == first_register_risk["severity"]
    assert first_risk["likelihood"] == first_register_risk["likelihood"]
    assert first_risk["source"] == first_register_risk["source"]
    assert first_risk["description"] == first_register_risk["description"]
    assert first_risk["owner_suggestion"] == first_register_risk["owner_suggestion"]
    assert first_risk["mitigations"]
    assert first_risk["validation_trigger"] == first_register_risk["validation_trigger"]
    assert any("signal:sig-test001" in row["evidence_links"] for row in risk_rows)


def test_render_risk_register_csv_handles_empty_risk_register(sample_unit) -> None:
    register = generate_risk_register(
        sample_unit.model_copy(
            update={
                "domain_risks": [],
                "inspiring_insights": ["ins-test001"],
                "evidence_signals": ["sig-test001"],
                "source_idea_ids": [],
            }
        ),
        None,
        {"density_score": 80.0, "average_credibility": 0.9},
        None,
    )
    register["risks"] = []
    register["validation_triggers"] = []
    register["summary"] = {
        **register["summary"],
        "risk_count": 0,
        "critical_risk_count": 0,
        "high_risk_count": 0,
        "top_risk_id": None,
    }

    rows = list(csv.DictReader(StringIO(render_risk_register_csv(register))))

    assert [row for row in rows if row["section"] == "risks"] == []
    assert any(row["section"] == "summary" and row["key"] == "risk_count" for row in rows)
    assert any(
        row["section"] == "source_flags" and row["key"] == "evaluation_available"
        for row in rows
    )


def test_render_risk_register_csv_orders_risks_by_priority() -> None:
    register = {
        "idea_id": "bu-order",
        "summary": {"title": "Ordering", "risk_count": 2},
        "source": {"idea_id": "bu-order", "evaluation_available": False},
        "risks": [
            _risk("risk-2", 2, "Second"),
            _risk("risk-1", 1, "First"),
        ],
    }

    rows = list(csv.DictReader(StringIO(render_risk_register_csv(register))))

    assert [row["risk_id"] for row in rows if row["section"] == "risks"] == [
        "risk-1",
        "risk-2",
    ]


def test_render_risk_register_csv_uses_csv_writer_escaping() -> None:
    register = {
        "idea_id": "bu-escape",
        "summary": {"title": 'CSV "Escape", Case', "risk_count": 1},
        "source": {"idea_id": "bu-escape", "evaluation_available": False},
        "risks": [
            {
                **_risk('risk,"quoted"', 1, 'Quoted "risk", high'),
                "description": 'Line one\nLine two, with "quotes"',
                "owner_suggestion": "PM, Risk",
                "mitigations": ['Ask buyers, then document "go/no-go".'],
                "evidence_links": ["signal:one,two", 'insight:"three"'],
                "validation_trigger": "Run review\nRecord outcome",
            }
        ],
    }

    rendered = render_risk_register_csv(register)
    rows = list(csv.DictReader(StringIO(rendered)))
    risk_row = next(row for row in rows if row["section"] == "risks")

    assert '"risk,""quoted"""' in rendered
    assert '"Line one\nLine two, with ""quotes"""' in rendered
    assert risk_row["risk_id"] == 'risk,"quoted"'
    assert risk_row["description"] == 'Line one\nLine two, with "quotes"'
    assert risk_row["mitigations"] == 'Ask buyers, then document "go/no-go".'
    assert risk_row["evidence_links"] == 'signal:one,two; insight:"three"'
    assert risk_row["validation_trigger"] == "Run review\nRecord outcome"


def _risk(risk_id: str, priority: int, title: str) -> dict[str, object]:
    return {
        "id": risk_id,
        "priority": priority,
        "title": title,
        "severity": "high",
        "likelihood": "likely",
        "source": "manual",
        "description": f"{title} description",
        "owner_suggestion": "product_owner",
        "mitigations": [f"Mitigate {title}"],
        "evidence_links": [f"signal:{risk_id}"],
        "validation_trigger": f"Validate {title}",
    }
