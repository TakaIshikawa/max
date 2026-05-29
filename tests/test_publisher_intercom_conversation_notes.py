from __future__ import annotations

import httpx
import pytest

from max.publisher.intercom_conversation_notes import IntercomConversationNotePublishError, IntercomConversationNotePublisher
from tests.test_zoom_team_chat_messages_publisher import _spec


def test_missing_conversation_or_empty_note_is_rejected() -> None:
    with pytest.raises(IntercomConversationNotePublishError):
        IntercomConversationNotePublisher().publish(_spec())


def test_admin_metadata_is_included_when_provided_by_spec_and_dry_run() -> None:
    result = IntercomConversationNotePublisher(conversation_id="c1").publish(_spec())
    assert result.payload["type"] == "admin"
    assert result.payload["message_type"] == "note"
    assert result.payload["metadata"]["idea_id"] == "bu-zoom001"


def test_api_failure_is_redacted() -> None:
    publisher = IntercomConversationNotePublisher(conversation_id="c1", access_token="tok", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401, text="bad tok"))))
    with pytest.raises(IntercomConversationNotePublishError) as exc:
        publisher.publish(_spec(), dry_run=False)
    assert "tok" not in str(exc.value)
