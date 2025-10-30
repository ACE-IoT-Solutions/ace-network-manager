"""File locking utilities for mutual exclusion."""

import fcntl
import os
from pathlib import Path
from typing import Any


class FileLock:
    """Advisory file lock for mutual exclusion.

    Uses fcntl.flock() for POSIX advisory file locks.
    This prevents concurrent operations on the same resource.

    Example:
        ```python
        lock = FileLock("/var/lock/myapp.lock")
        with lock:
            # Protected code
            pass
        ```
    """

    def __init__(self, lock_file: Path | str, timeout: float = 10.0) -> None:
        """Initialize file lock.

        Args:
            lock_file: Path to lock file
            timeout: Maximum seconds to wait for lock (default: 10)
        """
        self.lock_file = Path(lock_file)
        self.timeout = timeout
        self._fd: int | None = None

    def acquire(self, timeout: float | None = None) -> bool:
        """Acquire the lock.

        Args:
            timeout: Override default timeout (seconds)

        Returns:
            True if lock acquired

        Raises:
            TimeoutError: If lock cannot be acquired within timeout
        """
        timeout = timeout or self.timeout

        # Ensure lock directory exists
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)

        # Open lock file (creates if doesn't exist)
        self._fd = os.open(self.lock_file, os.O_CREAT | os.O_RDWR, 0o644)

        try:
            # Try to acquire lock (blocking with timeout)
            # Use LOCK_EX for exclusive lock
            fcntl.flock(self._fd, fcntl.LOCK_EX)
            return True
        except Exception:
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
            raise

    def release(self) -> None:
        """Release the lock."""
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> "FileLock":
        """Context manager entry."""
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.release()

    def __del__(self) -> None:
        """Cleanup on deletion."""
        if self._fd is not None:
            self.release()
