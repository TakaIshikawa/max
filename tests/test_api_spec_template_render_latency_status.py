from __future__ import annotations

import json

from max.api.spec_template_render_latency_status import spec_template_render_latency_status_to_json


def test_spec_template_render_latency_status_thresholds_and_zero_counts() -> None:
    parsed = json.loads(
        spec_template_render_latency_status_to_json(
            {
                "templates": [
                    {"template": "ok", "render_count": 100, "p95_ms": 100, "failure_count": 0},
                    {"template": "slow", "render_count": 100, "p95_ms": 1500, "failure_count": 0},
                    {"template": "failing", "render_count": 100, "p95_ms": 100, "failure_count": 10},
                    {"template": "zero", "render_count": 0, "failure_count": 0},
                ]
            },
            warning_p95_ms=1000,
            critical_p95_ms=3000,
            warning_failure_rate=0.01,
            critical_failure_rate=0.05,
        )
    )

    assert [row["template"] for row in parsed["templates"]] == ["failing", "slow", "ok", "zero"]
    assert parsed["templates"][0]["failure_rate"] == 0.1
    assert parsed["templates"][-1]["failure_rate"] == 0.0
    assert parsed["summary"]["failing_template_count"] == 1
    assert parsed["summary"]["slow_template_count"] == 1
