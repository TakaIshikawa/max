"""MCP quality-loop inspection tests."""

from __future__ import annotations

import json

from max.server.mcp_tools import (
    evidence_pack_detail,
    get_evidence_pack,
    get_idea,
    get_idea_critique,
    search_ideas,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_mcp_exposes_quality_fields_and_evidence_pack(tmp_path):
    db_path = str(tmp_path / "mcp_quality.db")
    store = Store(db_path=db_path, wal_mode=True)
    unit = BuildableUnit(
        id="bu-mcp-quality",
        title="Quality MCP Idea",
        one_liner="Quality fields in MCP",
        category="application",
        problem="Quality data hidden",
        solution="Expose it via MCP",
        value_proposition="Inspectable ideas",
        specific_user="platform engineer",
        buyer="VP engineering",
        workflow_context="idea review",
        quality_score=7.2,
        novelty_score=6.0,
        usefulness_score=8.0,
    )
    store.insert_buildable_unit(unit)
    store.insert_feedback(unit.id, "rejected", "not enough buyer pull")
    store.insert_idea_critique(
        unit.id,
        {
            "urgency": 7,
            "buyer_clarity": 8,
            "specificity": 8,
            "evidence_support": 6,
            "feasibility": 7,
            "differentiation": 6,
            "distribution_path": 6,
            "domain_risk": 7,
            "novelty": 6,
            "usefulness": 8,
            "quality_score": 6.9,
            "reasoning": "Good review workflow.",
            "rejection_tags": [],
        },
        evidence_pack={"domain_name": "developer-tools"},
    )
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    try:
        results = search_ideas()
        assert results[0]["quality_score"] == 7.2
        assert results[0]["review_state"] == "rejected"
        assert results[0]["feedback_outcome"] == "rejected"
        assert "ReviewRejected" in results[0]["graph_labels"]

        detail = get_idea(unit.id)
        assert detail["buyer"] == "VP engineering"
        assert detail["review_state"] == "rejected"
        assert detail["feedback_reason"] == "not enough buyer pull"
        assert detail["latest_critique"]["dimensions"]["buyer_clarity"] == 8

        critique = get_idea_critique(unit.id)
        assert critique["critiques"][0]["dimensions"]["quality_score"] == 6.9

        pack = get_evidence_pack(unit.id)
        assert pack["domain_name"] == "developer-tools"

        resource_payload = json.loads(evidence_pack_detail(unit.id))
        assert resource_payload["domain_name"] == "developer-tools"
    finally:
        set_store_factory(lambda: Store(wal_mode=True))
