"""Focused tests for design brief bundle risk-register exports."""

from __future__ import annotations

from max.analysis import design_brief_bundle
from max.analysis.design_brief_bundle import build_design_brief_bundle, render_design_brief_bundle
from tests.test_design_brief_bundle import _store_with_design_brief


def test_design_brief_bundle_includes_risk_register_json_and_markdown(tmp_path) -> None:
    store, brief_id = _store_with_design_brief(tmp_path)
    try:
        bundle = build_design_brief_bundle(store, brief_id)
    finally:
        store.close()

    assert bundle is not None
    assert bundle["risk_register"] is not None
    assert bundle["risk_register"]["design_brief"]["id"] == brief_id
    assert bundle["risk_register"]["summary"]["risk_count"] > 0
    assert bundle["artifact_status"]["risk_register"] == {"status": "generated"}

    markdown = render_design_brief_bundle(bundle, fmt="markdown")

    assert "## Risk Register" in markdown
    assert "### Risk Register: Bundle Export Brief" in markdown


def test_design_brief_bundle_tracks_unavailable_risk_register(tmp_path, monkeypatch) -> None:
    store, brief_id = _store_with_design_brief(tmp_path)

    def unavailable_risk_register(store, brief_id):
        return None

    monkeypatch.setattr(design_brief_bundle, "build_design_brief_risk_register", unavailable_risk_register)
    try:
        bundle = build_design_brief_bundle(store, brief_id)
    finally:
        store.close()

    assert bundle is not None
    assert bundle["risk_register"] is None
    assert bundle["artifact_status"]["risk_register"] == {"status": "missing"}

    markdown = render_design_brief_bundle(bundle, fmt="markdown")

    assert "## Risk Register" in markdown
    assert "Artifact unavailable. See artifact status above." in markdown
