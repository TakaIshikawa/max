from __future__ import annotations

from max.spec.tokenizer_drift_reconciliation_plan import generate_tokenizer_drift_reconciliation_plan


def test_tokenizer_drift_plan_schema_and_evidence() -> None:
    plan = generate_tokenizer_drift_reconciliation_plan({"evidence": {"signal_ids": ["s1"]}, "metadata": {"tokenizer_drift_reconciliation": {"rows": [{"id": "p1", "old_token_count": 100, "new_token_count": 130}]}}})
    assert plan["schema_version"] == "max.spec.tokenizer_drift_reconciliation_plan.v1"
    assert plan["kind"] == "max.spec.tokenizer_drift_reconciliation_plan"
    assert plan["evidence_references"][0]["reference"] == "signal:s1"


def test_tokenizer_drift_plan_ranks_high_drift_and_tokenizer_changes_first() -> None:
    plan = generate_tokenizer_drift_reconciliation_plan({"tokenizers": [{"id": "low", "old_token_count": 100, "new_token_count": 105, "old_tokenizer": "a", "new_tokenizer": "a"}, {"id": "changed", "old_token_count": 100, "new_token_count": 101, "old_tokenizer": "a", "new_tokenizer": "b"}, {"id": "high", "old_token_count": 100, "new_token_count": 140}]})
    assert [row["prompt_id"] for row in plan["drift_findings"][:2]] == ["high", "changed"]


def test_tokenizer_drift_plan_fallback_is_monitorable() -> None:
    plan = generate_tokenizer_drift_reconciliation_plan(None)
    assert plan["summary"]["status"] == "monitor"
    assert plan["drift_findings"] == []
    assert plan["verification_gates"]
