"""Background monitoring daemon for pending configurations."""

import asyncio
import logging
import signal
from pathlib import Path

from ace_network_manager.core.constants import DEFAULT_STATE_DIR
from ace_network_manager.core.manager import NetworkConfigManager
from ace_network_manager.state.models import StateStatus
from ace_network_manager.state.tracker import StateTracker

# Set up logging for daemon
logger = logging.getLogger(__name__)


class ConfigMonitorDaemon:
    """Background daemon that monitors pending states and triggers rollbacks.

    This daemon runs continuously in the background, checking for pending
    network configurations and automatically rolling them back if they
    expire without confirmation.
    """

    def __init__(
        self,
        state_dir: Path = DEFAULT_STATE_DIR,
        check_interval: int = 5,
    ) -> None:
        """Initialize the daemon.

        Args:
            state_dir: Directory containing state files
            check_interval: Seconds between state checks
        """
        self.state_tracker = StateTracker(state_dir=state_dir)
        self.manager = NetworkConfigManager(state_dir=state_dir)
        self.check_interval = check_interval
        self._running = False
        self._monitored_states: dict[str, asyncio.Task] = {}

    async def run(self) -> None:
        """Run the daemon main loop.

        This continuously checks for pending states and monitors them
        until they expire or are confirmed.
        """
        self._running = True

        # Set up signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))

        logger.info("ACE Network Manager daemon started")
        logger.info(f"Monitoring state directory: {self.state_tracker.state_dir}")
        logger.info(f"Check interval: {self.check_interval}s")

        # Clean up any stale systemd restoration services
        try:
            from ace_network_manager.systemd.integration import SystemdIntegration

            systemd = SystemdIntegration()
            cleaned = systemd.cleanup_stale_services()
            if cleaned:
                logger.info(f"Cleaned up {len(cleaned)} stale restoration service(s)")
        except Exception as e:
            logger.warning(f"Failed to clean up stale services: {e}")

        try:
            while self._running:
                # Find all pending states
                pending_states = [
                    state
                    for state in self.state_tracker.list_states()
                    if state.status == StateStatus.PENDING
                ]

                # Monitor any new pending states
                for state in pending_states:
                    if state.state_id not in self._monitored_states:
                        # Start monitoring this state
                        logger.info(f"Found pending state: {state.state_id}")
                        logger.info(f"  Timeout at: {state.timeout_at}")
                        logger.info(f"  Time remaining: {state.time_remaining()}")
                        task = asyncio.create_task(self._monitor_state(state.state_id))
                        self._monitored_states[state.state_id] = task

                # Clean up completed tasks
                completed = [
                    state_id for state_id, task in self._monitored_states.items() if task.done()
                ]
                for state_id in completed:
                    self._monitored_states.pop(state_id)

                # Sleep before next check
                await asyncio.sleep(self.check_interval)

        except asyncio.CancelledError:
            logger.info("Daemon shutting down...")
        finally:
            # Cancel all monitoring tasks
            for task in self._monitored_states.values():
                task.cancel()
            if self._monitored_states:
                await asyncio.gather(*self._monitored_states.values(), return_exceptions=True)

    async def _monitor_state(self, state_id: str) -> None:
        """Monitor a specific state until it expires or is confirmed.

        Args:
            state_id: State to monitor
        """
        try:
            while self._running:
                state = self.state_tracker.get_state(state_id)

                if not state:
                    # State was removed (confirmed or rolled back)
                    logger.info(f"State {state_id} no longer exists (confirmed or rolled back)")
                    break

                if state.status != StateStatus.PENDING:
                    # State was confirmed or rolled back
                    logger.info(f"State {state_id} status changed to {state.status}")
                    break

                if state.is_expired():
                    # Timeout expired - trigger rollback
                    logger.warning(f"State {state_id} expired! Triggering automatic rollback...")
                    try:
                        await self.manager._perform_rollback(state_id, "timeout_expired")
                        logger.info(f"Automatic rollback completed for {state_id}")
                    except Exception as e:
                        logger.error(f"Rollback failed for {state_id}: {e}")
                    break

                # Calculate sleep time (check more frequently as we approach timeout)
                time_remaining = state.time_remaining()
                if time_remaining.total_seconds() <= 0:
                    # Just expired
                    logger.warning(f"State {state_id} just expired! Triggering rollback...")
                    try:
                        await self.manager._perform_rollback(state_id, "timeout_expired")
                        logger.info(f"Automatic rollback completed for {state_id}")
                    except Exception as e:
                        logger.error(f"Rollback failed for {state_id}: {e}")
                    break

                # Sleep for a bit, but not more than the check interval
                sleep_time = min(self.check_interval, max(1, time_remaining.total_seconds() / 2))
                await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            logger.info(f"Monitoring cancelled for state {state_id}")
        except Exception as e:
            logger.error(f"Error monitoring state {state_id}: {e}")

    async def shutdown(self) -> None:
        """Gracefully shutdown the daemon."""
        logger.info("Shutdown signal received")
        self._running = False

    @staticmethod
    def check_if_running() -> bool:
        """Check if daemon is currently running.

        Returns:
            True if daemon is running
        """
        pid_file = Path("/var/run/ace-network-manager-daemon.pid")
        if not pid_file.exists():
            return False

        try:
            pid = int(pid_file.read_text().strip())
            # Check if process exists
            import os

            try:
                os.kill(pid, 0)
                return True
            except OSError:
                # Process doesn't exist
                return False
        except Exception:
            return False

    @staticmethod
    def write_pid_file() -> None:
        """Write PID file to track daemon."""
        import os

        pid_file = Path("/var/run/ace-network-manager-daemon.pid")
        try:
            pid_file.write_text(str(os.getpid()))
        except PermissionError:
            # Fall back to user-writable location
            pid_file = Path("/tmp/ace-network-manager-daemon.pid")
            pid_file.write_text(str(os.getpid()))

    @staticmethod
    def remove_pid_file() -> None:
        """Remove PID file."""
        for pid_file in [
            Path("/var/run/ace-network-manager-daemon.pid"),
            Path("/tmp/ace-network-manager-daemon.pid"),
        ]:
            if pid_file.exists():
                try:
                    pid_file.unlink()
                except Exception:
                    pass


async def run_daemon(state_dir: Path | None = None, check_interval: int = 5) -> None:
    """Run the monitoring daemon.

    Args:
        state_dir: State directory to monitor
        check_interval: Seconds between checks
    """
    daemon = ConfigMonitorDaemon(
        state_dir=state_dir or DEFAULT_STATE_DIR,
        check_interval=check_interval,
    )

    # Write PID file
    daemon.write_pid_file()

    try:
        await daemon.run()
    finally:
        daemon.remove_pid_file()
