from __future__ import annotations

import json

from max.api import llm_model_retirement_status_to_json


def test_llm_model_retirement_status_is_deterministic_with_as_of() -> None:
    report = json.loads(
        llm_model_retirement_status_to_json(
            {
                "warning_days": 30,
                "models": [
                    {"model": "retired", "retirement_date": "2026-05-01", "impacted_stages": ["draft"]},
                    {"model": "soon", "retirement_date": "2026-06-10", "fallback_ready": True},
                    {"model": "deprecated", "deprecated": True},
                    {"model": "ok", "retirement_date": "2027-01-01"},
                ],
            },
            as_of="2026-06-01T00:00:00Z",
        )
    )

    assert report["status"] == "critical"
    assert report["summary"]["retired_count"] == 1
    assert report["summary"]["retiring_soon_count"] == 1
    assert report["summary"]["deprecated_count"] == 1
    assert report["models"][0]["days_until_retirement"] == -31
    assert report["models"][0]["impacted_stages"] == ["draft"]
