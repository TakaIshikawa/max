"""Tests for centralized notification manager."""

from __future__ import annotations

from typing import Any

import pytest

from max.notifications.notification_manager import (
    NotificationChannel,
    NotificationManager,
    Subscription,
)


class MockChannel:
    """Mock notification channel for testing."""

    def __init__(self, should_succeed: bool = True) -> None:
        self.should_succeed = should_succeed
        self.sent_events: list[dict[str, Any]] = []

    def send(self, event: dict[str, Any]) -> bool:
        """Record the event and return success/failure."""
        self.sent_events.append(event)
        return self.should_succeed


class FailingChannel:
    """Mock channel that raises exceptions."""

    def send(self, event: dict[str, Any]) -> bool:
        """Always raise an exception."""
        raise RuntimeError("Channel error")


def test_register_and_unregister_channels() -> None:
    """Should register and unregister notification channels."""
    manager = NotificationManager()
    channel = MockChannel()

    manager.register_channel("slack", channel)
    assert "slack" in manager._channels

    manager.unregister_channel("slack")
    assert "slack" not in manager._channels


def test_subscribe_creates_subscription() -> None:
    """Should create subscription for user and channel."""
    manager = NotificationManager()

    subscription = manager.subscribe(
        "user123",
        "email",
        {"spec.created", "spec.approved"},
    )

    assert subscription.user_id == "user123"
    assert subscription.channel_type == "email"
    assert subscription.event_types == {"spec.created", "spec.approved"}
    assert subscription.enabled is True


def test_subscribe_with_empty_event_types_subscribes_to_all() -> None:
    """Empty event_types set should subscribe to all events."""
    manager = NotificationManager()

    subscription = manager.subscribe("user123", "webhook", set())

    assert subscription.is_subscribed_to("spec.created")
    assert subscription.is_subscribed_to("spec.approved")
    assert subscription.is_subscribed_to("any.event.type")


def test_unsubscribe_disables_subscription() -> None:
    """Should disable subscription when unsubscribing from all events."""
    manager = NotificationManager()
    manager.subscribe("user123", "slack", {"spec.created"})

    manager.unsubscribe("user123", "slack")

    subscriptions = manager.get_subscriptions("user123", "slack")
    assert len(subscriptions) == 1
    assert subscriptions[0].enabled is False


def test_unsubscribe_removes_specific_event_type() -> None:
    """Should remove specific event type from subscription."""
    manager = NotificationManager()
    subscription = manager.subscribe(
        "user123",
        "email",
        {"spec.created", "spec.approved", "spec.rejected"},
    )

    manager.unsubscribe("user123", "email", "spec.approved")

    assert "spec.created" in subscription.event_types
    assert "spec.approved" not in subscription.event_types
    assert "spec.rejected" in subscription.event_types
    assert subscription.enabled is True


def test_get_subscriptions_filters_by_user() -> None:
    """Should filter subscriptions by user ID."""
    manager = NotificationManager()
    manager.subscribe("user123", "slack", {"spec.created"})
    manager.subscribe("user456", "email", {"spec.approved"})
    manager.subscribe("user123", "webhook", set())

    user123_subs = manager.get_subscriptions(user_id="user123")

    assert len(user123_subs) == 2
    assert all(s.user_id == "user123" for s in user123_subs)


def test_get_subscriptions_filters_by_channel() -> None:
    """Should filter subscriptions by channel type."""
    manager = NotificationManager()
    manager.subscribe("user123", "slack", {"spec.created"})
    manager.subscribe("user456", "slack", {"spec.approved"})
    manager.subscribe("user789", "email", set())

    slack_subs = manager.get_subscriptions(channel_type="slack")

    assert len(slack_subs) == 2
    assert all(s.channel_type == "slack" for s in slack_subs)


def test_get_subscriptions_filters_by_user_and_channel() -> None:
    """Should filter by both user and channel."""
    manager = NotificationManager()
    manager.subscribe("user123", "slack", {"spec.created"})
    manager.subscribe("user123", "email", {"spec.approved"})
    manager.subscribe("user456", "slack", set())

    subs = manager.get_subscriptions(user_id="user123", channel_type="slack")

    assert len(subs) == 1
    assert subs[0].user_id == "user123"
    assert subs[0].channel_type == "slack"


def test_notify_routes_to_subscribed_channels() -> None:
    """Should route notifications to all subscribed channels."""
    manager = NotificationManager()
    slack_channel = MockChannel()
    webhook_channel = MockChannel()

    manager.register_channel("slack", slack_channel)
    manager.register_channel("webhook", webhook_channel)

    manager.subscribe("user123", "slack", {"spec.created"})
    manager.subscribe("user123", "webhook", {"spec.created"})

    event = {
        "event_type": "spec.created",
        "user_id": "user123",
        "data": {"spec_id": "spec-001"},
    }

    result = manager.notify(event)

    assert result.event_type == "spec.created"
    assert result.total_channels == 2
    assert result.successful_channels == 2
    assert result.failed_channels == 0
    assert len(slack_channel.sent_events) == 1
    assert len(webhook_channel.sent_events) == 1


def test_notify_filters_by_event_type() -> None:
    """Should only notify channels subscribed to specific event type."""
    manager = NotificationManager()
    slack_channel = MockChannel()
    email_channel = MockChannel()

    manager.register_channel("slack", slack_channel)
    manager.register_channel("email", email_channel)

    manager.subscribe("user123", "slack", {"spec.created"})
    manager.subscribe("user123", "email", {"spec.approved"})

    event = {
        "event_type": "spec.created",
        "user_id": "user123",
        "data": {},
    }

    result = manager.notify(event)

    assert result.total_channels == 1
    assert result.successful_channels == 1
    assert len(slack_channel.sent_events) == 1
    assert len(email_channel.sent_events) == 0


def test_notify_filters_by_user_id() -> None:
    """Should only notify channels for specific user."""
    manager = NotificationManager()
    channel = MockChannel()

    manager.register_channel("slack", channel)

    manager.subscribe("user123", "slack", {"spec.created"})
    manager.subscribe("user456", "slack", {"spec.created"})

    event = {
        "event_type": "spec.created",
        "user_id": "user123",
        "data": {},
    }

    result = manager.notify(event)

    # Only user123's subscription should be notified
    assert result.total_channels == 1
    assert len(channel.sent_events) == 1


def test_notify_without_user_id_notifies_all_subscribers() -> None:
    """Should notify all subscribers when no user_id in event."""
    manager = NotificationManager()
    channel = MockChannel()

    manager.register_channel("slack", channel)

    manager.subscribe("user123", "slack", {"spec.created"})
    manager.subscribe("user456", "slack", {"spec.created"})

    event = {
        "event_type": "spec.created",
        "data": {},
    }

    result = manager.notify(event)

    # Both subscriptions should be notified (combined into one channel call)
    assert result.total_channels == 1
    assert len(channel.sent_events) == 1


def test_notify_handles_channel_failure() -> None:
    """Should handle channel send failures gracefully."""
    manager = NotificationManager()
    failing_channel = MockChannel(should_succeed=False)
    working_channel = MockChannel(should_succeed=True)

    manager.register_channel("slack", failing_channel)
    manager.register_channel("email", working_channel)

    manager.subscribe("user123", "slack", {"spec.created"})
    manager.subscribe("user123", "email", {"spec.created"})

    event = {
        "event_type": "spec.created",
        "user_id": "user123",
        "data": {},
    }

    result = manager.notify(event)

    assert result.total_channels == 2
    assert result.successful_channels == 1
    assert result.failed_channels == 1
    assert result.channel_results["slack"] is False
    assert result.channel_results["email"] is True


def test_notify_handles_channel_exception() -> None:
    """Should handle exceptions from channels gracefully."""
    manager = NotificationManager()
    failing_channel = FailingChannel()

    manager.register_channel("webhook", failing_channel)
    manager.subscribe("user123", "webhook", {"spec.created"})

    event = {
        "event_type": "spec.created",
        "user_id": "user123",
        "data": {},
    }

    result = manager.notify(event)

    assert result.total_channels == 1
    assert result.successful_channels == 0
    assert result.failed_channels == 1
    assert result.channel_results["webhook"] is False


def test_notify_handles_unregistered_channel() -> None:
    """Should handle subscriptions to unregistered channels."""
    manager = NotificationManager()

    # Subscribe to slack but don't register the channel
    manager.subscribe("user123", "slack", {"spec.created"})

    event = {
        "event_type": "spec.created",
        "user_id": "user123",
        "data": {},
    }

    result = manager.notify(event)

    assert result.total_channels == 1
    assert result.successful_channels == 0
    assert result.failed_channels == 1
    assert result.channel_results["slack"] is False


def test_subscription_is_subscribed_to_checks_enabled() -> None:
    """Should return False if subscription is disabled."""
    subscription = Subscription(
        user_id="user123",
        channel_type="slack",
        event_types={"spec.created"},
        enabled=False,
    )

    assert subscription.is_subscribed_to("spec.created") is False


def test_notify_with_empty_subscriptions() -> None:
    """Should handle notification with no subscriptions gracefully."""
    manager = NotificationManager()
    channel = MockChannel()

    manager.register_channel("slack", channel)

    event = {
        "event_type": "spec.created",
        "user_id": "user123",
        "data": {},
    }

    result = manager.notify(event)

    assert result.total_channels == 0
    assert result.successful_channels == 0
    assert result.failed_channels == 0
    assert len(channel.sent_events) == 0


def test_multiple_users_same_channel() -> None:
    """Should handle multiple users subscribing to same channel."""
    manager = NotificationManager()
    channel = MockChannel()

    manager.register_channel("slack", channel)

    manager.subscribe("user123", "slack", {"spec.created"})
    manager.subscribe("user456", "slack", {"spec.created"})
    manager.subscribe("user789", "slack", {"spec.approved"})

    event = {
        "event_type": "spec.created",
        "data": {},
    }

    result = manager.notify(event)

    # All users subscribed to spec.created should get notified
    # But it's sent once to the slack channel
    assert result.total_channels == 1
    assert result.successful_channels == 1
    assert len(channel.sent_events) == 1
