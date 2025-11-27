"""Context sharing tools for inter-instance state synchronization."""

from typing import Any, Dict, List, Optional

from ..broker import StateManager, MessageBroker, C2CMessage, MessageType


def register_context_tools(
    mcp,
    state_manager: StateManager,
    broker: MessageBroker,
    get_instance_name
):
    """Register context sharing tools with the MCP server.

    Args:
        mcp: The FastMCP server instance.
        state_manager: The state manager.
        broker: The message broker.
        get_instance_name: Callable that returns current instance name.
    """

    @mcp.tool()
    async def c2c_share_context(
        key: str,
        value: Any,
        scope: str = "global",
        notify: bool = True
    ) -> Dict[str, Any]:
        """Share context data with other instances.

        Args:
            key: The context key.
            value: The value to share (must be JSON serializable).
            scope: Context scope ('global', 'project', or instance name).
            notify: Whether to notify other instances of the update.

        Returns:
            Dict confirming context was shared.
        """
        instance_name = get_instance_name()

        await state_manager.set_context(
            key=key,
            value=value,
            scope=scope,
            metadata={"source": instance_name}
        )

        if notify:
            # Notify other instances
            msg = C2CMessage(
                type=MessageType.CONTEXT_SHARE,
                source=instance_name,
                target="broadcast",
                payload={
                    "key": key,
                    "scope": scope,
                    "action": "updated",
                },
            )
            await broker.publish(msg)

        return {
            "success": True,
            "key": key,
            "scope": scope,
            "source": instance_name,
        }

    @mcp.tool()
    async def c2c_get_context(
        key: str,
        scope: str = "global"
    ) -> Dict[str, Any]:
        """Get shared context data.

        Args:
            key: The context key to retrieve.
            scope: Context scope to look in.

        Returns:
            Dict with the context value and metadata.
        """
        entry = await state_manager.get_context_with_metadata(key, scope)

        if entry is None:
            return {
                "found": False,
                "key": key,
                "scope": scope,
            }

        return {
            "found": True,
            "key": key,
            "scope": scope,
            "value": entry.get("value"),
            "updated_at": entry.get("updated_at"),
            "source": entry.get("metadata", {}).get("source"),
        }

    @mcp.tool()
    async def c2c_list_context(
        scope: Optional[str] = None
    ) -> Dict[str, Any]:
        """List all shared context keys.

        Args:
            scope: Optional scope to filter by. If None, lists all scopes.

        Returns:
            Dict with context keys and their metadata.
        """
        if scope:
            context = await state_manager.list_context(scope)
            keys = list(context.keys())
            return {
                "scope": scope,
                "keys": keys,
                "count": len(keys),
            }

        # List all scopes
        scopes = await state_manager.list_scopes()
        result = {}
        for s in scopes:
            context = await state_manager.list_context(s)
            result[s] = list(context.keys())

        return {
            "scopes": scopes,
            "context_by_scope": result,
        }

    @mcp.tool()
    async def c2c_delete_context(
        key: str,
        scope: str = "global",
        notify: bool = True
    ) -> Dict[str, Any]:
        """Delete shared context data.

        Args:
            key: The context key to delete.
            scope: Context scope.
            notify: Whether to notify other instances.

        Returns:
            Dict confirming deletion.
        """
        instance_name = get_instance_name()

        deleted = await state_manager.delete_context(key, scope)

        if deleted and notify:
            msg = C2CMessage(
                type=MessageType.CONTEXT_SHARE,
                source=instance_name,
                target="broadcast",
                payload={
                    "key": key,
                    "scope": scope,
                    "action": "deleted",
                },
            )
            await broker.publish(msg)

        return {
            "success": deleted,
            "key": key,
            "scope": scope,
            "deleted": deleted,
        }

    @mcp.tool()
    async def c2c_sync_file(
        path: str,
        content: str
    ) -> Dict[str, Any]:
        """Share a file with other instances.

        Args:
            path: Virtual path for the file.
            content: File content.

        Returns:
            Dict confirming file was shared.
        """
        instance_name = get_instance_name()

        await state_manager.cache_file(path, content, instance_name)

        # Notify other instances
        msg = C2CMessage(
            type=MessageType.FILE_SYNC,
            source=instance_name,
            target="broadcast",
            payload={
                "path": path,
                "action": "synced",
            },
        )
        await broker.publish(msg)

        return {
            "success": True,
            "path": path,
            "source": instance_name,
            "size": len(content),
        }

    @mcp.tool()
    async def c2c_get_file(
        path: str
    ) -> Dict[str, Any]:
        """Get a shared file.

        Args:
            path: Virtual path of the file.

        Returns:
            Dict with file content and metadata.
        """
        file_data = await state_manager.get_cached_file(path)

        if file_data is None:
            return {
                "found": False,
                "path": path,
            }

        return {
            "found": True,
            "path": path,
            "content": file_data.get("content"),
            "source": file_data.get("source"),
            "cached_at": file_data.get("cached_at"),
        }

    @mcp.tool()
    async def c2c_list_files() -> Dict[str, Any]:
        """List all shared files.

        Returns:
            Dict with list of shared file paths.
        """
        files = await state_manager.list_cached_files()

        return {
            "count": len(files),
            "files": files,
        }
