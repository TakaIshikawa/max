"""Tests for Trello checklist item publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher import (
    TrelloChecklistItemPublisher as ExportedTrelloChecklistItemPublisher,
)
from max.publisher.trello_checklist_items import (
    TrelloChecklistItemPublishError,
    TrelloChecklistItemPublisher,
)


def test_dry_run_returns_intended_request_without_optional_position() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = TrelloChecklistItemPublisher(
        card_id="card-123",
        checklist_id="checklist-123",
        key="trello_key",
        token="trello_token",
        name="Confirm launch gate",
        client=client,
    )

    result = publisher.publish(dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.provider == "trello"
    assert result.card_id == "card-123"
    assert result.checklist_id == "checklist-123"
    assert result.check_item_id is None
    assert result.name == "Confirm launch gate"
    assert result.state == "incomplete"
    assert result.payload["request"] == {
        "method": "POST",
        "url": "https://api.trello.com/1/checklists/checklist-123/checkItems",
        "params": {"key": "trello_key", "token": "trello_token"},
        "json": {"name": "Confirm launch gate", "checked": False},
    }
    assert "pos" not in result.payload
    assert "pos" not in result.payload["request"]["json"]


def test_checked_true_maps_to_trello_checked_parameter_and_complete_state() -> None:
    publisher = TrelloChecklistItemPublisher(
        card_id="card-123",
        checklist_id="checklist-123",
        key="trello_key",
        token="trello_token",
        name="Review compliance checklist",
        checked=True,
        position="top",
    )

    result = publisher.publish(dry_run=True)

    assert result.state == "complete"
    assert result.payload["checked"] is True
    assert result.payload["pos"] == "top"
    assert result.payload["request"]["json"] == {
        "name": "Review compliance checklist",
        "checked": True,
        "pos": "top",
    }


def test_successful_publish_posts_check_item_and_normalizes_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "checkitem-123",
                "name": "Run implementation checklist",
                "state": "complete",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = TrelloChecklistItemPublisher(
        card_id="card-123",
        checklist_id="checklist-123",
        key="trello_key",
        token="trello_token",
        name="Run implementation checklist",
        checked=True,
        position=42,
        client=client,
    )

    result = publisher.publish(dry_run=False)

    assert result.status_code == 200
    assert result.provider == "trello"
    assert result.card_id == "card-123"
    assert result.checklist_id == "checklist-123"
    assert result.check_item_id == "checkitem-123"
    assert result.name == "Run implementation checklist"
    assert result.state == "complete"
    assert requests[0].url == (
        "https://api.trello.com/1/checklists/checklist-123/checkItems?key=trello_key&token=trello_token"
    )
    assert requests[0].headers["User-Agent"] == "max-trello-checklist-items-publisher/1"
    assert _json_from_request(requests[0]) == {
        "name": "Run implementation checklist",
        "checked": True,
        "pos": 42.0,
    }
    assert result.payload["check_item_id"] == "checkitem-123"
    assert result.payload["state"] == "complete"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"card_id": None}, "Trello card_id is required"),
        ({"checklist_id": None}, "Trello checklist_id is required"),
        ({"name": None}, "Trello checklist item name is required"),
        ({"key": None}, "Trello key is required"),
        ({"token": None}, "Trello token is required"),
    ],
)
def test_missing_required_fields_raise_deterministic_validation_errors(
    kwargs: dict[str, str | None],
    message: str,
) -> None:
    values = {
        "card_id": "card-123",
        "checklist_id": "checklist-123",
        "key": "trello_key",
        "token": "trello_token",
        "name": "Validate publish",
    }
    values.update(kwargs)
    publisher = TrelloChecklistItemPublisher(**values)

    with pytest.raises(TrelloChecklistItemPublishError, match=message):
        publisher.publish(dry_run=True)


def test_live_publish_raises_error_with_status_code_on_non_2xx() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(401, json={"message": "bad token=secret"})
        )
    )
    publisher = TrelloChecklistItemPublisher(
        card_id="card-123",
        checklist_id="checklist-123",
        key="trello_key",
        token="trello_token",
        name="Validate publish",
        client=client,
    )

    with pytest.raises(TrelloChecklistItemPublishError, match="HTTP 401") as exc:
        publisher.publish(dry_run=False)

    assert exc.value.status_code == 401
    assert "secret" not in str(exc.value)


def test_exported_from_publisher_package() -> None:
    assert ExportedTrelloChecklistItemPublisher is TrelloChecklistItemPublisher


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
