"""Compatibility tests for the Freshdesk integration path."""

from __future__ import annotations

from max.publisher.freshdesk_tickets import FreshdeskTicketPublisher


def test_freshdesk_ticket_publisher_adapter_path_is_available() -> None:
    publisher = FreshdeskTicketPublisher(domain="example", api_key="freshdesk_key")

    assert publisher.domain == "example.freshdesk.com"
    assert publisher.api_key == "freshdesk_key"
