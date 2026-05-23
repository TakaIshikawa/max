from max.spec import generate_ai_safety_evaluation_exception_plan


def test_ai_safety_exception_plan_uses_custom_metadata():
    plan = generate_ai_safety_evaluation_exception_plan(
        {"metadata": {"ai_safety_evaluation_exception": {"evaluation_items": [{"model": "classifier-v2", "feature": "triage"}], "rollback_triggers": ["harmful output spike"]}}}
    )

    assert plan["evaluation_items"][0]["name"] == "classifier-v2"
    assert plan["evaluation_items"][0]["feature"] == "triage"
    assert plan["rollback_triggers"][0]["name"] == "harmful output spike"


def test_ai_safety_exception_plan_defaults_are_conservative():
    plan = generate_ai_safety_evaluation_exception_plan({})

    assert plan["safety_controls"]
    assert "conservative safety review" in plan["safety_controls"][0]["description"]
    assert "rollback" in plan["rollback_triggers"][0]["description"]
