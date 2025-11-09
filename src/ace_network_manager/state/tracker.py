"""State tracking and semaphore file management."""

import uuid
from datetime import datetime, timedelta
from pathlib import Path

from ace_network_manager.core.constants import (
    DEFAULT_STATE_DIR,
    STATE_ARCHIVE_DIR,
    STATE_FILE_PERMS,
    STATE_PENDING_DIR,
)
from ace_network_manager.core.exceptions import StateError
from ace_network_manager.state.models import ConfigurationState, StateStatus
from ace_network_manager.utils.filesystem import atomic_write_json, ensure_dir, safe_read_json
from ace_network_manager.utils.locking import FileLock


class StateTracker:
    """Manages state semaphore files for tracking configuration changes.

    Uses atomic file operations and file locking to prevent races.
    Semaphore files survive reboots for recovery.

    Directory structure:
        {state_dir}/
            pending/
                {state_id}.json
            archive/
                {state_id}.json
            .lock
    """

    def __init__(self, state_dir: Path = DEFAULT_STATE_DIR) -> None:
        """Initialize state tracker.

        Args:
            state_dir: Directory for semaphore files
        """
        self.state_dir = Path(state_dir)
        self.pending_dir = self.state_dir / STATE_PENDING_DIR
        self.archive_dir = self.state_dir / STATE_ARCHIVE_DIR
        self.lock_file = self.state_dir / ".lock"

        # Ensure directories exist
        ensure_dir(self.state_dir, mode=0o700)
        ensure_dir(self.pending_dir, mode=0o700)
        ensure_dir(self.archive_dir, mode=0o700)

    def _get_lock(self) -> FileLock:
        """Get file lock for state operations."""
        return FileLock(self.lock_file, timeout=10.0)

    def create_pending_state(
        self,
        backup_path: Path,
        config_path: Path,
        timeout: timedelta,
        original_hash: str,
        new_hash: str,
        metadata: dict[str, str] | None = None,
    ) -> ConfigurationState:
        """Create a new pending state with semaphore file.

        The semaphore file is written atomically to prevent corruption
        if power is lost during write.

        Args:
            backup_path: Path to backup of previous config
            config_path: Path to new config that was applied
            timeout: How long until auto-rollback
            original_hash: SHA256 hash of original config
            new_hash: SHA256 hash of new config
            metadata: Additional metadata (user, hostname, etc.)

        Returns:
            ConfigurationState object with unique state_id

        Raises:
            StateError: Cannot write semaphore file or pending state already exists
        """
        with self._get_lock():
            # Check for existing pending state (without nested lock)
            pending_files = sorted(self.pending_dir.glob("*.json"))
            if pending_files:
                state_file = pending_files[-1]
                data = safe_read_json(state_file)
                if data:
                    try:
                        existing = ConfigurationState.from_dict(data)
                        if existing.status == StateStatus.PENDING:
                            msg = (
                                f"Cannot create new pending state: existing state {existing.state_id} "
                                f"is still pending (expires at {existing.timeout_at})"
                            )
                            raise StateError(msg)
                    except StateError:
                        # Re-raise StateError
                        raise
                    except Exception:
                        # Invalid state file, ignore
                        pass

            # Create new state
            state_id = str(uuid.uuid4())
            now = datetime.now()
            timeout_at = now + timeout

            state = ConfigurationState(
                state_id=state_id,
                status=StateStatus.PENDING,
                created_at=now,
                timeout_at=timeout_at,
                timeout_seconds=int(timeout.total_seconds()),
                backup_path=backup_path,
                config_path=config_path,
                original_config_hash=original_hash,
                new_config_hash=new_hash,
                metadata=metadata or {},
            )

            # Write state file atomically
            state_file = self.pending_dir / f"{state_id}.json"
            try:
                atomic_write_json(state_file, state.to_dict(), mode=STATE_FILE_PERMS)
            except Exception as e:
                msg = f"Failed to write state file: {e}"
                raise StateError(msg) from e

            return state

    def get_pending_state(self) -> ConfigurationState | None:
        """Get the current pending state if any exists.

        Returns:
            ConfigurationState or None if no pending state
        """
        with self._get_lock():
            # List all pending state files
            pending_files = sorted(self.pending_dir.glob("*.json"))

            if not pending_files:
                return None

            # Should only be one, but take the most recent
            state_file = pending_files[-1]

            data = safe_read_json(state_file)
            if not data:
                return None

            try:
                return ConfigurationState.from_dict(data)
            except Exception:
                # Corrupted state file, ignore it
                return None

    def get_state(self, state_id: str) -> ConfigurationState | None:
        """Get a specific state by ID.

        Args:
            state_id: State UUID to retrieve

        Returns:
            ConfigurationState or None if not found
        """
        with self._get_lock():
            # Check pending first
            state_file = self.pending_dir / f"{state_id}.json"
            data = safe_read_json(state_file)

            if not data:
                # Check archive
                state_file = self.archive_dir / f"{state_id}.json"
                data = safe_read_json(state_file)

            if not data:
                return None

            try:
                return ConfigurationState.from_dict(data)
            except Exception:
                return None

    def confirm_state(self, state_id: str) -> None:
        """Mark a state as confirmed and move to archive.

        Args:
            state_id: State to confirm

        Raises:
            StateError: State not found or not in pending status
        """
        with self._get_lock():
            # Get the state (without nested lock)
            pending_file = self.pending_dir / f"{state_id}.json"
            archive_file_check = self.archive_dir / f"{state_id}.json"

            # Try pending first
            data = safe_read_json(pending_file)
            if not data:
                # Try archive
                data = safe_read_json(archive_file_check)

            if not data:
                msg = f"State {state_id} not found"
                raise StateError(msg)

            try:
                state = ConfigurationState.from_dict(data)
            except Exception as e:
                msg = f"Invalid state data: {e}"
                raise StateError(msg) from e

            if state.status != StateStatus.PENDING:
                msg = f"State {state_id} is not pending (current status: {state.status})"
                raise StateError(msg)

            # Update state
            state.status = StateStatus.CONFIRMED
            state.confirmed_at = datetime.now()

            # Move from pending to archive
            archive_file = self.archive_dir / f"{state_id}.json"

            atomic_write_json(archive_file, state.to_dict(), mode=STATE_FILE_PERMS)

            # Remove from pending
            if pending_file.exists():
                pending_file.unlink()

    def mark_rolled_back(
        self,
        state_id: str,
        reason: str = "timeout_expired",
    ) -> None:
        """Mark a state as rolled back.

        Args:
            state_id: State that was rolled back
            reason: Why rollback occurred (timeout, manual, boot_check)

        Raises:
            StateError: State not found
        """
        with self._get_lock():
            # Get the state (without nested lock)
            pending_file = self.pending_dir / f"{state_id}.json"
            archive_file_check = self.archive_dir / f"{state_id}.json"

            # Try pending first
            data = safe_read_json(pending_file)
            if not data:
                # Try archive
                data = safe_read_json(archive_file_check)

            if not data:
                msg = f"State {state_id} not found"
                raise StateError(msg)

            try:
                state = ConfigurationState.from_dict(data)
            except Exception as e:
                msg = f"Invalid state data: {e}"
                raise StateError(msg) from e

            # Update state
            state.status = StateStatus.ROLLBACK_COMPLETE
            state.rolled_back_at = datetime.now()
            state.rollback_reason = reason

            # Move from pending to archive
            archive_file = self.archive_dir / f"{state_id}.json"

            atomic_write_json(archive_file, state.to_dict(), mode=STATE_FILE_PERMS)

            # Remove from pending
            if pending_file.exists():
                pending_file.unlink()

    def list_states(
        self,
        status: StateStatus | None = None,
        limit: int = 100,
    ) -> list[ConfigurationState]:
        """List all states, optionally filtered by status.

        Args:
            status: Filter to specific status (None = all)
            limit: Maximum number to return

        Returns:
            List of ConfigurationState objects, newest first
        """
        with self._get_lock():
            states: list[ConfigurationState] = []

            # Collect from both pending and archive
            all_files = list(self.pending_dir.glob("*.json")) + list(
                self.archive_dir.glob("*.json")
            )

            # Sort by modification time (newest first)
            all_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            for state_file in all_files[:limit]:
                data = safe_read_json(state_file)
                if not data:
                    continue

                try:
                    state = ConfigurationState.from_dict(data)

                    # Filter by status if specified
                    if status is None or state.status == status:
                        states.append(state)

                    if len(states) >= limit:
                        break
                except Exception:
                    # Skip corrupted state files
                    continue

            return states

    def cleanup_old_states(self, keep_days: int = 30) -> int:
        """Remove old archived state files.

        Args:
            keep_days: Keep states from last N days

        Returns:
            Number of states removed
        """
        with self._get_lock():
            cutoff = datetime.now() - timedelta(days=keep_days)
            removed = 0

            for state_file in self.archive_dir.glob("*.json"):
                data = safe_read_json(state_file)
                if not data:
                    # Corrupted file, remove it
                    state_file.unlink()
                    removed += 1
                    continue

                try:
                    state = ConfigurationState.from_dict(data)
                    if state.created_at < cutoff:
                        state_file.unlink()
                        removed += 1
                except Exception:
                    # Corrupted file, remove it
                    state_file.unlink()
                    removed += 1

            return removed
