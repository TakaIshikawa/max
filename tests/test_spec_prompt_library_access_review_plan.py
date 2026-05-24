from __future__ import annotations

import json

from max.spec.prompt_library_access_review_plan import (
    generate_prompt_library_access_review_plan,
)


def test_prompt_library_access_review_plan_covers_read_only_access() -> None:
    plan = generate_prompt_library_access_review_plan(
        {
            "metadata": {
                "prompt_library_access_review": {
                    "subjects": [{"user": "analyst", "permission": "read"}],
                    "permissions": ["read"],
                }
            }
        }
    )

    assert plan["access_subjects"][0]["user"] == "analyst"
    assert plan["access_subjects"][0]["permission"] == "read"
    assert plan["permission_levels"][0]["name"] == "read"


def test_prompt_library_access_review_plan_flags_broad_write_access() -> None:
    plan = generate_prompt_library_access_review_plan(
        {
            "metadata": {
                "prompt_library_access_review": {
                    "access_subjects": [{"group": "all engineers", "permission": "write"}],
                }
            }
        }
    )

    assert plan["risks"][0]["name"] == "broad prompt library write access"
    assert plan["revocation_actions"][0]["name"] == "reduce broad write access to least-privilege maintainers"


def test_prompt_library_access_review_plan_flags_stale_users() -> None:
    plan = generate_prompt_library_access_review_plan(
        {
            "metadata": {
                "prompt_library_access_review": {
                    "users": [{"user": "former-contractor", "permission": "read", "status": "stale"}],
                }
            }
        }
    )

    assert plan["risks"][0]["name"] == "stale prompt library access"
    assert plan["revocation_actions"][0]["name"] == "remove stale or inactive prompt library subject access"


def test_prompt_library_access_review_plan_includes_sensitive_categories() -> None:
    plan = generate_prompt_library_access_review_plan(
        {
            "metadata": {
                "prompt_library_access_review": {
                    "sensitive_categories": ["system prompts", "regulated workflow prompts"],
                }
            }
        }
    )

    assert [row["name"] for row in plan["sensitive_prompt_categories"]] == [
        "regulated workflow prompts",
        "system prompts",
    ]


def test_prompt_library_access_review_plan_is_deterministic_and_preserves_metadata() -> None:
    payload = {
        "source": {"idea_id": "pla-1"},
        "metadata": {
            "prompt_library_access_review": {
                "subjects": [{"user": "z"}, {"user": "a"}, {"user": "a"}],
                "evidence": ["IAM export"],
            }
        },
    }

    first = generate_prompt_library_access_review_plan(payload)
    assert first == generate_prompt_library_access_review_plan(payload)
    assert [row["name"] for row in first["access_subjects"]] == ["a", "z"]
    assert first["source"]["idea_id"] == "pla-1"
    assert json.loads(json.dumps(first)) == first
