from max.spec import generate_data_subject_access_request_exception_plan


def test_dsar_exception_plan_uses_metadata_hints():
    plan = generate_data_subject_access_request_exception_plan(
        {"metadata": {"data_subject_access_request_exception": {"request_scope": [{"requester": "Case 42"}], "data_categories": ["billing profile"], "controls": ["identity recheck"]}}}
    )

    assert plan["schema_version"] == "max.spec.data_subject_access_request_exception_plan.v1"
    assert plan["kind"] == "max.spec.data_subject_access_request_exception_plan"
    assert plan["request_scope"][0]["name"] == "Case 42"
    assert plan["affected_data_categories"][0]["name"] == "billing profile"
    assert plan["compensating_controls"][0]["name"] == "identity recheck"


def test_dsar_exception_plan_defaults_include_category_and_reviewer_path():
    plan = generate_data_subject_access_request_exception_plan({})

    assert plan["affected_data_categories"]
    assert "privacy owner and legal reviewer path" in plan["legal_privacy_review"][0]["description"]
