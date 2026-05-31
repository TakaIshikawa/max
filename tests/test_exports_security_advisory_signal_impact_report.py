from __future__ import annotations

import json

from max.exports import generate_security_advisory_signal_impact_report
from max.exports.security_advisory_signal_impact_report import render_security_advisory_signal_impact_report_json, render_security_advisory_signal_impact_report_markdown


def test_security_advisory_signal_impact_matches_dependencies_and_tracks_unmatched() -> None:
    report = generate_security_advisory_signal_impact_report([{"id": "CVE-1", "package": "openssl", "severity": "critical"}, {"id": "CVE-2", "package": "unused", "severity": "high"}], [{"id": "spec-1", "profile": "prod", "dependencies": ["openssl", "django"]}])

    assert report["rows"][0]["affected_artifact_ids"] == ["spec-1"]
    assert report["rows"][0]["recommended_disposition"] == "Patch or quarantine affected artifacts."
    assert report["summary"]["unmatched_advisory_count"] == 1
    assert "CVE-2 / unused: unmatched" in render_security_advisory_signal_impact_report_markdown(report)
    json.loads(render_security_advisory_signal_impact_report_json(report))
