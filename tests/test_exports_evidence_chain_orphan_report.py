from __future__ import annotations

import json

from max.exports import generate_evidence_chain_orphan_report
from max.exports.evidence_chain_orphan_report import render_evidence_chain_orphan_report_json, render_evidence_chain_orphan_report_markdown


def test_evidence_chain_orphan_report_finds_missing_upstream_and_terminal_orphans() -> None:
    report = generate_evidence_chain_orphan_report([{"id": "insight-1", "artifact_type": "insight", "profile": "p", "upstream_ids": ["signal-missing"], "downstream_ids": ["spec-1"]}, {"id": "spec-1", "artifact_type": "spec", "profile": "p", "upstream_ids": ["insight-1"], "downstream_ids": []}])

    assert report["summary"]["orphan_count"] == 2
    assert report["summary"]["missing_upstream_reference_count"] == 1
    assert report["summary"]["terminal_orphan_count"] == 1
    assert report["rows"][0]["severity"] == "critical"
    assert "signal-missing" in render_evidence_chain_orphan_report_markdown(report)
    json.loads(render_evidence_chain_orphan_report_json(report))
