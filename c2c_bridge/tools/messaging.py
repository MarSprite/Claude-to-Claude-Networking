"""Messaging tools for inter-instance communication."""

from typing import Any, Dict, List, Optional

from ..broker import MessageBroker, C2CMessage, MessageType, MessagePriority


def register_messaging_tools(mcp, broker: MessageBroker, get_instance_name):
    """Register messaging tools with the MCP server.

    Args:
        mcp: The FastMCP server instance.
        broker: The message broker.
        get_instance_name: Callable that returns current instance name.
    """

    @mcp.tool()
    async def c2c_send_message(
        target: str,
        message: str,
        priority: str = "normal",
        message_type: str = "chat"
    ) -> Dict[str, Any]:
        """Send a message to another Claude Code instance.

        Args:
            target: Instance name to send to, or 'broadcast' for all instances.
            message: The message content to send.
            priority: Message priority ('low', 'normal', 'high', 'urgent').
            message_type: Type of message ('chat', 'system').

        Returns:
            Dict with message_id and list of recipients.
        """
        instance_name = get_instance_name()

        # Validate priority
        try:
            msg_priority = MessagePriority(priority)
        except ValueError:
            msg_priority = MessagePriority.NORMAL

        # Validate type
        try:
            msg_type = MessageType(message_type)
        except ValueError:
            msg_type = MessageType.CHAT

        msg = C2CMessage(
            type=msg_type,
            source=instance_name,
            target=target,
            priority=msg_priority,
            payload={"message": message},
        )

        message_id, delivered_to = await broker.publish(msg)

        return {
            "success": len(delivered_to) > 0 or target == "broadcast",
            "message_id": message_id,
            "delivered_to": delivered_to,
            "target": target,
        }

    @mcp.tool()
    async def c2c_get_messages(
        limit: int = 50,
        timeout: float = 0.5
    ) -> Dict[str, Any]:
        """Retrieve pending messages for this instance.

        Args:
            limit: Maximum number of messages to retrieve.
            timeout: How long to wait for messages (seconds).

        Returns:
            Dict with list of messages.
        """
        instance_name = get_instance_name()

        messages = await broker.get_messages(
            instance_name,
            timeout=timeout,
            max_messages=limit
        )

        return {
            "count": len(messages),
            "messages": [
                {
                    "id": msg.id,
                    "type": msg.type.value,
                    "source": msg.source,
                    "priority": msg.priority.value,
                    "timestamp": msg.timestamp.isoformat(),
                    "payload": msg.payload,
                }
                for msg in messages
            ],
        }

    @mcp.tool()
    async def c2c_get_message_history(
        since_id: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """Get message history for this instance.

        Args:
            since_id: Only return messages after this message ID.
            limit: Maximum number of messages to return.

        Returns:
            Dict with list of historical messages.
        """
        instance_name = get_instance_name()

        messages = await broker.get_message_history(
            instance_id=instance_name,
            since_id=since_id,
            limit=limit
        )

        return {
            "count": len(messages),
            "messages": [
                {
                    "id": msg.id,
                    "type": msg.type.value,
                    "source": msg.source,
                    "target": msg.target,
                    "priority": msg.priority.value,
                    "timestamp": msg.timestamp.isoformat(),
                    "payload": msg.payload,
                }
                for msg in messages
            ],
        }

    @mcp.tool()
    async def c2c_broadcast(
        message: str,
        priority: str = "normal"
    ) -> Dict[str, Any]:
        """Broadcast a message to all connected instances.

        Args:
            message: The message to broadcast.
            priority: Message priority ('low', 'normal', 'high', 'urgent').

        Returns:
            Dict with broadcast result.
        """
        return await c2c_send_message(
            target="broadcast",
            message=message,
            priority=priority,
            message_type="chat"
        )
