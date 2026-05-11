from __future__ import annotations

import csv
import io
import json

from fastapi.testclient import TestClient

from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.server.dependencies import get_store
from max.server.mcp_tools import set_store_factory
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def api_client(db_path: str) -> TestClient:
    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def seed_design_brief(db_path: str, *, label: str = "Artifact") -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        lead = BuildableUnit(
            id=f"bu-{label.lower().replace(' ', '-')}-lead",
            title=f"{label} Lead",
            one_liner="Expose generated design brief artifacts through product APIs.",
            category="application",
            problem="Downstream teams cannot retrieve design brief analysis artifacts.",
            solution="Publish deterministic JSON, Markdown, and CSV exports.",
            value_proposition="Reduce handoff ambiguity for product, GTM, and engineering teams.",
            specific_user="product operations manager",
            buyer="VP of Product",
            workflow_context="launch readiness review",
            current_workaround="Manual copying from local analysis output.",
            why_now="Design briefs already contain enough structured planning context.",
            validation_plan="Compare REST and MCP payloads with renderer output.",
            domain_risks=["Security review may delay launch.", "Procurement proof may be weak."],
            evidence_rationale="Interview and validation notes support the brief.",
            evidence_signals=["sig-artifact-1", "sig-artifact-2"],
            inspiring_insights=["ins-artifact-1"],
            domain="product-ops",
            status="approved",
        )
        support = BuildableUnit(
            id=f"bu-{label.lower().replace(' ', '-')}-support",
            title=f"{label} Support",
            one_liner="Keep artifact exports traceable to source ideas.",
            category="application",
            problem="Analysis handoffs lose source traceability.",
            solution="Attach source idea references and evidence notes.",
            value_proposition="Make artifact consumers confident in generated recommendations.",
            specific_user="engineering manager",
            buyer="VP of Engineering",
            workflow_context="implementation planning",
            validation_plan="Review generated artifact rows with owners.",
            domain_risks=["Integration dependencies may require OAuth approval."],
            evidence_signals=["sig-artifact-3"],
            domain="product-ops",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        store.insert_buildable_unit(support)
        return store.insert_design_brief(
            ProjectBrief(
                title=f"{label} API Brief",
                domain="product-ops",
                theme="artifact-api-export",
                lead=Candidate(unit=lead),
                supporting=[Candidate(unit=support)],
                readiness_score=86.0,
                why_this_now="API access lets automation retrieve design brief artifacts.",
                merged_product_concept=(
                    "A deterministic artifact export surface for persisted design briefs."
                ),
                synthesis_rationale="The artifact modules already produce stable reports.",
                mvp_scope=["JSON artifact route", "Markdown artifact download", "CSV artifact download"],
                first_milestones=["Expose artifact through REST", "Expose artifact through MCP"],
                validation_plan="Confirm endpoint responses match artifact renderers.",
                risks=["Security review may delay launch.", "Procurement proof may be weak."],
                source_idea_ids=[lead.id, support.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def configure_mcp_store(db_path: str) -> None:
    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))


def reset_mcp_store() -> None:
    set_store_factory(lambda: Store(wal_mode=True))


def assert_api_artifact(
    tmp_path,
    *,
    path: str,
    kind: str,
    schema_version: str,
    markdown_heading: str,
    csv_header: tuple[str, ...] | None = None,
) -> None:
    db_path = str(tmp_path / f"{path.replace('-', '_')}.db")
    brief_id = seed_design_brief(db_path, label=path.replace("-", " ").title())
    client = api_client(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/{path}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == schema_version
    assert payload["kind"] == kind
    assert payload["design_brief"]["id"] == brief_id

    markdown_response = client.get(f"/api/v1/design-briefs/{brief_id}/{path}.md")
    assert markdown_response.status_code == 200
    assert markdown_response.headers["content-type"].startswith("text/markdown")
    assert "attachment; filename=" in markdown_response.headers["content-disposition"]
    assert markdown_response.text.startswith(markdown_heading)

    if csv_header is not None:
        csv_response = client.get(f"/api/v1/design-briefs/{brief_id}/{path}.csv")
        assert csv_response.status_code == 200
        assert csv_response.headers["content-type"].startswith("text/csv")
        assert "attachment; filename=" in csv_response.headers["content-disposition"]
        reader = csv.DictReader(io.StringIO(csv_response.text))
        assert reader.fieldnames == list(csv_header)

    missing = client.get(f"/api/v1/design-briefs/dbf-missing/{path}")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Design brief not found: dbf-missing"


def assert_mcp_artifact(
    tmp_path,
    *,
    tool,
    resource,
    kind: str,
    schema_version: str,
    markdown_heading: str,
    csv_header: tuple[str, ...] | None = None,
) -> None:
    db_path = str(tmp_path / f"{tool.__name__}.db")
    brief_id = seed_design_brief(db_path, label=tool.__name__.replace("_", " ").title())
    configure_mcp_store(db_path)
    try:
        payload = tool(brief_id)
        assert payload["schema_version"] == schema_version
        assert payload["kind"] == kind
        assert payload["design_brief"]["id"] == brief_id

        markdown = tool(brief_id, format="markdown")
        assert markdown["id"] == brief_id
        assert markdown["format"] == "markdown"
        assert markdown["markdown"].startswith(markdown_heading)

        if csv_header is not None:
            csv_payload = tool(brief_id, format="csv")
            assert csv_payload["id"] == brief_id
            assert csv_payload["format"] == "csv"
            reader = csv.DictReader(io.StringIO(csv_payload["csv"]))
            assert reader.fieldnames == list(csv_header)

        missing = tool("dbf-missing")
        assert missing["error"] == "Design brief not found: dbf-missing"
        assert missing["code"] == 404

        resource_payload = json.loads(resource(brief_id))
        assert resource_payload["schema_version"] == schema_version
        assert resource_payload["design_brief"]["id"] == brief_id
    finally:
        reset_mcp_store()
