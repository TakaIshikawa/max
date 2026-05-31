from __future__ import annotations

import json

from max.exports import generate_llm_prompt_version_adoption_report
from max.exports.llm_prompt_version_adoption_report import render_llm_prompt_version_adoption_report_json, render_llm_prompt_version_adoption_report_markdown


def test_llm_prompt_version_adoption_flags_old_version_traffic() -> None:
    report = generate_llm_prompt_version_adoption_report([{"template": "synth", "current_version": "v3"}], [{"prompt_template": "synth", "version": "v3", "call_count": 7}, {"prompt_template": "synth", "version": "v2", "call_count": 3}], old_version_traffic_threshold=2)

    assert report["rows"][0]["adoption_percent"] == 70.0
    assert report["rows"][0]["old_versions"] == {"v2": 3}
    assert report["summary"]["flagged_template_count"] == 1
    assert "v2=3" in render_llm_prompt_version_adoption_report_markdown(report)
    json.loads(render_llm_prompt_version_adoption_report_json(report))
