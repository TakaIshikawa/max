"""Tests for design brief stakeholder map REST exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_stakeholder_map import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test_design_brief_stakeholder_map_api.db")
    Store(db_path=path, wal_mode=True).close()
    return path


@pytest.fixture
def client(db_path: str) -> TestClient:
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def _seed_design_brief(db_path: str) -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_signal(
            Signal(
                id="sig-budget",
                source_type=SignalSourceType.FUNDING,
                source_adapter="budget_report",
                title="Budget owner purchase intent",
                content="Engineering leaders have budget for release workflow governance.",
                url="https://example.com/sig-budget",
                tags=["budget", "buyer"],
                credibility=0.86,
                metadata={"signal_role": "budget"},
            )
        )
        store.insert_signal(
            Signal(
                id="sig-user-pain",
                source_type=SignalSourceType.SURVEY,
                source_adapter="survey",
                title="Platform engineer workflow pain",
                content="Users report manual release reviews and unclear adoption paths.",
                url="https://example.com/sig-user-pain",
                tags=["user", "workflow", "pain"],
                credibility=0.82,
                metadata={"signal_role": "problem"},
            )
        )
        store.insert_signal(
            Signal(
                id="sig-approval",
                source_type=SignalSourceType.SECURITY,
                source_adapter="security_review",
                title="Security approval risk",
                content="Security approval and procurement review can block rollout.",
                url="https://example.com/sig-approval",
                tags=["security", "approval", "risk"],
                credibility=0.8,
                metadata={"signal_role": "risk"},
            )
        )
        store.insert_insight(
            Insight(
                id="ins-stakeholder",
                category=InsightCategory.EMERGING_PATTERN,
                title="Approval path needs stakeholder mapping",
                summary="Teams need buyer, user, and approval owners before pilots.",
                evidence=["sig-approval"],
                confidence=0.78,
                domains=["developer-tools"],
            )
        )

        lead = BuildableUnit(
            id="bu-stakeholder-lead",
            title="Stakeholder Release Map",
            one_liner="Map stakeholders for release governance pilots.",
            category="application",
            problem="Platform teams do not know who must approve release governance pilots.",
            solution="Generate a stakeholder map from persisted design brief lineage.",
            value_proposition="Make buyer, user, approver, and blocker assumptions explicit.",
            specific_user="platform engineer",
            buyer="VP of Engineering",
            workflow_context="agent release governance review",
            current_workaround="manual release notes and ad hoc approval chats",
            why_now="Agent release reviews are becoming a recurring governance workflow.",
            validation_plan="Interview platform engineers, security approvers, and engineering buyers.",
            first_10_customers="platform teams shipping production agents",
            domain_risks=["Security approval and procurement review may block rollout."],
            evidence_rationale="Evidence shows user pain, budget ownership, and approval risk.",
            evidence_signals=["sig-budget", "sig-user-pain"],
            inspiring_insights=["ins-stakeholder"],
            tech_approach="Deterministic Python report over persisted Store records.",
            suggested_stack={"language": "python"},
            domain="developer-tools",
            status="approved",
        )
        support = BuildableUnit(
            id="bu-stakeholder-support",
            title="Stakeholder Interview Plan",
            one_liner="Ask validation questions for buyer and approver roles.",
            category="application",
            problem="Discovery skips economic buyer and blocker validation.",
            solution="Recommend interview questions by stakeholder role.",
            value_proposition="Improve GTM validation before implementation.",
            specific_user="product operator",
            buyer="product lead",
            workflow_context="pilot stakeholder discovery",
            validation_plan="Validate champion access and approval gates.",
            domain_risks=["Champion may not control budget."],
            evidence_signals=["sig-user-pain"],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        store.insert_buildable_unit(support)
        store.insert_evaluation(_evaluation(lead.id, 86.0))
        store.insert_evaluation(_evaluation(support.id, 78.0))

        return store.insert_design_brief(
            ProjectBrief(
                title="Stakeholder Map Brief",
                domain="developer-tools",
                theme="stakeholder-validation",
                lead=Candidate(unit=lead),
                supporting=[Candidate(unit=support)],
                readiness_score=88.0,
                why_this_now="Release governance pilots need named buyer, user, approver, and blocker roles.",
                merged_product_concept="A deterministic stakeholder map export for design briefs.",
                synthesis_rationale="Source ideas show GTM validation gaps around stakeholder ownership.",
                mvp_scope=["JSON stakeholder map", "Markdown stakeholder map"],
                first_milestones=["Build deterministic stakeholder report"],
                validation_plan="Run interviews with buyer, user, economic buyer, approver, blocker, and champion.",
                risks=["Security approval and procurement review may block rollout."],
                source_idea_ids=[lead.id, support.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def _evaluation(unit_id: str, overall_score: float) -> UtilityEvaluation:
    dim = DimensionScore(value=8.0, confidence=0.8, reasoning="seeded")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=dim,
        addressable_scale=dim,
        build_effort=dim,
        composability=dim,
        competitive_density=DimensionScore(value=5.0, confidence=0.7, reasoning="some alternatives"),
        timing_fit=dim,
        compounding_value=dim,
        overall_score=overall_score,
        strengths=["clear stakeholder"],
        weaknesses=["approval path needs validation"],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )


def test_get_design_brief_stakeholder_map_json(
    client: TestClient,
    db_path: str,
) -> None:
    brief_id = _seed_design_brief(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/stakeholder-map")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["kind"] == "max.design_brief.stakeholder_map"
    assert data["design_brief"]["id"] == brief_id
    assert data["design_brief"]["title"] == "Stakeholder Map Brief"
    assert data["summary"]["stakeholder_count"] == 7
    assert [stakeholder["role"] for stakeholder in data["stakeholders"]] == [
        "buyer",
        "user",
        "economic_buyer",
        "implementer",
        "approver",
        "blocker",
        "champion",
    ]


def test_get_design_brief_stakeholder_map_markdown_download(
    client: TestClient,
    db_path: str,
) -> None:
    brief_id = _seed_design_brief(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/stakeholder-map.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-Stakeholder-Map-Brief-stakeholder-map.md"'
    )
    assert response.text.startswith("# Stakeholder Map: Stakeholder Map Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert "### Buyer: VP of Engineering" in response.text
    assert "## Interview Questions" in response.text
    assert "`sig-approval`" in response.text


def test_get_design_brief_stakeholder_map_markdown_query_format(
    client: TestClient,
    db_path: str,
) -> None:
    brief_id = _seed_design_brief(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/stakeholder-map?format=markdown")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.text.startswith("# Stakeholder Map: Stakeholder Map Brief")


def test_get_design_brief_stakeholder_map_missing_brief_returns_404(
    client: TestClient,
) -> None:
    json_response = client.get("/api/v1/design-briefs/dbf-missing/stakeholder-map")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/stakeholder-map.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"


def test_get_design_brief_stakeholder_map_rejects_unsupported_format(
    client: TestClient,
    db_path: str,
) -> None:
    brief_id = _seed_design_brief(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/stakeholder-map?format=yaml")

    assert response.status_code == 422
