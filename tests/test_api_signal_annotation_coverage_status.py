from __future__ import annotations

import json

from max.api import signal_annotation_coverage_status_to_json


def test_signal_annotation_coverage_status_full_coverage() -> None:
    report = json.loads(signal_annotation_coverage_status_to_json({"signals": [{"id": "s1", "source": "crm", "annotations": [{"role": "owner"}]}]}))
    assert report["summary"]["status"] == "healthy"
    assert report["summary"]["coverage"] == 1.0


def test_signal_annotation_coverage_status_partial_per_source() -> None:
    report = json.loads(signal_annotation_coverage_status_to_json({"warning_min_coverage": 0.8, "signals": [{"source": "crm", "role": "owner"}, {"source": "crm"}, {"source": "docs", "role": "reviewer"}]}))
    assert report["summary"]["status"] == "warning"
    assert report["sources"][0]["source"] == "crm"
    assert report["sources"][0]["coverage"] == 0.5


def test_signal_annotation_coverage_status_invalid_role_handling() -> None:
    report = json.loads(signal_annotation_coverage_status_to_json({"signals": [{"id": "s1", "role": "bad"}]}))
    assert report["summary"]["invalid_role_count"] == 1
    assert report["summary"]["status"] == "critical"


def test_signal_annotation_coverage_status_empty_input() -> None:
    report = json.loads(signal_annotation_coverage_status_to_json({}))
    assert report["summary"]["status"] == "healthy"
    assert report["summary"]["coverage"] == 1.0
