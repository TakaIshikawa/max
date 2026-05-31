from __future__ import annotations

from max.spec import generate_feedback_quality_remediation_plan
from max.spec.feedback_quality_remediation_plan import KIND, SCHEMA_VERSION


def test_feedback_quality_remediation_plan_covers_full_quality_workflow() -> None:
    plan = generate_feedback_quality_remediation_plan(
        {
            "project": {"title": "Feedback Scoring"},
            "metadata": {
                "feedback_quality_remediation": {
                    "label_confusion_pairs": [
                        {"from": "approved", "to": "accepted", "count": 12},
                        {"from": "rejected", "to": "needs_review", "count": 19},
                    ],
                    "missing_reason_counts": {"no_comment": 7, "empty_reason": 11},
                    "taxonomy_cleanup": ["merge accepted into approved"],
                    "reviewer_calibration": ["calibrate reviewers on approved and needs_review examples"],
                    "sampling_plan": ["sample 10% by label and reviewer"],
                    "data_correction_workflow": ["backfill corrected labels through immutable correction jobs"],
                    "monitoring_metrics": ["track confusion and missing reason rates daily"],
                    "acceptance_metrics": [
                        {"name": "label confusion rate", "operator": "<=", "target": "2%"},
                        {"name": "reviewer agreement", "operator": ">=", "target": "92%"},
                    ],
                    "rollout_phases": ["audit", "pilot", "backfill", "monitor"],
                    "stop_go_criteria": ["go when high severity defects are zero"],
                }
            },
            "evidence": {"signal_ids": ["fq-1"]},
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert list(plan) == [
        "schema_version",
        "kind",
        "source",
        "title",
        "summary",
        "label_audit",
        "taxonomy_cleanup",
        "reviewer_calibration",
        "sampling_plan",
        "data_correction_workflow",
        "monitoring_metrics",
        "acceptance_metrics",
        "rollout_phases",
        "stop_go_criteria",
        "evidence_references",
    ]
    assert plan["summary"]["label_confusion_pair_count"] == 2
    assert [item["name"] for item in plan["label_audit"][:2]] == [
        "rejected -> needs_review",
        "approved -> accepted",
    ]
    assert plan["label_audit"][2]["name"] == "empty_reason"
    assert plan["taxonomy_cleanup"][0]["name"] == "merge accepted into approved"
    assert plan["reviewer_calibration"][0]["name"] == "calibrate reviewers on approved and needs_review examples"
    assert plan["data_correction_workflow"][0]["owner"] == "data_owner"
    assert plan["monitoring_metrics"][0]["name"] == "track confusion and missing reason rates daily"
    assert [item["name"] for item in plan["acceptance_metrics"]] == ["label confusion rate", "reviewer agreement"]
    assert plan["rollout_phases"][0]["name"] == "audit"
    assert plan["stop_go_criteria"][0]["name"] == "go when high severity defects are zero"


def test_feedback_quality_remediation_plan_sparse_input_uses_defaults() -> None:
    plan = generate_feedback_quality_remediation_plan({})

    assert plan["summary"]["label_confusion_pair_count"] == 0
    assert plan["label_audit"][0]["type"] == "baseline_audit"
    assert plan["taxonomy_cleanup"]
    assert plan["reviewer_calibration"]
    assert plan["sampling_plan"]
    assert plan["data_correction_workflow"]
    assert plan["monitoring_metrics"]
    assert [item["name"] for item in plan["acceptance_metrics"]] == [
        "label confusion rate",
        "missing feedback reason rate",
        "reviewer agreement",
    ]
    assert plan["rollout_phases"]
    assert plan["stop_go_criteria"]
