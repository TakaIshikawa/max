from __future__ import annotations

import json

from max.spec.release_artifact_signoff_plan import generate_release_artifact_signoff_plan


def test_release_artifact_signoff_plan_rich_input() -> None:
    report = generate_release_artifact_signoff_plan(_brief())

    assert report == generate_release_artifact_signoff_plan(_brief())
    assert json.loads(json.dumps(report)) == report
    assert [row["artifact"] for row in report["artifacts"]] == ["api-image", "worker-image"]
    assert report["summary"] == {"signed_count": 1, "pending_count": 1, "blocked_count": 0}
    assert report["signoff_status"] == "pending"
    assert report["blockers"] == []


def test_release_artifact_signoff_plan_flags_required_blockers() -> None:
    report = generate_release_artifact_signoff_plan({"artifacts": [{"artifact": "api-image", "required": "true"}]})

    assert [row["blocker"] for row in report["blockers"]] == [
        "missing approvers",
        "missing provenance",
        "unsigned required artifact",
    ]
    assert report["signoff_status"] == "blocked"


def _brief() -> dict:
    return {
        "release_artifact_signoff": {
            "artifacts": [
                {"artifact": "worker-image", "required": "false"},
                {"artifact": "api-image", "signed": "true", "checksum": "sha256:abc", "build_provenance": "slsa://api"},
            ],
            "approvers": [{"approver": "Release manager"}],
            "provenance_evidence": [{"evidence": "slsa://api"}],
            "publication_destinations": [{"destination": "registry"}],
        }
    }
