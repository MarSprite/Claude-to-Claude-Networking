"""Task queue for delegating work between Claude Code instances."""

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Status of a delegated task."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task(BaseModel):
    """A task delegated between instances."""

    id: str = Field(default="", description="Unique task ID")
    delegator: str = Field(..., description="Instance that delegated the task")
    assignee: str = Field(..., description="Instance assigned to do the task")
    description: str = Field(..., description="Task description/prompt")
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context for the task"
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        description="Current task status"
    )
    result: Optional[Any] = Field(
        default=None,
        description="Task result when completed"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if failed"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the task was created"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last update time"
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="When the task was completed"
    )

    def is_terminal(self) -> bool:
        """Check if task is in a terminal state."""
        return self.status in [
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED
        ]


class TaskQueue:
    """Manages task delegation between instances."""

    def __init__(self):
        """Initialize the task queue."""
        self._tasks: Dict[str, Task] = {}
        self._pending_results: Dict[str, asyncio.Event] = {}
        self._task_counter = 0
        self._lock = asyncio.Lock()

        # Index tasks by assignee for quick lookup
        self._tasks_by_assignee: Dict[str, List[str]] = {}
        self._tasks_by_delegator: Dict[str, List[str]] = {}

    async def create_task(
        self,
        delegator: str,
        assignee: str,
        description: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Task:
        """Create a new task for delegation.

        Args:
            delegator: Instance delegating the task.
            assignee: Instance to perform the task.
            description: Task description.
            context: Optional additional context.

        Returns:
            The created Task object.
        """
        async with self._lock:
            self._task_counter += 1
            task_id = f"task_{self._task_counter:08d}"

            task = Task(
                id=task_id,
                delegator=delegator,
                assignee=assignee,
                description=description,
                context=context or {},
            )

            self._tasks[task_id] = task
            self._pending_results[task_id] = asyncio.Event()

            # Update indexes
            if assignee not in self._tasks_by_assignee:
                self._tasks_by_assignee[assignee] = []
            self._tasks_by_assignee[assignee].append(task_id)

            if delegator not in self._tasks_by_delegator:
                self._tasks_by_delegator[delegator] = []
            self._tasks_by_delegator[delegator].append(task_id)

            return task

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID.

        Args:
            task_id: The task ID.

        Returns:
            The Task or None if not found.
        """
        return self._tasks.get(task_id)

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        result: Optional[Any] = None,
        error: Optional[str] = None
    ) -> Optional[Task]:
        """Update task status and optionally set result.

        Args:
            task_id: The task to update.
            status: New status.
            result: Optional result data.
            error: Optional error message.

        Returns:
            Updated Task or None if not found.
        """
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None

            task.status = status
            task.updated_at = datetime.now(timezone.utc)

            if result is not None:
                task.result = result
            if error is not None:
                task.error = error

            if task.is_terminal():
                task.completed_at = datetime.now(timezone.utc)
                # Signal waiters
                event = self._pending_results.get(task_id)
                if event:
                    event.set()

            return task

    async def wait_for_result(
        self,
        task_id: str,
        timeout: float = 300
    ) -> Optional[Task]:
        """Wait for a task to complete.

        Args:
            task_id: The task to wait for.
            timeout: Maximum time to wait in seconds.

        Returns:
            The completed Task or None if timeout.
        """
        event = self._pending_results.get(task_id)
        if not event:
            return self._tasks.get(task_id)

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

        return self._tasks.get(task_id)

    async def get_tasks_for_assignee(
        self,
        assignee: str,
        status: Optional[TaskStatus] = None
    ) -> List[Task]:
        """Get tasks assigned to an instance.

        Args:
            assignee: The instance name.
            status: Optional status filter.

        Returns:
            List of tasks.
        """
        task_ids = self._tasks_by_assignee.get(assignee, [])
        tasks = [self._tasks[tid] for tid in task_ids if tid in self._tasks]

        if status:
            tasks = [t for t in tasks if t.status == status]

        return tasks

    async def get_tasks_by_delegator(
        self,
        delegator: str,
        status: Optional[TaskStatus] = None
    ) -> List[Task]:
        """Get tasks delegated by an instance.

        Args:
            delegator: The instance name.
            status: Optional status filter.

        Returns:
            List of tasks.
        """
        task_ids = self._tasks_by_delegator.get(delegator, [])
        tasks = [self._tasks[tid] for tid in task_ids if tid in self._tasks]

        if status:
            tasks = [t for t in tasks if t.status == status]

        return tasks

    async def get_pending_tasks(self, assignee: str) -> List[Task]:
        """Get pending tasks for an instance.

        Args:
            assignee: The instance name.

        Returns:
            List of pending tasks.
        """
        return await self.get_tasks_for_assignee(assignee, TaskStatus.PENDING)

    async def accept_task(self, task_id: str) -> Optional[Task]:
        """Mark a task as accepted.

        Args:
            task_id: The task to accept.

        Returns:
            Updated Task or None.
        """
        return await self.update_task_status(task_id, TaskStatus.ACCEPTED)

    async def start_task(self, task_id: str) -> Optional[Task]:
        """Mark a task as in progress.

        Args:
            task_id: The task to start.

        Returns:
            Updated Task or None.
        """
        return await self.update_task_status(task_id, TaskStatus.IN_PROGRESS)

    async def complete_task(
        self,
        task_id: str,
        result: Any
    ) -> Optional[Task]:
        """Mark a task as completed with result.

        Args:
            task_id: The task to complete.
            result: The task result.

        Returns:
            Updated Task or None.
        """
        return await self.update_task_status(
            task_id,
            TaskStatus.COMPLETED,
            result=result
        )

    async def fail_task(
        self,
        task_id: str,
        error: str
    ) -> Optional[Task]:
        """Mark a task as failed.

        Args:
            task_id: The task that failed.
            error: Error description.

        Returns:
            Updated Task or None.
        """
        return await self.update_task_status(
            task_id,
            TaskStatus.FAILED,
            error=error
        )

    async def cancel_task(self, task_id: str) -> Optional[Task]:
        """Cancel a task.

        Args:
            task_id: The task to cancel.

        Returns:
            Updated Task or None.
        """
        return await self.update_task_status(task_id, TaskStatus.CANCELLED)

    async def get_all_tasks(
        self,
        include_completed: bool = False
    ) -> List[Task]:
        """Get all tasks.

        Args:
            include_completed: Whether to include terminal tasks.

        Returns:
            List of tasks.
        """
        tasks = list(self._tasks.values())
        if not include_completed:
            tasks = [t for t in tasks if not t.is_terminal()]
        return tasks

    async def cleanup_old_tasks(self, max_age_hours: int = 24) -> int:
        """Remove old completed tasks.

        Args:
            max_age_hours: Maximum age for completed tasks.

        Returns:
            Number of tasks removed.
        """
        now = datetime.now(timezone.utc)
        removed = 0

        async with self._lock:
            to_remove = []
            for task_id, task in self._tasks.items():
                if task.is_terminal() and task.completed_at:
                    age_hours = (now - task.completed_at).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        to_remove.append(task_id)

            for task_id in to_remove:
                task = self._tasks.pop(task_id, None)
                if task:
                    # Clean up indexes
                    if task.assignee in self._tasks_by_assignee:
                        self._tasks_by_assignee[task.assignee] = [
                            tid for tid in self._tasks_by_assignee[task.assignee]
                            if tid != task_id
                        ]
                    if task.delegator in self._tasks_by_delegator:
                        self._tasks_by_delegator[task.delegator] = [
                            tid for tid in self._tasks_by_delegator[task.delegator]
                            if tid != task_id
                        ]
                    self._pending_results.pop(task_id, None)
                    removed += 1

        return removed
