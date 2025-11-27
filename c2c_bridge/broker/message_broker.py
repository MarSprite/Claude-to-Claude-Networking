"""Pub/sub message broker for inter-instance communication."""

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field


class MessagePriority(str, Enum):
    """Message priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class MessageType(str, Enum):
    """Types of messages in the system."""
    CHAT = "chat"
    TASK_DELEGATE = "task_delegate"
    TASK_RESULT = "task_result"
    TASK_UPDATE = "task_update"
    CONTEXT_SHARE = "context_share"
    FILE_SYNC = "file_sync"
    STATUS_UPDATE = "status_update"
    SYSTEM = "system"


class C2CMessage(BaseModel):
    """A message between Claude Code instances."""

    id: str = Field(default="", description="Unique message ID")
    type: MessageType = Field(default=MessageType.CHAT, description="Message type")
    source: str = Field(..., description="Source instance name")
    target: str = Field(..., description="Target instance name or 'broadcast'")
    priority: MessagePriority = Field(
        default=MessagePriority.NORMAL,
        description="Message priority"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Message creation time"
    )
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Message payload data"
    )
    requires_ack: bool = Field(
        default=False,
        description="Whether message requires acknowledgment"
    )
    ttl_seconds: int = Field(
        default=3600,
        description="Time to live in seconds"
    )

    def is_expired(self) -> bool:
        """Check if message has expired based on TTL."""
        age = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        return age > self.ttl_seconds


class MessageBroker:
    """Handles message routing between instances using pub/sub pattern."""

    BROADCAST_TARGET = "broadcast"

    def __init__(self):
        """Initialize the message broker."""
        self._subscribers: Dict[str, Set[str]] = defaultdict(set)
        self._queues: Dict[str, asyncio.Queue] = {}
        self._message_store: List[C2CMessage] = []
        self._message_id_counter = 0
        self._lock = asyncio.Lock()

        # Track instance metadata
        self._instances: Dict[str, Dict[str, Any]] = {}

    async def register_instance(
        self,
        instance_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> asyncio.Queue:
        """Register an instance and create its message queue.

        Args:
            instance_id: Unique identifier for the instance.
            metadata: Optional metadata about the instance.

        Returns:
            The message queue for this instance.
        """
        async with self._lock:
            if instance_id not in self._queues:
                self._queues[instance_id] = asyncio.Queue()
                self._subscribers[self.BROADCAST_TARGET].add(instance_id)

            self._instances[instance_id] = {
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or {},
            }

            return self._queues[instance_id]

    async def unregister_instance(self, instance_id: str) -> None:
        """Unregister an instance and clean up.

        Args:
            instance_id: The instance to unregister.
        """
        async with self._lock:
            self._queues.pop(instance_id, None)
            self._instances.pop(instance_id, None)

            # Remove from all subscription topics
            for topic in self._subscribers.values():
                topic.discard(instance_id)

    async def is_registered(self, instance_id: str) -> bool:
        """Check if an instance is registered.

        Args:
            instance_id: The instance to check.

        Returns:
            True if registered, False otherwise.
        """
        return instance_id in self._queues

    async def get_registered_instances(self) -> List[Dict[str, Any]]:
        """Get list of all registered instances.

        Returns:
            List of instance information dictionaries.
        """
        async with self._lock:
            return [
                {"id": inst_id, **info}
                for inst_id, info in self._instances.items()
            ]

    async def publish(self, message: C2CMessage) -> tuple[str, List[str]]:
        """Publish a message to target instance(s).

        Args:
            message: The message to publish.

        Returns:
            Tuple of (message_id, list of recipients).
        """
        async with self._lock:
            # Assign message ID
            self._message_id_counter += 1
            message.id = f"msg_{self._message_id_counter:08d}"

            # Store message
            self._message_store.append(message)

            # Clean up expired messages periodically
            if self._message_id_counter % 100 == 0:
                self._message_store = [
                    m for m in self._message_store if not m.is_expired()
                ]

        # Determine recipients
        if message.target == self.BROADCAST_TARGET:
            recipients = [
                inst for inst in self._queues.keys()
                if inst != message.source
            ]
        else:
            recipients = (
                [message.target]
                if message.target in self._queues
                else []
            )

        # Deliver to all recipients
        delivered_to = []
        for recipient in recipients:
            queue = self._queues.get(recipient)
            if queue:
                await queue.put(message)
                delivered_to.append(recipient)

        return message.id, delivered_to

    async def get_messages(
        self,
        instance_id: str,
        timeout: float = 0.1,
        max_messages: int = 100
    ) -> List[C2CMessage]:
        """Get pending messages for an instance.

        Args:
            instance_id: The instance to get messages for.
            timeout: How long to wait for each message.
            max_messages: Maximum number of messages to return.

        Returns:
            List of pending messages.
        """
        messages = []
        queue = self._queues.get(instance_id)

        if not queue:
            return messages

        try:
            while len(messages) < max_messages:
                msg = await asyncio.wait_for(queue.get(), timeout=timeout)
                if not msg.is_expired():
                    messages.append(msg)
        except asyncio.TimeoutError:
            pass

        return messages

    async def get_message_history(
        self,
        instance_id: Optional[str] = None,
        since_id: Optional[str] = None,
        limit: int = 50
    ) -> List[C2CMessage]:
        """Get message history.

        Args:
            instance_id: Filter to messages involving this instance.
            since_id: Only return messages after this ID.
            limit: Maximum number of messages to return.

        Returns:
            List of historical messages.
        """
        async with self._lock:
            messages = self._message_store.copy()

        # Filter by instance
        if instance_id:
            messages = [
                m for m in messages
                if m.source == instance_id
                or m.target == instance_id
                or m.target == self.BROADCAST_TARGET
            ]

        # Filter by ID
        if since_id:
            found = False
            filtered = []
            for m in messages:
                if found:
                    filtered.append(m)
                elif m.id == since_id:
                    found = True
            messages = filtered

        # Filter expired
        messages = [m for m in messages if not m.is_expired()]

        # Apply limit
        return messages[-limit:]

    async def subscribe_to_topic(self, instance_id: str, topic: str) -> None:
        """Subscribe an instance to a topic.

        Args:
            instance_id: The instance to subscribe.
            topic: The topic to subscribe to.
        """
        async with self._lock:
            self._subscribers[topic].add(instance_id)

    async def unsubscribe_from_topic(self, instance_id: str, topic: str) -> None:
        """Unsubscribe an instance from a topic.

        Args:
            instance_id: The instance to unsubscribe.
            topic: The topic to unsubscribe from.
        """
        async with self._lock:
            self._subscribers[topic].discard(instance_id)

    def get_queue_size(self, instance_id: str) -> int:
        """Get the number of pending messages for an instance.

        Args:
            instance_id: The instance to check.

        Returns:
            Number of pending messages.
        """
        queue = self._queues.get(instance_id)
        return queue.qsize() if queue else 0
