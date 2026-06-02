from __future__ import annotations

import pytest

from max.spec.synthetic_signal_poisoning_response_plan import generate_synthetic_signal_poisoning_response_plan


def test_synthetic_signal_poisoning_response_sorts_signals_and_checks_downstream() -> None:
    plan = generate_synthetic_signal_poisoning_response_plan(
        {
            "metadata": {
                "synthetic_signal_poisoning_response": {
                    "source": "synthetic-fixtures",
                    "poisoning_indicator": "label inversion",
                    "affected_signal_ids": ["sig-9", "sig-1", "sig-9"],
                    "detected_at": "2026-06-01T11:00:00Z",
                    "owner": "data_quality_owner",
                }
            }
        }
    )

    assert [item["signal_id"] for item in plan["affected_signals"]] == ["sig-1", "sig-9"]
    assert [item["artifact"] for item in plan["downstream_impact"]] == ["insights", "units", "generated_specs"]


def test_synthetic_signal_poisoning_response_validates_required_fields() -> None:
    with pytest.raises(ValueError, match="affected_signal_ids"):
        generate_synthetic_signal_poisoning_response_plan({"metadata": {"synthetic_signal_poisoning_response": {"source": "fixtures"}}})
