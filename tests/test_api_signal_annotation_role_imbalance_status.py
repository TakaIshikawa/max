from __future__ import annotations

import json

from max.api import signal_annotation_role_imbalance_status_to_json


def test_balanced_roles_are_ok() -> None:
    report = json.loads(signal_annotation_role_imbalance_status_to_json({"annotations": [{"source": "s", "role": "problem"}, {"source": "s", "role": "solution"}, {"source": "s", "role": "market"}]}))
    assert report["role_rows"][0]["status"] == "ok"


def test_single_role_dominance_is_critical_for_missing_roles() -> None:
    report = json.loads(signal_annotation_role_imbalance_status_to_json({"rows": [{"source": "s", "role": "problem"}, {"source": "s", "role": "problem"}]}))
    assert report["role_rows"][0]["status"] == "critical"


def test_missing_roles_are_listed() -> None:
    report = json.loads(signal_annotation_role_imbalance_status_to_json({"items": [{"source": "s", "role": "problem"}, {"source": "s", "role": "solution"}]}))
    assert report["role_rows"][0]["missing_roles"] == ["market"]


def test_unknown_roles_are_counted() -> None:
    report = json.loads(signal_annotation_role_imbalance_status_to_json({"items": [{"source": "s", "role": "problem"}, {"source": "s", "role": "solution"}, {"source": "s", "role": "market"}, {"source": "s", "role": "other"}]}))
    assert report["role_rows"][0]["unknown_role_count"] == 1


def test_empty_annotations_return_empty_rows() -> None:
    report = json.loads(signal_annotation_role_imbalance_status_to_json({}))
    assert report["role_rows"] == []
