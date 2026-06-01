from __future__ import annotations

import json

from max.api import signal_ingestion_error_spike_status_to_json


def test_signal_ingestion_error_spike_status_healthy() -> None:
    report = json.loads(signal_ingestion_error_spike_status_to_json({"sources": [{"source": "crm", "errors": 4, "baseline_errors": 3, "affected_signals": 20}]}))

    assert report["summary"]["status"] == "healthy"
    assert report["summary"]["total_errors"] == 4
    assert report["spiking_sources"] == []


def test_signal_ingestion_error_spike_status_warning() -> None:
    report = json.loads(signal_ingestion_error_spike_status_to_json({"warning_ratio": 2, "critical_ratio": 5, "sources": [{"source": "tickets", "errors": 8, "baseline_errors": 3, "affected_signals": 40}]}))

    assert report["summary"]["status"] == "warning"
    assert report["worst_source"]["source"] == "tickets"
    assert report["worst_source"]["spike_ratio"] == 2.6667


def test_signal_ingestion_error_spike_status_critical_zero_baseline() -> None:
    report = json.loads(signal_ingestion_error_spike_status_to_json({"zero_baseline_critical_errors": 5, "sources": [{"source": "reviews", "errors": 5, "baseline_errors": 0}]}))

    assert report["summary"]["status"] == "critical"
    assert report["worst_source"]["spike_ratio"] == 5.0


def test_signal_ingestion_error_spike_status_empty_input() -> None:
    report = json.loads(signal_ingestion_error_spike_status_to_json({}))

    assert report["summary"]["status"] == "healthy"
    assert report["summary"]["total_baseline_errors"] == 0
    assert report["worst_source"] is None
