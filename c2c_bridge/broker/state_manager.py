"""Shared state management for inter-instance context sharing."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles


class StateManager:
    """Manages shared state between Claude Code instances."""

    def __init__(self, state_file: Path):
        """Initialize state manager.

        Args:
            state_file: Path to persistent state file.
        """
        self.state_file = Path(state_file)
        self._state: Dict[str, Dict[str, Any]] = {}
        self._instance_states: Dict[str, Dict[str, Any]] = {}
        self._file_cache: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._loaded = False

    async def _ensure_loaded(self) -> None:
        """Ensure state is loaded from disk."""
        if not self._loaded:
            await self._load_state()
            self._loaded = True

    async def _load_state(self) -> None:
        """Load state from disk."""
        if self.state_file.exists():
            try:
                async with aiofiles.open(self.state_file, 'r') as f:
                    content = await f.read()
                    data = json.loads(content)
                    self._state = data.get("context", {})
                    self._file_cache = data.get("files", {})
            except (json.JSONDecodeError, IOError):
                self._state = {}
                self._file_cache = {}

    async def _save_state(self) -> None:
        """Persist state to disk."""
        # Ensure parent directory exists
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "context": self._state,
            "files": self._file_cache,
            "last_saved": datetime.now(timezone.utc).isoformat(),
        }

        async with aiofiles.open(self.state_file, 'w') as f:
            await f.write(json.dumps(data, indent=2, default=str))

    async def set_context(
        self,
        key: str,
        value: Any,
        scope: str = "global",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Set a shared context value.

        Args:
            key: The context key.
            value: The value to store.
            scope: Context scope (e.g., "global", "project", instance name).
            metadata: Optional metadata about the context.
        """
        await self._ensure_loaded()

        async with self._lock:
            if scope not in self._state:
                self._state[scope] = {}

            self._state[scope][key] = {
                "value": value,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or {},
            }

            await self._save_state()

    async def get_context(
        self,
        key: str,
        scope: str = "global",
        default: Any = None
    ) -> Any:
        """Get a shared context value.

        Args:
            key: The context key.
            scope: Context scope to look in.
            default: Default value if not found.

        Returns:
            The stored value or default.
        """
        await self._ensure_loaded()

        entry = self._state.get(scope, {}).get(key)
        if entry is None:
            return default
        return entry.get("value", default)

    async def get_context_with_metadata(
        self,
        key: str,
        scope: str = "global"
    ) -> Optional[Dict[str, Any]]:
        """Get a context value with its metadata.

        Args:
            key: The context key.
            scope: Context scope to look in.

        Returns:
            Dict with value, updated_at, and metadata, or None.
        """
        await self._ensure_loaded()
        return self._state.get(scope, {}).get(key)

    async def delete_context(self, key: str, scope: str = "global") -> bool:
        """Delete a context value.

        Args:
            key: The context key to delete.
            scope: Context scope.

        Returns:
            True if deleted, False if not found.
        """
        await self._ensure_loaded()

        async with self._lock:
            if scope in self._state and key in self._state[scope]:
                del self._state[scope][key]
                await self._save_state()
                return True
            return False

    async def list_context(
        self,
        scope: Optional[str] = None
    ) -> Dict[str, Any]:
        """List all context keys and values.

        Args:
            scope: Optional scope to filter by.

        Returns:
            Dictionary of context data.
        """
        await self._ensure_loaded()

        if scope:
            return self._state.get(scope, {})
        return self._state.copy()

    async def list_scopes(self) -> List[str]:
        """List all available scopes.

        Returns:
            List of scope names.
        """
        await self._ensure_loaded()
        return list(self._state.keys())

    # Instance state management

    async def update_instance_state(
        self,
        instance_id: str,
        status: str,
        current_task: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update state for a specific instance.

        Args:
            instance_id: The instance identifier.
            status: Current status (e.g., "idle", "busy", "offline").
            current_task: Optional current task description.
            extra: Optional additional state data.
        """
        async with self._lock:
            self._instance_states[instance_id] = {
                "status": status,
                "current_task": current_task,
                "last_seen": datetime.now(timezone.utc).isoformat(),
                **(extra or {}),
            }

    async def get_instance_state(
        self,
        instance_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get state for a specific instance.

        Args:
            instance_id: The instance identifier.

        Returns:
            Instance state dict or None.
        """
        return self._instance_states.get(instance_id)

    async def get_all_instance_states(self) -> Dict[str, Dict[str, Any]]:
        """Get state of all registered instances.

        Returns:
            Dictionary mapping instance IDs to their states.
        """
        return dict(self._instance_states)

    async def remove_instance_state(self, instance_id: str) -> None:
        """Remove state for an instance.

        Args:
            instance_id: The instance to remove.
        """
        async with self._lock:
            self._instance_states.pop(instance_id, None)

    # File cache management

    async def cache_file(
        self,
        path: str,
        content: str,
        source_instance: str
    ) -> None:
        """Cache a file for sharing between instances.

        Args:
            path: Virtual path for the file.
            content: File content.
            source_instance: Instance that shared the file.
        """
        await self._ensure_loaded()

        async with self._lock:
            self._file_cache[path] = {
                "content": content,
                "source": source_instance,
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }
            await self._save_state()

    async def get_cached_file(self, path: str) -> Optional[Dict[str, Any]]:
        """Get a cached file.

        Args:
            path: Virtual path of the file.

        Returns:
            Dict with content, source, and cached_at, or None.
        """
        await self._ensure_loaded()
        return self._file_cache.get(path)

    async def list_cached_files(self) -> List[str]:
        """List all cached file paths.

        Returns:
            List of virtual file paths.
        """
        await self._ensure_loaded()
        return list(self._file_cache.keys())

    async def delete_cached_file(self, path: str) -> bool:
        """Delete a cached file.

        Args:
            path: Virtual path to delete.

        Returns:
            True if deleted, False if not found.
        """
        await self._ensure_loaded()

        async with self._lock:
            if path in self._file_cache:
                del self._file_cache[path]
                await self._save_state()
                return True
            return False
