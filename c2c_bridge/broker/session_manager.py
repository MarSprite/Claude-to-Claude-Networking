"""Session management with idle timeout and activity tracking."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional


class SessionManager:
    """Manages collaboration sessions with idle timeout."""

    def __init__(
        self,
        idle_timeout_seconds: int = 900,  # 15 minutes default
        on_session_end: Optional[Callable[[], None]] = None,
    ):
        """Initialize the session manager.

        Args:
            idle_timeout_seconds: Seconds of inactivity before auto-shutdown.
            on_session_end: Callback when session ends (timeout or manual).
        """
        self._idle_timeout = idle_timeout_seconds
        self._on_session_end = on_session_end

        self._session_start: Optional[datetime] = None
        self._last_activity: Optional[datetime] = None
        self._activity_count = 0
        self._tasks_completed = 0
        self._messages_sent = 0
        self._is_active = False

        self._shutdown_event = asyncio.Event()
        self._timeout_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def start_session(self) -> Dict[str, Any]:
        """Start a new collaboration session.

        Returns:
            Session info dict.
        """
        async with self._lock:
            now = datetime.now(timezone.utc)
            self._session_start = now
            self._last_activity = now
            self._activity_count = 0
            self._tasks_completed = 0
            self._messages_sent = 0
            self._is_active = True
            self._shutdown_event.clear()

            # Start idle timeout monitor
            if self._timeout_task:
                self._timeout_task.cancel()
            self._timeout_task = asyncio.create_task(self._idle_monitor())

            return {
                "started": True,
                "start_time": now.isoformat(),
                "idle_timeout_seconds": self._idle_timeout,
            }

    async def end_session(self, reason: str = "manual") -> Dict[str, Any]:
        """End the current session.

        Args:
            reason: Why the session is ending.

        Returns:
            Session summary dict.
        """
        async with self._lock:
            if not self._is_active:
                return {
                    "ended": False,
                    "message": "No active session",
                }

            summary = self._get_session_summary_unlocked()
            summary["ended"] = True
            summary["end_reason"] = reason

            self._is_active = False
            self._shutdown_event.set()

            if self._timeout_task:
                self._timeout_task.cancel()
                self._timeout_task = None

            if self._on_session_end:
                self._on_session_end()

            return summary

    async def record_activity(self, activity_type: str = "general") -> None:
        """Record activity to reset idle timer.

        Args:
            activity_type: Type of activity (for logging).
        """
        async with self._lock:
            if not self._is_active:
                return

            self._last_activity = datetime.now(timezone.utc)
            self._activity_count += 1

            if activity_type == "task_complete":
                self._tasks_completed += 1
            elif activity_type == "message":
                self._messages_sent += 1

    async def extend_session(self, additional_seconds: int = 0) -> Dict[str, Any]:
        """Extend the session by resetting idle timer.

        Args:
            additional_seconds: Optional additional time (currently just resets timer).

        Returns:
            Updated session status.
        """
        async with self._lock:
            if not self._is_active:
                return {
                    "extended": False,
                    "message": "No active session",
                }

            self._last_activity = datetime.now(timezone.utc)

            return {
                "extended": True,
                "idle_timeout_seconds": self._idle_timeout,
                "message": "Session extended - idle timer reset",
            }

    async def get_status(self) -> Dict[str, Any]:
        """Get current session status.

        Returns:
            Session status dict.
        """
        async with self._lock:
            return self._get_session_summary_unlocked()

    def _get_session_summary_unlocked(self) -> Dict[str, Any]:
        """Get session summary without lock (internal use).

        Returns:
            Session summary dict.
        """
        if not self._is_active or not self._session_start:
            return {
                "active": False,
                "message": "No active session",
            }

        now = datetime.now(timezone.utc)
        uptime = (now - self._session_start).total_seconds()
        idle_seconds = (now - self._last_activity).total_seconds() if self._last_activity else 0
        time_until_timeout = max(0, self._idle_timeout - idle_seconds)

        return {
            "active": True,
            "start_time": self._session_start.isoformat(),
            "uptime_seconds": int(uptime),
            "idle_seconds": int(idle_seconds),
            "idle_timeout_seconds": self._idle_timeout,
            "time_until_timeout_seconds": int(time_until_timeout),
            "activity_count": self._activity_count,
            "tasks_completed": self._tasks_completed,
            "messages_sent": self._messages_sent,
        }

    async def _idle_monitor(self) -> None:
        """Background task to monitor idle timeout."""
        try:
            while self._is_active:
                await asyncio.sleep(10)  # Check every 10 seconds

                async with self._lock:
                    if not self._is_active or not self._last_activity:
                        break

                    idle_seconds = (
                        datetime.now(timezone.utc) - self._last_activity
                    ).total_seconds()

                    if idle_seconds >= self._idle_timeout:
                        # Timeout reached - end session
                        break

            # If we exit the loop due to timeout (not cancellation)
            if self._is_active:
                await self.end_session(reason="idle_timeout")

        except asyncio.CancelledError:
            pass

    async def wait_for_shutdown(self) -> None:
        """Wait for the session to end."""
        await self._shutdown_event.wait()

    @property
    def is_active(self) -> bool:
        """Check if session is currently active."""
        return self._is_active
