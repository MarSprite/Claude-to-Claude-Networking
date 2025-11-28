"""Session control tools for managing collaboration sessions."""

from typing import Any, Dict

from ..broker import SessionManager


def register_session_tools(
    mcp,
    session_manager: SessionManager,
    get_instance_name,
):
    """Register session control tools with the MCP server.

    Args:
        mcp: The FastMCP server instance.
        session_manager: The session manager.
        get_instance_name: Callable that returns current instance name.
    """

    @mcp.tool()
    async def c2c_get_session_status() -> Dict[str, Any]:
        """Get current collaboration session status.

        Returns the session uptime, idle time, time until auto-shutdown,
        and activity statistics.

        Returns:
            Dict with session status information.
        """
        status = await session_manager.get_status()
        status["instance_name"] = get_instance_name()
        return status

    @mcp.tool()
    async def c2c_extend_session() -> Dict[str, Any]:
        """Extend the collaboration session by resetting the idle timer.

        Call this to prevent auto-shutdown when you need more time.
        The session will remain active for another idle timeout period
        from the time of this call.

        Returns:
            Dict confirming session extension.
        """
        result = await session_manager.extend_session()
        result["instance_name"] = get_instance_name()

        # Record this as activity too
        await session_manager.record_activity("extend")

        return result

    @mcp.tool()
    async def c2c_end_session() -> Dict[str, Any]:
        """End the collaboration session and shut down the bridge.

        Call this when collaboration is complete. The remote machine's
        bridge will shut down gracefully.

        Returns:
            Dict with session summary.
        """
        result = await session_manager.end_session(reason="remote_request")
        result["instance_name"] = get_instance_name()
        return result
