"""Tests for profile gap matrix REST exports."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = str(tmp_path / "test_profile_gap_matrix_api.db")
    Store(db_path=path, wal_mode=True).close()
    return path


@pytest.fixture
def client(db_path: str) -> TestClient:
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


@pytest.fixture
def profiles_dir(tmp_path: Path) -> Path:
    path = tmp_path / "profiles"
    path.mkdir()
    _write_profile(
        path,
        "devtools",
        sources=[
            {"adapter": "hackernews", "enabled": True, "watchlist": ["mcp"]},
            {"adapter": "github_issues", "enabled": False, "watchlist": ["bugs"]},
            {"adapter": "ghost_adapter", "enabled": True, "watchlist": ["unknown"]},
        ],
        custom_weights={
            "pain_severity": 0.40,
            "addressable_scale": 0.20,
            "build_effort": 0.20,
            "composability": 0.10,
            "competitive_density": 0.05,
            "timing_fit": 0.05,
        },
    )
    _write_profile(
        path,
        "security",
        sources=[
            {"adapter": "security_advisories", "enabled": True},
            {"adapter": "reddit", "enabled": False, "watchlist": ["supply chain"]},
        ],
    )
    (path / "schema.yaml").write_text("type: object\n", encoding="utf-8")
    return path


@pytest.fixture
def adapter_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = {
        "hackernews": SimpleNamespace(source_categories=["forum"], description="Forum posts."),
        "github_issues": SimpleNamespace(
            source_categories=["code_hosting"],
            description="Code hosting issue threads.",
        ),
        "security_advisories": SimpleNamespace(
            source_categories=["security_feed"],
            description="Security advisory feeds.",
        ),
        "reddit": SimpleNamespace(source_categories=["forum"], description="Forum posts."),
        "product_hunt": SimpleNamespace(
            source_categories=["marketplace"],
            description="Product marketplace launches.",
        ),
    }
    monkeypatch.setattr(
        "max.analysis.profile_gap_matrix.get_adapter_metadata",
        lambda: metadata,
    )


def _write_profile(
    profiles_dir: Path,
    name: str,
    *,
    sources: list[dict],
    custom_weights: dict[str, float] | None = None,
) -> None:
    evaluation: dict[str, object] = {"weight_profile": "default"}
    if custom_weights is not None:
        evaluation = {"weight_profile": "custom", "custom_weights": custom_weights}
    payload = {
        "name": name,
        "domain": {
            "name": f"{name}-domain",
            "description": f"{name} test domain",
            "categories": ["workflow automation"],
            "target_user_types": ["developers"],
        },
        "sources": sources,
        "evaluation": evaluation,
    }
    (profiles_dir / f"{name}.yaml").write_text(
        yaml.safe_dump(payload),
        encoding="utf-8",
    )


def test_get_profile_gap_matrix_returns_structured_rows(
    client: TestClient,
    profiles_dir: Path,
    adapter_metadata: None,
) -> None:
    response = client.get(
        "/api/v1/profiles/gap-matrix",
        params={"profile_dir": str(profiles_dir), "min_signals": 1, "max_age_days": 30},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["profiles_dir"] == str(profiles_dir)
    assert data["profile_count"] == 2
    assert data["row_count"] == 2
    assert data["required_source_categories"] == [
        "code_hosting",
        "forum",
        "marketplace",
        "security_feed",
    ]

    rows = {row["profile_name"]: row for row in data["rows"]}
    assert rows["devtools"]["status"] == "action_required"
    assert rows["devtools"]["unknown_adapters"] == ["ghost_adapter"]
    assert rows["devtools"]["recommended_next_adapters"] == [
        "github_issues",
        "product_hunt",
        "security_advisories",
    ]
    assert rows["security"]["status"] == "gaps"
    assert rows["security"]["disabled_relevant_adapters"] == ["reddit"]


def test_get_profile_gap_matrix_markdown_download(
    client: TestClient,
    profiles_dir: Path,
    adapter_metadata: None,
) -> None:
    response = client.get(
        "/api/v1/profiles/gap-matrix.md",
        params={"profile_dir": str(profiles_dir)},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        'attachment; filename="profile-gap-matrix.md"'
    )
    assert response.text.startswith("# Profile Gap Matrix")
    assert "Profiles: 2" in response.text
    assert "| devtools | devtools-domain | action_required |" in response.text


def test_get_profile_gap_matrix_missing_profile_dir_returns_400(
    client: TestClient,
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing-profiles"

    response = client.get(
        "/api/v1/profiles/gap-matrix",
        params={"profile_dir": str(missing)},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == f"Profile directory not found: {missing}"


def test_get_profile_gap_matrix_rejects_invalid_query_parameters(
    client: TestClient,
    profiles_dir: Path,
) -> None:
    invalid_min_signals = client.get(
        "/api/v1/profiles/gap-matrix",
        params={"profile_dir": str(profiles_dir), "min_signals": 0},
    )
    invalid_max_age = client.get(
        "/api/v1/profiles/gap-matrix.md",
        params={"profile_dir": str(profiles_dir), "max_age_days": 0},
    )

    assert invalid_min_signals.status_code == 422
    assert invalid_max_age.status_code == 422
