"""Asynchronous timeout monitoring for pending configurations."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta

from ace_network_manager.state.tracker import StateTracker


class TimeoutWatcher:
    """Asynchronous timeout monitoring for pending configurations.

    Runs in background and triggers rollback callback when timeout expires.
    """

    def __init__(
        self,
        state_tracker: StateTracker,
        rollback_callback: Callable[[str], Awaitable[None]],
    ) -> None:
        """Initialize timeout watcher.

        Args:
            state_tracker: StateTracker to monitor
            rollback_callback: Async function to call on timeout (receives state_id)
        """
        self.state_tracker = state_tracker
        self.rollback_callback = rollback_callback
        self._tasks: dict[str, asyncio.Task] = {}
        self._cancelled: set[str] = set()

    async def watch(self, state_id: str) -> None:
        """Watch a pending state until timeout or cancellation.

        This is a long-running coroutine that should be run as a task.
        It checks the state periodically and triggers rollback if expired.

        Args:
            state_id: State to watch

        Example:
            ```python
            watcher = TimeoutWatcher(tracker, rollback_func)
            task = asyncio.create_task(watcher.watch(state_id))
            # ... later ...
            watcher.cancel(state_id)
            await task
            ```
        """
        # Store task reference
        self._tasks[state_id] = asyncio.current_task()  # type: ignore[assignment]

        try:
            while state_id not in self._cancelled:
                # Get current state
                state = self.state_tracker.get_state(state_id)

                if not state:
                    # State was removed (confirmed or rolled back externally)
                    break

                if state.is_expired():
                    # Timeout expired - trigger rollback
                    await self.rollback_callback(state_id)
                    break

                # Calculate sleep time (check more frequently as we approach timeout)
                time_remaining = state.time_remaining()
                if time_remaining.total_seconds() <= 0:
                    # Just expired
                    await self.rollback_callback(state_id)
                    break

                # Sleep for a bit, but not more than 10 seconds
                sleep_time = min(10, time_remaining.total_seconds() / 2)
                await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            # Task was cancelled (normal during shutdown or confirmation)
            pass
        finally:
            # Clean up
            self._tasks.pop(state_id, None)
            self._cancelled.discard(state_id)

    def cancel(self, state_id: str) -> None:
        """Cancel watching a state (called when user confirms).

        Args:
            state_id: State to stop watching
        """
        self._cancelled.add(state_id)

        # Cancel the task if it exists
        task = self._tasks.get(state_id)
        if task and not task.done():
            task.cancel()

    def get_time_remaining(self, state_id: str) -> timedelta | None:
        """Get time remaining until timeout for a state.

        Args:
            state_id: State to check

        Returns:
            Time remaining or None if not being watched
        """
        if state_id not in self._tasks:
            return None

        state = self.state_tracker.get_state(state_id)
        if not state:
            return None

        return state.time_remaining()

    def is_watching(self, state_id: str) -> bool:
        """Check if actively watching a state.

        Args:
            state_id: State to check

        Returns:
            True if currently watching
        """
        task = self._tasks.get(state_id)
        return task is not None and not task.done()
