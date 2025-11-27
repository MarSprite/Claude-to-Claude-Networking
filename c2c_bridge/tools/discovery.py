"""Discovery tools for instance registration and listing."""

from typing import Any, Dict, List, Optional

from ..broker import MessageBroker, StateManager


def register_discovery_tools(
    mcp,
    broker: MessageBroker,
    state_manager: StateManager,
    get_instance_name
):
    """Register discovery tools with the MCP server.

    Args:
        mcp: The FastMCP server instance.
        broker: The message broker.
        state_manager: The state manager.
        get_instance_name: Callable that returns current instance name.
    """

    @mcp.tool()
    async def c2c_register(
        capabilities: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Register this instance with the C2C Bridge.

        Args:
            capabilities: Optional list of capabilities this instance has.

        Returns:
            Dict with registration status.
        """
        instance_name = get_instance_name()

        metadata = {
            "capabilities": capabilities or [],
        }

        await broker.register_instance(instance_name, metadata)
        await state_manager.update_instance_state(
            instance_name,
            status="online",
            extra={"capabilities": capabilities or []}
        )

        return {
            "success": True,
            "instance_name": instance_name,
            "message": f"Instance '{instance_name}' registered successfully",
        }

    @mcp.tool()
    async def c2c_list_instances() -> Dict[str, Any]:
        """List all connected Claude Code instances.

        Returns:
            Dict with list of instances and their status.
        """
        instances = await broker.get_registered_instances()
        states = await state_manager.get_all_instance_states()

        result = []
        for inst in instances:
            inst_id = inst["id"]
            state = states.get(inst_id, {})
            result.append({
                "name": inst_id,
                "registered_at": inst.get("registered_at"),
                "status": state.get("status", "unknown"),
                "current_task": state.get("current_task"),
                "last_seen": state.get("last_seen"),
                "capabilities": inst.get("metadata", {}).get("capabilities", []),
            })

        return {
            "count": len(result),
            "instances": result,
        }

    @mcp.tool()
    async def c2c_set_status(
        status: str,
        current_task: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update this instance's status.

        Args:
            status: Status string (e.g., 'idle', 'busy', 'working').
            current_task: Optional description of current task.

        Returns:
            Dict confirming status update.
        """
        instance_name = get_instance_name()

        await state_manager.update_instance_state(
            instance_name,
            status=status,
            current_task=current_task
        )

        return {
            "success": True,
            "instance_name": instance_name,
            "status": status,
            "current_task": current_task,
        }

    @mcp.tool()
    async def c2c_get_status(
        instance: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get status of instances.

        Args:
            instance: Specific instance to get status for, or None for all.

        Returns:
            Dict with instance status information.
        """
        if instance:
            state = await state_manager.get_instance_state(instance)
            if state:
                return {
                    "found": True,
                    "instance": instance,
                    **state,
                }
            return {
                "found": False,
                "instance": instance,
                "message": f"Instance '{instance}' not found",
            }

        states = await state_manager.get_all_instance_states()
        return {
            "count": len(states),
            "instances": {
                name: state for name, state in states.items()
            },
        }

    @mcp.tool()
    async def c2c_unregister() -> Dict[str, Any]:
        """Unregister this instance from the C2C Bridge.

        Returns:
            Dict confirming unregistration.
        """
        instance_name = get_instance_name()

        await broker.unregister_instance(instance_name)
        await state_manager.remove_instance_state(instance_name)

        return {
            "success": True,
            "instance_name": instance_name,
            "message": f"Instance '{instance_name}' unregistered",
        }
