"""Task delegation tools for inter-instance work distribution."""

from typing import Any, Dict, List, Optional

from ..broker import (
    TaskQueue,
    Task,
    TaskStatus,
    MessageBroker,
    C2CMessage,
    MessageType,
    MessagePriority,
)


def register_task_tools(
    mcp,
    task_queue: TaskQueue,
    broker: MessageBroker,
    get_instance_name
):
    """Register task delegation tools with the MCP server.

    Args:
        mcp: The FastMCP server instance.
        task_queue: The task queue.
        broker: The message broker.
        get_instance_name: Callable that returns current instance name.
    """

    @mcp.tool()
    async def c2c_delegate_task(
        target: str,
        task_description: str,
        context: Optional[Dict[str, Any]] = None,
        wait: bool = False,
        timeout: float = 300
    ) -> Dict[str, Any]:
        """Delegate a task to another Claude Code instance.

        Args:
            target: Instance name to assign the task to.
            task_description: Description of what needs to be done.
            context: Optional additional context for the task.
            wait: Whether to wait for the task to complete.
            timeout: How long to wait if wait=True (seconds).

        Returns:
            Dict with task ID and status.
        """
        instance_name = get_instance_name()

        # Create the task
        task = await task_queue.create_task(
            delegator=instance_name,
            assignee=target,
            description=task_description,
            context=context,
        )

        # Notify the target instance
        msg = C2CMessage(
            type=MessageType.TASK_DELEGATE,
            source=instance_name,
            target=target,
            priority=MessagePriority.HIGH,
            payload={
                "task_id": task.id,
                "description": task_description,
                "context": context or {},
            },
        )
        _, delivered = await broker.publish(msg)

        result = {
            "success": len(delivered) > 0,
            "task_id": task.id,
            "delegator": instance_name,
            "assignee": target,
            "status": task.status.value,
            "delivered": len(delivered) > 0,
        }

        if wait:
            completed_task = await task_queue.wait_for_result(task.id, timeout)
            if completed_task:
                result["status"] = completed_task.status.value
                result["result"] = completed_task.result
                result["error"] = completed_task.error

        return result

    @mcp.tool()
    async def c2c_get_pending_tasks() -> Dict[str, Any]:
        """Get tasks assigned to this instance that are pending.

        Returns:
            Dict with list of pending tasks.
        """
        instance_name = get_instance_name()

        tasks = await task_queue.get_pending_tasks(instance_name)

        return {
            "count": len(tasks),
            "tasks": [
                {
                    "id": t.id,
                    "delegator": t.delegator,
                    "description": t.description,
                    "context": t.context,
                    "created_at": t.created_at.isoformat(),
                }
                for t in tasks
            ],
        }

    @mcp.tool()
    async def c2c_accept_task(task_id: str) -> Dict[str, Any]:
        """Accept a delegated task.

        Args:
            task_id: The task ID to accept.

        Returns:
            Dict confirming task acceptance.
        """
        instance_name = get_instance_name()

        task = await task_queue.accept_task(task_id)

        if not task:
            return {
                "success": False,
                "error": f"Task {task_id} not found",
            }

        # Notify delegator
        msg = C2CMessage(
            type=MessageType.TASK_UPDATE,
            source=instance_name,
            target=task.delegator,
            payload={
                "task_id": task_id,
                "status": "accepted",
            },
        )
        await broker.publish(msg)

        return {
            "success": True,
            "task_id": task_id,
            "status": task.status.value,
        }

    @mcp.tool()
    async def c2c_start_task(task_id: str) -> Dict[str, Any]:
        """Mark a task as in progress.

        Args:
            task_id: The task ID to start.

        Returns:
            Dict confirming task started.
        """
        instance_name = get_instance_name()

        task = await task_queue.start_task(task_id)

        if not task:
            return {
                "success": False,
                "error": f"Task {task_id} not found",
            }

        # Notify delegator
        msg = C2CMessage(
            type=MessageType.TASK_UPDATE,
            source=instance_name,
            target=task.delegator,
            payload={
                "task_id": task_id,
                "status": "in_progress",
            },
        )
        await broker.publish(msg)

        return {
            "success": True,
            "task_id": task_id,
            "status": task.status.value,
        }

    @mcp.tool()
    async def c2c_complete_task(
        task_id: str,
        result: Any
    ) -> Dict[str, Any]:
        """Mark a task as completed with result.

        Args:
            task_id: The task ID to complete.
            result: The result of the task.

        Returns:
            Dict confirming task completion.
        """
        instance_name = get_instance_name()

        task = await task_queue.complete_task(task_id, result)

        if not task:
            return {
                "success": False,
                "error": f"Task {task_id} not found",
            }

        # Notify delegator
        msg = C2CMessage(
            type=MessageType.TASK_RESULT,
            source=instance_name,
            target=task.delegator,
            priority=MessagePriority.HIGH,
            payload={
                "task_id": task_id,
                "status": "completed",
                "result": result,
            },
        )
        await broker.publish(msg)

        return {
            "success": True,
            "task_id": task_id,
            "status": task.status.value,
        }

    @mcp.tool()
    async def c2c_fail_task(
        task_id: str,
        error: str
    ) -> Dict[str, Any]:
        """Mark a task as failed.

        Args:
            task_id: The task ID that failed.
            error: Error description.

        Returns:
            Dict confirming task failure.
        """
        instance_name = get_instance_name()

        task = await task_queue.fail_task(task_id, error)

        if not task:
            return {
                "success": False,
                "error": f"Task {task_id} not found",
            }

        # Notify delegator
        msg = C2CMessage(
            type=MessageType.TASK_RESULT,
            source=instance_name,
            target=task.delegator,
            priority=MessagePriority.HIGH,
            payload={
                "task_id": task_id,
                "status": "failed",
                "error": error,
            },
        )
        await broker.publish(msg)

        return {
            "success": True,
            "task_id": task_id,
            "status": task.status.value,
            "error": error,
        }

    @mcp.tool()
    async def c2c_get_task_result(
        task_id: str,
        wait: bool = False,
        timeout: float = 300
    ) -> Dict[str, Any]:
        """Get the result of a delegated task.

        Args:
            task_id: The task ID to check.
            wait: Whether to wait for completion if not done.
            timeout: How long to wait if wait=True (seconds).

        Returns:
            Dict with task status and result.
        """
        if wait:
            task = await task_queue.wait_for_result(task_id, timeout)
        else:
            task = await task_queue.get_task(task_id)

        if not task:
            return {
                "found": False,
                "task_id": task_id,
                "error": "Task not found",
            }

        return {
            "found": True,
            "task_id": task_id,
            "status": task.status.value,
            "delegator": task.delegator,
            "assignee": task.assignee,
            "description": task.description,
            "result": task.result,
            "error": task.error,
            "created_at": task.created_at.isoformat(),
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }

    @mcp.tool()
    async def c2c_list_my_tasks(
        role: str = "both",
        include_completed: bool = False
    ) -> Dict[str, Any]:
        """List tasks related to this instance.

        Args:
            role: Filter by role ('delegator', 'assignee', or 'both').
            include_completed: Whether to include completed tasks.

        Returns:
            Dict with lists of tasks.
        """
        instance_name = get_instance_name()

        result = {"delegated": [], "assigned": []}

        if role in ["delegator", "both"]:
            tasks = await task_queue.get_tasks_by_delegator(instance_name)
            if not include_completed:
                tasks = [t for t in tasks if not t.is_terminal()]
            result["delegated"] = [
                {
                    "id": t.id,
                    "assignee": t.assignee,
                    "description": t.description,
                    "status": t.status.value,
                    "created_at": t.created_at.isoformat(),
                }
                for t in tasks
            ]

        if role in ["assignee", "both"]:
            tasks = await task_queue.get_tasks_for_assignee(instance_name)
            if not include_completed:
                tasks = [t for t in tasks if not t.is_terminal()]
            result["assigned"] = [
                {
                    "id": t.id,
                    "delegator": t.delegator,
                    "description": t.description,
                    "status": t.status.value,
                    "created_at": t.created_at.isoformat(),
                }
                for t in tasks
            ]

        return result
