"""Centralized notification manager with subscription system.

Coordinates all notification channels (email, Slack, webhooks) and manages
user subscriptions to specific event types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

# Channel types supported by the notification manager
ChannelType = Literal["email", "slack", "webhook"]
EventType = Literal[
    "spec.created",
    "spec.updated",
    "spec.approved",
    "spec.rejected",
    "design_brief.created",
    "design_brief.updated",
    "idea.evaluated",
]


class NotificationChannel(Protocol):
    """Protocol for notification channel implementations."""

    def send(self, event: dict[str, Any]) -> bool:
        """Send notification through this channel.

        Returns True if successful, False otherwise.
        """
        ...


@dataclass
class Subscription:
    """Represents a user's subscription to specific event types on a channel."""

    user_id: str
    channel_type: ChannelType
    event_types: set[EventType] = field(default_factory=set)
    enabled: bool = True

    def is_subscribed_to(self, event_type: str) -> bool:
        """Check if this subscription covers the given event type."""
        if not self.enabled:
            return False
        # If event_types is empty, subscribe to all events
        if not self.event_types:
            return True
        return event_type in self.event_types


@dataclass
class NotificationResult:
    """Result of sending notifications across channels."""

    event_type: str
    total_channels: int
    successful_channels: int
    failed_channels: int
    channel_results: dict[ChannelType, bool] = field(default_factory=dict)


class NotificationManager:
    """Centralized manager for coordinating notifications across channels.

    Features:
    - Routes events to appropriate channels based on subscriptions
    - Manages user subscriptions per event type
    - Provides unified API for triggering notifications
    - Tracks success/failure across channels

    Example:
        manager = NotificationManager()
        manager.register_channel("slack", slack_channel)
        manager.register_channel("webhook", webhook_channel)

        manager.subscribe("user123", "slack", {"spec.created", "spec.approved"})
        manager.subscribe("user123", "webhook", set())  # All events

        result = manager.notify({
            "event_type": "spec.created",
            "user_id": "user123",
            "data": {...}
        })
    """

    def __init__(self) -> None:
        """Initialize the notification manager."""
        self._channels: dict[ChannelType, NotificationChannel] = {}
        self._subscriptions: list[Subscription] = []

    def register_channel(
        self,
        channel_type: ChannelType,
        channel: NotificationChannel,
    ) -> None:
        """Register a notification channel.

        Args:
            channel_type: Type of channel (email, slack, webhook)
            channel: Channel implementation
        """
        self._channels[channel_type] = channel

    def unregister_channel(self, channel_type: ChannelType) -> None:
        """Unregister a notification channel.

        Args:
            channel_type: Type of channel to remove
        """
        self._channels.pop(channel_type, None)

    def subscribe(
        self,
        user_id: str,
        channel_type: ChannelType,
        event_types: set[EventType] | None = None,
    ) -> Subscription:
        """Subscribe a user to notifications on a specific channel.

        Args:
            user_id: User identifier
            channel_type: Channel to subscribe to
            event_types: Set of event types to subscribe to (empty set = all events)

        Returns:
            Created subscription
        """
        subscription = Subscription(
            user_id=user_id,
            channel_type=channel_type,
            event_types=event_types or set(),
        )
        self._subscriptions.append(subscription)
        return subscription

    def unsubscribe(
        self,
        user_id: str,
        channel_type: ChannelType,
        event_type: EventType | None = None,
    ) -> None:
        """Unsubscribe a user from notifications.

        Args:
            user_id: User identifier
            channel_type: Channel to unsubscribe from
            event_type: Specific event type to unsubscribe from (None = all events)
        """
        for subscription in self._subscriptions:
            if subscription.user_id == user_id and subscription.channel_type == channel_type:
                if event_type is None:
                    # Disable entire subscription
                    subscription.enabled = False
                else:
                    # Remove specific event type
                    subscription.event_types.discard(event_type)

    def get_subscriptions(
        self,
        user_id: str | None = None,
        channel_type: ChannelType | None = None,
    ) -> list[Subscription]:
        """Get subscriptions filtered by user and/or channel.

        Args:
            user_id: Filter by user (None = all users)
            channel_type: Filter by channel (None = all channels)

        Returns:
            List of matching subscriptions
        """
        subscriptions = self._subscriptions

        if user_id is not None:
            subscriptions = [s for s in subscriptions if s.user_id == user_id]

        if channel_type is not None:
            subscriptions = [s for s in subscriptions if s.channel_type == channel_type]

        return subscriptions

    def notify(self, event: dict[str, Any]) -> NotificationResult:
        """Send notification across all subscribed channels.

        Args:
            event: Event payload containing event_type, user_id, and data

        Returns:
            NotificationResult with success/failure information
        """
        event_type = event.get("event_type", "unknown")
        user_id = event.get("user_id")

        # Find all channels that should receive this event
        target_channels: set[ChannelType] = set()

        for subscription in self._subscriptions:
            # Filter by user if specified
            if user_id and subscription.user_id != user_id:
                continue

            # Check if subscription covers this event type
            if subscription.is_subscribed_to(event_type):
                target_channels.add(subscription.channel_type)

        # Send to each target channel
        channel_results: dict[ChannelType, bool] = {}
        successful = 0
        failed = 0

        for channel_type in target_channels:
            channel = self._channels.get(channel_type)
            if channel is None:
                # Channel registered in subscription but not available
                channel_results[channel_type] = False
                failed += 1
                continue

            try:
                success = channel.send(event)
                channel_results[channel_type] = success
                if success:
                    successful += 1
                else:
                    failed += 1
            except Exception:
                # Channel raised an exception
                channel_results[channel_type] = False
                failed += 1

        return NotificationResult(
            event_type=event_type,
            total_channels=len(target_channels),
            successful_channels=successful,
            failed_channels=failed,
            channel_results=channel_results,
        )
