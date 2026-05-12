import csv
import io

from tests._design_brief_artifact_endpoint_helpers import api_client

from max.analysis.design_brief_kill_criteria import CSV_COLUMNS, KIND, SCHEMA_VERSION
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.signal import Signal, SignalSourceType


def _seed_idea(db_path: str) -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_signal(
            Signal(
                id="sig-kill-001",
                source_type=SignalSourceType.SURVEY,
                source_adapter="test",
                title="Operators report manual renewal handoff failures",
                content=(
                    "Product operations teams report costly manual handoff failures "
                    "during renewal reviews."
                ),
                url="https://example.com/kill-criteria-evidence",
                credibility=0.86,
            )
        )
        unit = BuildableUnit(
            id="idea-kill-001",
            title="Renewal Gatekeeper",
            one_liner="Stop, pivot, or continue renewal workflow bets with explicit gates.",
            category="application",
            problem="Manual renewal handoff failures create costly delays and missed reviews.",
            solution="Track validation gates for stop, pivot, and continue decisions.",
            value_proposition="Keep product operations from expanding weak renewal ideas.",
            specific_user="product operations manager",
            buyer="VP of Product",
            workflow_context="quarterly renewal review workflow",
            current_workaround="Teams review spreadsheets manually and miss risk signals.",
            why_now="Renewal risk is increasing as customer workflows expand.",
            validation_plan="Run five customer validation sessions and review gate outcomes.",
            evidence_rationale="Survey and interview notes indicate the workflow pain is recurring.",
            evidence_signals=["sig-kill-001"],
            domain="product-ops",
            status="approved",
        )
        store.insert_buildable_unit(unit)
        return unit.id
    finally:
        store.close()


def test_idea_kill_criteria_json(tmp_path) -> None:
    db_path = str(tmp_path / "idea_kill_criteria.db")
    idea_id = _seed_idea(db_path)
    client = api_client(db_path)

    response = client.get(f"/api/v1/ideas/{idea_id}/kill-criteria")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["kind"] == KIND
    assert payload["design_brief"]["id"] == idea_id
    assert payload["summary"]["evidence_count"] >= 2
    assert isinstance(payload["stop_triggers"], list)
    assert isinstance(payload["pivot_triggers"], list)
    assert isinstance(payload["continue_signals"], list)
    assert payload["next_validation_action"]["owner"]
    assert any(ref["id"] == "sig-kill-001" for ref in payload["evidence_references"])


def test_idea_kill_criteria_markdown_and_csv_attachments(tmp_path) -> None:
    db_path = str(tmp_path / "idea_kill_criteria_exports.db")
    idea_id = _seed_idea(db_path)
    client = api_client(db_path)

    markdown_response = client.get(f"/api/v1/ideas/{idea_id}/kill-criteria.md")
    markdown_format_response = client.get(
        f"/api/v1/ideas/{idea_id}/kill-criteria?format=markdown"
    )
    csv_response = client.get(f"/api/v1/ideas/{idea_id}/kill-criteria?format=csv")

    assert markdown_response.status_code == 200
    assert markdown_response.headers["content-type"].startswith("text/markdown")
    assert "attachment; filename=" in markdown_response.headers["content-disposition"]
    assert "kill-criteria.md" in markdown_response.headers["content-disposition"]
    assert markdown_response.text.startswith("# Kill Criteria: Renewal Gatekeeper")
    assert markdown_format_response.status_code == 200
    assert markdown_format_response.text == markdown_response.text

    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=" in csv_response.headers["content-disposition"]
    assert "kill-criteria.csv" in csv_response.headers["content-disposition"]
    reader = csv.DictReader(io.StringIO(csv_response.text))
    assert reader.fieldnames == list(CSV_COLUMNS)


def test_idea_kill_criteria_missing_and_unsupported_format(tmp_path) -> None:
    db_path = str(tmp_path / "idea_kill_criteria_missing.db")
    idea_id = _seed_idea(db_path)
    client = api_client(db_path)

    missing = client.get("/api/v1/ideas/idea-missing/kill-criteria")
    unsupported = client.get(f"/api/v1/ideas/{idea_id}/kill-criteria?format=yaml")

    assert missing.status_code == 404
    assert missing.json()["detail"] == "Idea not found: idea-missing"
    assert unsupported.status_code == 422
