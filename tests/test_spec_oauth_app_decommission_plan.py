from max.spec import generate_oauth_app_decommission_plan


def test_oauth_app_decommission_plan_uses_app_metadata():
    plan = generate_oauth_app_decommission_plan(
        {"metadata": {"oauth_app_decommission": {"app_inventory": [{"app": "Legacy CRM", "client_id": "abc"}], "dependent_integrations": ["CRM sync"]}}}
    )

    assert plan["app_inventory"][0]["name"] == "Legacy CRM"
    assert plan["app_inventory"][0]["client_id"] == "abc"
    assert plan["dependency_review"][0]["name"] == "CRM sync"


def test_oauth_app_decommission_plan_defaults_scope_and_revocation_checklists():
    plan = generate_oauth_app_decommission_plan({})

    assert "least-privilege scope review" in plan["scope_review"][0]["description"]
    assert "revocation checklist" in plan["token_revocation"][0]["description"]
