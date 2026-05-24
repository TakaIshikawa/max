from __future__ import annotations

import json

from max.api.run_input_completeness import run_input_completeness_to_json


def test_run_input_completeness_blocks_missing_required_inputs() -> None:
    parsed = json.loads(
        run_input_completeness_to_json(
            {
                "required_inputs": {"ideate": ["insights", "profiles"], "fetch": ["sources"]},
                "observed_inputs": {"fetch": ["sources"], "ideate": ["profiles"]},
                "missing_reasons": {"ideate.insights": "synthesis not complete"},
            }
        )
    )

    assert [row["stage"] for row in parsed["stages"]] == ["fetch", "ideate"]
    assert parsed["summary"]["ready"] is False
    assert parsed["blocked_stages"] == ["ideate"]
    assert parsed["stages"][1]["missing_required_inputs"] == [{"input": "insights", "reason": "synthesis not complete"}]
    assert parsed["recommended_remediation_actions"][0]["input"] == "insights"


def test_run_input_completeness_optional_missing_warns_only() -> None:
    parsed = json.loads(
        run_input_completeness_to_json(
            {
                "required": {"publication": ["payload"]},
                "observed": {"publication": ["payload"]},
                "optional": {"publication": ["preview"]},
            },
            as_of="2026-05-21T00:00:00Z",
        )
    )

    assert parsed["summary"]["ready"] is True
    assert parsed["warnings"][0]["input"] == "preview"
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"


def test_run_input_completeness_empty_input_is_ready() -> None:
    parsed = json.loads(run_input_completeness_to_json({}))

    assert parsed["summary"]["ready"] is True
    assert parsed["stages"] == []
    assert parsed["blocked_stages"] == []
