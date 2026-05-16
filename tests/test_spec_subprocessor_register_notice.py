from __future__ import annotations

from max.spec.subprocessor_register import generate_subprocessor_register


def test_subprocessor_register_includes_required_register_fields() -> None:
    register = generate_subprocessor_register(
        {
            "project": {"title": "Support Desk"},
            "solution": {"suggested_stack": {"messaging": "Slack"}},
        }
    )

    row = register["subprocessors"][0]
    assert row["processing_purpose"]
    assert row["data_categories"]
    assert row["regions"]
    assert row["safeguards"]
    assert row["contract_status"] == "needs_review"
    assert row["notice_requirements"] in {"standard register notice", "advance customer notice before use"}
    assert row["review_date"]
    assert register["risk_notes"]


def test_subprocessor_register_cross_border_sensitive_data_strengthens_safeguards_and_notice() -> None:
    register = generate_subprocessor_register(
        {
            "project": {"title": "EU Customer Assistant"},
            "solution": {
                "technical_approach": (
                    "OpenAI processes EU customer personal data in a cross-border GDPR workflow."
                )
            },
        }
    )

    row = next(item for item in register["subprocessors"] if item["vendor_id"] == "openai")
    assert row["risk_level"] == "high"
    assert row["regions"] == "cross-border or unknown"
    assert "SCCs" in row["safeguards"]
    assert row["notice_requirements"] == "advance customer notice before use"
    assert any("Cross-border processing" in note for note in register["risk_notes"])
