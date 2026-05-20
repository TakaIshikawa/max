from __future__ import annotations

from max.spec.evidence_trace_handoff_plan import KIND, SCHEMA_VERSION, generate_evidence_trace_handoff_plan


def test_evidence_trace_handoff_plan_builds_complete_chain() -> None:
    plan = generate_evidence_trace_handoff_plan(
        {
            "source": {"idea_id": "trace-1"},
            "evidence": {"signal_ids": ["sig-1", "sig-1"], "insight_ids": ["ins-1"]},
            "metadata": {
                "evidence_trace_handoff": {
                    "units": ["checkout worker"],
                    "evaluations": ["eval-1"],
                    "specs": ["spec-1"],
                    "owners": {"implementation_owner": "eng"},
                }
            },
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["trace_gaps"] == []
    assert plan["validation_checkpoints"][0]["complete"] is True
    assert plan["evidence_references"] == [
        {"id": "EV1", "type": "insight", "reference": "insight:ins-1"},
        {"id": "EV2", "type": "signal", "reference": "signal:sig-1"},
    ]
    assert plan["evidence_bundle"][0]["evidence_reference_ids"] == ["EV1", "EV2"]


def test_evidence_trace_handoff_plan_reports_partial_chain_gaps() -> None:
    plan = generate_evidence_trace_handoff_plan({"evidence": {"signal_ids": ["sig-1"]}, "specs": ["spec-1"]})

    assert [gap["type"] for gap in plan["trace_gaps"]] == ["insights", "units", "evaluations"]
    assert any(action["type"] == "close_trace_gaps" for action in plan["handoff_actions"])


def test_evidence_trace_handoff_plan_extracts_assumptions() -> None:
    plan = generate_evidence_trace_handoff_plan({"assumptions": ["API quota remains stable", "API quota remains stable"]})

    assert plan["assumptions"] == [
        {
            "id": "ASM1",
            "assumption": "API quota remains stable",
            "owner": "implementation_owner",
            "status": "unresolved",
        }
    ]
    assert any(action["type"] == "resolve_assumptions" for action in plan["handoff_actions"])
