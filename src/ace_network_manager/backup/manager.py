"""Backup manager for network configurations."""

import hashlib
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from ace_network_manager.core.constants import (
    BACKUP_DIR_PERMS,
    CONFIG_FILE_PERMS,
    DEFAULT_BACKUP_DIR,
    DEFAULT_CONFIG_DIR,
    LATEST_BACKUP_LINK,
)
from ace_network_manager.core.exceptions import BackupError
from ace_network_manager.state.models import BackupMetadata
from ace_network_manager.utils.filesystem import (
    atomic_write_json,
    create_symlink,
    ensure_dir,
    safe_read_json,
)


class BackupManager:
    """Manages timestamped backups of network configurations.

    Creates directory-based backups with uncompressed YAML files
    for human readability and easy debugging.

    Backup structure:
        {backup_dir}/
            YYYY-MM-DD-HHMMSS-{uuid}/
                metadata.json
                00-installer-config.yaml
                01-network.yaml
                checksums.sha256
            latest -> YYYY-MM-DD-HHMMSS-{uuid}/
    """

    def __init__(
        self,
        backup_dir: Path = DEFAULT_BACKUP_DIR,
        config_dir: Path = DEFAULT_CONFIG_DIR,
    ) -> None:
        """Initialize backup manager.

        Args:
            backup_dir: Where to store backups
            config_dir: Source directory for netplan configs
        """
        self.backup_dir = Path(backup_dir)
        self.config_dir = Path(config_dir)

        # Ensure backup directory exists
        ensure_dir(self.backup_dir, mode=BACKUP_DIR_PERMS)

    def create_backup(
        self,
        description: str | None = None,
    ) -> tuple[Path, BackupMetadata]:
        """Create a new backup of all netplan configurations.

        Steps:
        1. Find all .yaml files in config_dir
        2. Create timestamped backup directory
        3. Copy YAML files preserving names
        4. Calculate checksums
        5. Write metadata.json
        6. Update 'latest' symlink

        Args:
            description: Optional description to store in metadata

        Returns:
            Tuple of (backup_path, metadata)

        Raises:
            BackupError: Cannot create or verify backup
        """
        # Find all netplan YAML files
        yaml_files = sorted(self.config_dir.glob("*.yaml"))
        if not yaml_files:
            msg = f"No netplan YAML files found in {self.config_dir}"
            raise BackupError(msg)

        # Create backup directory with timestamp and UUID
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        backup_id = str(uuid.uuid4())[:8]
        backup_name = f"{timestamp}-{backup_id}"
        backup_path = self.backup_dir / backup_name

        try:
            ensure_dir(backup_path, mode=BACKUP_DIR_PERMS)
        except Exception as e:
            msg = f"Cannot create backup directory: {e}"
            raise BackupError(msg) from e

        # Copy files and calculate checksums
        checksums: dict[str, str] = {}
        source_configs: list[str] = []

        for yaml_file in yaml_files:
            filename = yaml_file.name
            dest_file = backup_path / filename

            try:
                # Copy file
                shutil.copy2(yaml_file, dest_file)
                dest_file.chmod(CONFIG_FILE_PERMS)

                # Calculate checksum
                checksum = self._calculate_checksum(dest_file)
                checksums[filename] = checksum
                source_configs.append(filename)

            except Exception as e:
                msg = f"Failed to backup {filename}: {e}"
                raise BackupError(msg) from e

        # Gather system info
        import platform
        import subprocess

        system_info = {
            "hostname": platform.node(),
            "os_version": f"{platform.system()} {platform.release()}",
        }

        # Try to get netplan version
        try:
            result = subprocess.run(
                ["netplan", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                system_info["netplan_version"] = result.stdout.strip()
        except Exception:
            pass

        # Create metadata
        metadata = BackupMetadata(
            backup_id=backup_id,
            created_at=datetime.now(),
            description=description,
            source_configs=source_configs,
            checksums=checksums,
            system_info=system_info,
        )

        # Write metadata
        metadata_file = backup_path / "metadata.json"
        try:
            atomic_write_json(metadata_file, metadata.to_dict(), mode=CONFIG_FILE_PERMS)
        except Exception as e:
            msg = f"Failed to write metadata: {e}"
            raise BackupError(msg) from e

        # Write checksums file for human readability
        checksums_file = backup_path / "checksums.sha256"
        checksums_content = "\n".join(
            f"{checksum}  {filename}" for filename, checksum in checksums.items()
        )
        checksums_file.write_text(checksums_content + "\n")
        checksums_file.chmod(CONFIG_FILE_PERMS)

        # Update 'latest' symlink
        latest_link = self.backup_dir / LATEST_BACKUP_LINK
        try:
            create_symlink(backup_path, latest_link, force=True)
        except Exception:
            # Non-critical error, continue
            pass

        return backup_path, metadata

    def restore_backup(
        self,
        backup_path: Path,
        verify: bool = True,
    ) -> None:
        """Restore network configuration from a backup.

        Steps:
        1. Verify backup integrity (if verify=True)
        2. Validate YAML files
        3. Copy files to /etc/netplan atomically
        4. Restore file permissions

        Args:
            backup_path: Path to backup directory
            verify: Whether to verify checksums before restore

        Raises:
            BackupError: Backup corrupt, invalid, or cannot restore
        """
        backup_path = Path(backup_path)

        if not backup_path.exists():
            msg = f"Backup directory not found: {backup_path}"
            raise BackupError(msg)

        if not backup_path.is_dir():
            msg = f"Backup path is not a directory: {backup_path}"
            raise BackupError(msg)

        # Load metadata
        metadata_file = backup_path / "metadata.json"
        metadata_data = safe_read_json(metadata_file)

        if not metadata_data:
            msg = f"Backup metadata not found or invalid: {metadata_file}"
            raise BackupError(msg)

        try:
            metadata = BackupMetadata.from_dict(metadata_data)
        except Exception as e:
            msg = f"Invalid backup metadata: {e}"
            raise BackupError(msg) from e

        # Verify checksums if requested
        if verify:
            for filename, expected_checksum in metadata.checksums.items():
                file_path = backup_path / filename
                if not file_path.exists():
                    msg = f"Backup file missing: {filename}"
                    raise BackupError(msg)

                actual_checksum = self._calculate_checksum(file_path)
                if actual_checksum != expected_checksum:
                    msg = f"Checksum mismatch for {filename}: backup is corrupted"
                    raise BackupError(msg)

        # Validate YAML files before copying
        from ace_network_manager.network.validator import NetplanValidator

        for filename in metadata.source_configs:
            file_path = backup_path / filename
            result = NetplanValidator.validate_file(file_path)
            if not result.valid:
                msg = f"Backup contains invalid config {filename}:\n"
                for error in result.errors:
                    msg += f"  - {error}\n"
                raise BackupError(msg)

        # Remove all existing YAML files from config directory
        # This ensures we don't have leftover configs that would interfere
        try:
            for existing_yaml in self.config_dir.glob("*.yaml"):
                existing_yaml.unlink()
        except Exception as e:
            msg = f"Failed to clear config directory: {e}"
            raise BackupError(msg) from e

        # Copy files to config directory
        for filename in metadata.source_configs:
            source_file = backup_path / filename
            dest_file = self.config_dir / filename

            try:
                # Atomic copy via temp file
                temp_file = dest_file.with_suffix(dest_file.suffix + ".tmp")
                shutil.copy2(source_file, temp_file)
                temp_file.chmod(CONFIG_FILE_PERMS)
                temp_file.replace(dest_file)
            except Exception as e:
                msg = f"Failed to restore {filename}: {e}"
                raise BackupError(msg) from e

    def list_backups(self) -> list[tuple[Path, BackupMetadata]]:
        """List all available backups with metadata.

        Returns:
            List of (path, metadata) tuples, newest first
        """
        backups: list[tuple[Path, BackupMetadata]] = []

        # Find all backup directories
        for backup_dir in sorted(self.backup_dir.iterdir(), reverse=True):
            if not backup_dir.is_dir():
                continue

            # Skip the 'latest' symlink
            if backup_dir.name == LATEST_BACKUP_LINK:
                continue

            # Load metadata
            metadata_file = backup_dir / "metadata.json"
            metadata_data = safe_read_json(metadata_file)

            if not metadata_data:
                continue

            try:
                metadata = BackupMetadata.from_dict(metadata_data)
                backups.append((backup_dir, metadata))
            except Exception:
                # Skip invalid backups
                continue

        return backups

    def verify_backup(self, backup_path: Path) -> bool:
        """Verify a backup's integrity via checksums.

        Args:
            backup_path: Backup to verify

        Returns:
            True if backup is valid
        """
        try:
            backup_path = Path(backup_path)

            # Load metadata
            metadata_file = backup_path / "metadata.json"
            metadata_data = safe_read_json(metadata_file)
            if not metadata_data:
                return False

            metadata = BackupMetadata.from_dict(metadata_data)

            # Verify checksums
            for filename, expected_checksum in metadata.checksums.items():
                file_path = backup_path / filename
                if not file_path.exists():
                    return False

                actual_checksum = self._calculate_checksum(file_path)
                if actual_checksum != expected_checksum:
                    return False

            return True

        except Exception:
            return False

    def cleanup_old_backups(
        self,
        keep_count: int = 20,
        keep_days: int = 90,
    ) -> int:
        """Remove old backups based on retention policy.

        Keeps at least keep_count most recent backups, and all
        backups from the last keep_days days.

        Args:
            keep_count: Minimum number of backups to keep
            keep_days: Keep all backups from last N days

        Returns:
            Number of backups deleted
        """
        backups = self.list_backups()

        if len(backups) <= keep_count:
            return 0  # Keep all if under minimum

        cutoff = datetime.now() - timedelta(days=keep_days)
        removed = 0

        # Sort by creation time
        backups.sort(key=lambda x: x[1].created_at, reverse=True)

        # Keep first keep_count backups
        for i, (backup_path, metadata) in enumerate(backups):
            if i < keep_count:
                continue  # Keep minimum count

            if metadata.created_at >= cutoff:
                continue  # Keep recent backups

            # Remove this backup
            try:
                shutil.rmtree(backup_path)
                removed += 1
            except Exception:
                # Continue even if deletion fails
                pass

        return removed

    @staticmethod
    def _calculate_checksum(file_path: Path) -> str:
        """Calculate SHA256 checksum of a file.

        Args:
            file_path: File to checksum

        Returns:
            Hex digest of SHA256 hash
        """
        sha256 = hashlib.sha256()
        with file_path.open("rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()
