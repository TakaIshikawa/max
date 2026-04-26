"""Compatibility tests for Trello card publisher API options."""

from __future__ import annotations

import json

import httpx

from max.publisher.trello_cards import TrelloCardPublisher


def test_live_publish_posts_member_ids_and_position() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "card-123", "url": "https://trello.com/c/card123"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = TrelloCardPublisher(
        "list-123",
        key="trello_key",
        token="trello_token",
        labels=["label-1"],
        member_ids=["member-1", "member-2"],
        position="top",
        client=client,
    )

    result = publisher.publish(
        {
            "schema_version": "max.design_brief.trello_card.v1",
            "kind": "max.design_brief",
            "source": {
                "system": "max",
                "type": "design_brief",
                "design_brief_id": "dbf-123",
                "domain": "devtools",
                "theme": "handoff",
                "status": "ready",
                "readiness_score": 90.0,
                "lead_idea_id": "bu-123",
            },
            "project": {
                "title": "Trello Design Brief",
                "summary": "Create a Trello card from a design brief.",
                "why_this_now": "Execution needs a lightweight handoff.",
            },
            "execution": {
                "mvp_scope": ["Publish card"],
                "first_milestones": ["Ship endpoint"],
                "validation_plan": "Create one card.",
            },
            "evidence": {"source_idea_ids": ["bu-123"]},
            "readiness": {"score": 90.0},
        },
        dry_run=False,
    )

    posted = json.loads(requests[0].read())
    assert posted["idMembers"] == "member-1,member-2"
    assert posted["pos"] == "top"
    assert posted["idLabels"]
    assert result.payload["member_ids"] == ["member-1", "member-2"]
    assert result.payload["pos"] == "top"
    assert result.payload["metadata"]["design_brief_id"] == "dbf-123"
