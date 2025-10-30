"""Filesystem utilities for safe atomic operations."""

import json
import os
from pathlib import Path
from typing import Any


def atomic_write(path: Path, content: str | bytes, mode: int = 0o644) -> None:
    """Write file atomically to prevent corruption on crash.

    Args:
        path: Target file path
        content: Content to write (str or bytes)
        mode: File permissions (default: 0o644)

    The file is written to a temporary file first, then atomically
    renamed to the target path. This ensures the file is never in
    a partially-written state.
    """
    path = Path(path)
    tmp_path = path.with_suffix(path.suffix + ".tmp")

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temporary file
    if isinstance(content, str):
        tmp_path.write_text(content, encoding="utf-8")
    else:
        tmp_path.write_bytes(content)

    # Set permissions before rename
    os.chmod(tmp_path, mode)

    # Atomic rename (POSIX guarantees atomicity)
    tmp_path.replace(path)


def atomic_write_json(path: Path, data: dict[str, Any], mode: int = 0o644) -> None:
    """Write JSON file atomically.

    Args:
        path: Target file path
        data: Dictionary to serialize as JSON
        mode: File permissions (default: 0o644)
    """
    content = json.dumps(data, indent=2, sort_keys=False)
    atomic_write(path, content, mode)


def safe_read_json(path: Path) -> dict[str, Any] | None:
    """Safely read JSON file, returning None if not found or invalid.

    Args:
        path: Path to JSON file

    Returns:
        Parsed JSON data or None if file doesn't exist or is invalid
    """
    path = Path(path)
    if not path.exists():
        return None

    try:
        with path.open("r") as f:
            return json.load(f)  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError):
        return None


def ensure_dir(path: Path, mode: int = 0o755) -> None:
    """Ensure directory exists with proper permissions.

    Args:
        path: Directory path
        mode: Directory permissions (default: 0o755)
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True, mode=mode)


def create_symlink(target: Path, link: Path, force: bool = True) -> None:
    """Create symbolic link, optionally overwriting existing link.

    Args:
        target: Target path (what the symlink points to)
        link: Link path (the symlink itself)
        force: If True, overwrite existing symlink
    """
    target = Path(target)
    link = Path(link)

    if force and link.exists():
        link.unlink()

    link.symlink_to(target)
