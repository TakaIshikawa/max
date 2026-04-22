from __future__ import annotations

from pathlib import Path

import yaml

from max.profiles.validation import validate_profile_file


def _write_schema(profiles_dir: Path) -> dict:
    schema = {
        "type": "object",
        "required": ["name", "domain"],
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "domain": {
                "type": "object",
                "required": ["name", "description", "categories", "target_user_types"],
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "categories": {"type": "array", "items": {"type": "string"}},
                    "target_user_types": {"type": "array", "items": {"type": "string"}},
                },
            },
            "sources": {"type": "array"},
            "evaluation": {"type": "object"},
        },
    }
    (profiles_dir / "schema.yaml").write_text(yaml.safe_dump(schema))
    return schema


def test_validate_profile_file_reports_structured_warnings(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    schema = _write_schema(profiles_dir)
    profile_path = profiles_dir / "devtools.yaml"
    profile_path.write_text(
        yaml.safe_dump(
            {
                "name": "devtools",
                "domain": {
                    "name": "developer-tools",
                    "description": "Developer tools",
                    "categories": ["cli_tool", "cli_tool"],
                    "target_user_types": ["developers"],
                },
                "sources": [{"adapter": "hackernews"}],
                "evaluation": {
                    "custom_weights": {
                        "pain_severity": 0.5,
                        "not_a_dimension": 0.5,
                    }
                },
            }
        )
    )

    result = validate_profile_file(profile_path, schema=schema, profiles_dir=profiles_dir)

    assert not result.ok
    assert any(issue.code == "duplicate_category" for issue in result.warning_issues)
    assert any(issue.code == "unknown_weight_dimension" for issue in result.error_issues)
    assert all(issue.severity in {"error", "warning"} for issue in result.error_issues + result.warning_issues)


def test_validate_profile_file_warns_for_missing_optional_file_reference(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    schema = _write_schema(profiles_dir)
    profile_path = profiles_dir / "rss.yaml"
    profile_path.write_text(
        yaml.safe_dump(
            {
                "name": "rss",
                "domain": {
                    "name": "developer-tools",
                    "description": "Developer tools",
                    "categories": ["cli_tool"],
                    "target_user_types": ["developers"],
                },
                "sources": [
                    {
                        "adapter": "rss_feed",
                        "params": {
                            "feeds": ["https://example.com/feed.xml"],
                            "prompt_file": "missing-prompt.md",
                        },
                    }
                ],
            }
        )
    )

    result = validate_profile_file(profile_path, schema=schema, profiles_dir=profiles_dir)

    assert result.ok
    assert any(issue.code == "unreachable_file_reference" for issue in result.warning_issues)
    assert "missing-prompt.md" in result.warnings[0]
