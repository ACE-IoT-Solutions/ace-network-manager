"""Main orchestrator for network configuration management."""

import asyncio
import hashlib
from datetime import timedelta
from pathlib import Path

from ace_network_manager.backup.manager import BackupManager
from ace_network_manager.core.constants import (
    DEFAULT_BACKUP_DIR,
    DEFAULT_CONFIG_DIR,
    DEFAULT_NETPLAN_APPLY_TIMEOUT,
    DEFAULT_STATE_DIR,
    DEFAULT_TIMEOUT_SECONDS,
)
from ace_network_manager.core.exceptions import BackupError, NetworkError, StateError
from ace_network_manager.network.backend import NetplanBackend
from ace_network_manager.network.connectivity import ConnectivityChecker
from ace_network_manager.network.validator import NetplanValidator
from ace_network_manager.state.models import ApplyResult, StateStatus
from ace_network_manager.state.tracker import StateTracker
from ace_network_manager.systemd.integration import SystemdIntegration
from ace_network_manager.watcher.confirmation import ConfirmationHandler
from ace_network_manager.watcher.timeout import TimeoutWatcher


class NetworkConfigManager:
    """Main orchestrator for network configuration management.

    This class coordinates all operations including applying configs,
    managing state, handling timeouts, and orchestrating rollbacks.
    """

    def __init__(
        self,
        state_dir: Path = DEFAULT_STATE_DIR,
        backup_dir: Path = DEFAULT_BACKUP_DIR,
        config_dir: Path = DEFAULT_CONFIG_DIR,
        default_timeout: timedelta = timedelta(seconds=DEFAULT_TIMEOUT_SECONDS),
    ) -> None:
        """Initialize the manager with directory paths and defaults.

        Args:
            state_dir: Directory for state tracking
            backup_dir: Directory for backups
            config_dir: Netplan configuration directory
            default_timeout: Default timeout for confirmations
        """
        self.state_tracker = StateTracker(state_dir=state_dir)
        self.backup_manager = BackupManager(backup_dir=backup_dir, config_dir=config_dir)
        self.netplan_backend = NetplanBackend(config_dir=config_dir)
        self.connectivity_checker = ConnectivityChecker()
        self.systemd = SystemdIntegration()
        self.default_timeout = default_timeout

        # Timeout watcher will be created when needed
        self._timeout_watcher: TimeoutWatcher | None = None

    async def apply_config(
        self,
        config_path: Path,
        timeout: timedelta | None = None,
        skip_connectivity_check: bool = False,
    ) -> ApplyResult:
        """Apply a network configuration with automatic rollback protection.

        Steps:
        1. Validate config file syntax
        2. Create backup of current configuration
        3. Create state tracking semaphore
        4. Apply new configuration via netplan
        5. Start timeout watcher
        6. Install systemd restoration service
        7. Check network connectivity (unless skipped)
        8. Return result with state ID for confirmation

        Args:
            config_path: Path to new netplan YAML config
            timeout: How long to wait for confirmation (default: 5 minutes)
            skip_connectivity_check: Skip network validation (dangerous!)

        Returns:
            ApplyResult with success status and state information

        Raises:
            ValidationError: Config file invalid
            BackupError: Cannot create backup
            NetworkError: Cannot apply configuration
            StateError: Cannot create state
        """
        config_path = Path(config_path)
        timeout = timeout or self.default_timeout
        errors: list[str] = []

        # Step 1: Validate configuration
        validation_result = NetplanValidator.validate_file(config_path)
        if not validation_result.valid:
            return ApplyResult(
                success=False,
                backup_path=Path("/dev/null"),
                state_id="",
                message="Configuration validation failed",
                timeout_seconds=0,
                errors=validation_result.errors,
            )

        # Step 2: Create backup
        try:
            backup_path, backup_metadata = self.backup_manager.create_backup(
                description=f"Before applying {config_path.name}"
            )
        except BackupError as e:
            return ApplyResult(
                success=False,
                backup_path=Path("/dev/null"),
                state_id="",
                message=f"Backup failed: {e}",
                timeout_seconds=0,
                errors=[str(e)],
            )

        # Calculate config hashes
        original_hash = self._calculate_hash(backup_path / config_path.name)
        new_hash = self._calculate_hash(config_path)

        # Step 3: Create pending state
        try:
            state = self.state_tracker.create_pending_state(
                backup_path=backup_path,
                config_path=config_path,
                timeout=timeout,
                original_hash=original_hash,
                new_hash=new_hash,
                metadata={
                    "config_file": str(config_path),
                    "backup_id": backup_metadata.backup_id,
                },
            )
        except StateError as e:
            return ApplyResult(
                success=False,
                backup_path=backup_path,
                state_id="",
                message=f"State creation failed: {e}",
                timeout_seconds=0,
                errors=[str(e)],
            )

        # Step 4: Clear existing configs and copy new one to netplan directory
        try:
            import shutil

            # Remove all existing YAML files first
            # This ensures netplan apply only processes our new config
            for existing_yaml in self.netplan_backend.config_dir.glob("*.yaml"):
                existing_yaml.unlink()

            # Copy new config
            dest = self.netplan_backend.config_dir / config_path.name
            shutil.copy2(config_path, dest)
        except Exception as e:
            # If copy fails, we should try to restore the backup immediately
            try:
                self.backup_manager.restore_backup(backup_path, verify=False)
            except Exception:
                pass  # We'll report the original error

            return ApplyResult(
                success=False,
                backup_path=backup_path,
                state_id=state.state_id,
                message=f"Failed to replace config: {e}",
                timeout_seconds=0,
                errors=[str(e)],
            )

        # Step 5: Apply configuration
        try:
            await self.netplan_backend.apply_config(timeout=DEFAULT_NETPLAN_APPLY_TIMEOUT)
        except NetworkError as e:
            # Rollback immediately
            await self._perform_rollback(state.state_id, reason="apply_failed")
            return ApplyResult(
                success=False,
                backup_path=backup_path,
                state_id=state.state_id,
                message=f"netplan apply failed: {e}",
                timeout_seconds=0,
                errors=[str(e)],
            )

        # Step 6: Check connectivity (unless skipped)
        if not skip_connectivity_check:
            # Determine if the config uses DHCP on any interface
            config_uses_dhcp = self._config_uses_dhcp(validation_result.config)

            connectivity_result = await self.connectivity_checker.check_connectivity(
                check_gateway=True,
                check_dns=True,
                check_internet=False,  # Don't require internet
                timeout=10,
                dhcp_timeout=30,  # Give DHCP time to complete
                config_uses_dhcp=config_uses_dhcp,
            )

            if not connectivity_result.success:
                # Connectivity failed - rollback
                await self._perform_rollback(state.state_id, reason="connectivity_check_failed")

                # Build detailed error message
                error_msg = "Connectivity check failed:\n"
                for failure in connectivity_result.failures:
                    error_msg += f"  - {failure}\n"

                return ApplyResult(
                    success=False,
                    backup_path=backup_path,
                    state_id=state.state_id,
                    message=error_msg.strip(),
                    timeout_seconds=0,
                    errors=connectivity_result.failures,
                )

        # Step 7: Install systemd restoration service
        try:
            self.systemd.install_restoration_service(state.state_id)
        except Exception:
            # Non-critical - continue even if systemd setup fails
            pass

        # Step 8: Start timeout watcher
        self._start_timeout_watcher(state.state_id)

        # Step 9: Show confirmation prompt
        ConfirmationHandler.prompt_for_confirmation(
            state_id=state.state_id,
            timeout=timeout,
            config_path=str(config_path),
        )

        return ApplyResult(
            success=True,
            backup_path=backup_path,
            state_id=state.state_id,
            message="Configuration applied successfully - confirmation required",
            timeout_seconds=int(timeout.total_seconds()),
            errors=[],
        )

    async def confirm(self, state_id: str | None = None) -> bool:
        """Confirm that a pending configuration is working correctly.

        This stops the timeout watcher, removes the systemd restoration
        service, and marks the configuration as confirmed in state.

        Args:
            state_id: Optional specific state to confirm (default: latest)

        Returns:
            True if confirmed successfully

        Raises:
            StateError: No pending state to confirm
        """
        # Get state to confirm
        if state_id:
            state = self.state_tracker.get_state(state_id)
        else:
            state = self.state_tracker.get_pending_state()

        if not state:
            msg = "No pending configuration to confirm"
            raise StateError(msg)

        if state.status != StateStatus.PENDING:
            msg = f"State {state.state_id} is not pending (current status: {state.status})"
            raise StateError(msg)

        # Cancel timeout watcher
        if self._timeout_watcher:
            self._timeout_watcher.cancel(state.state_id)

        # Remove systemd service
        self.systemd.remove_restoration_service(state.state_id)

        # Mark as confirmed
        self.state_tracker.confirm_state(state.state_id)

        # Show success message
        ConfirmationHandler.show_confirmed()

        return True

    async def rollback(
        self,
        state_id: str | None = None,
        to_backup: Path | None = None,
    ) -> bool:
        """Manually rollback to a previous configuration.

        Args:
            state_id: Rollback to state with this ID (default: latest pending)
            to_backup: Specific backup directory to restore (overrides state_id)

        Returns:
            True if rollback successful

        Raises:
            BackupError: Cannot restore backup
            NetworkError: Cannot apply backup configuration
        """
        if to_backup:
            # Direct backup restoration
            self.backup_manager.restore_backup(to_backup, verify=True)
            await self.netplan_backend.apply_config()
            ConfirmationHandler.show_rolled_back(reason="manual_rollback")
            return True

        # Get state to rollback
        if state_id:
            state = self.state_tracker.get_state(state_id)
        else:
            state = self.state_tracker.get_pending_state()

        if not state:
            msg = "No state to rollback"
            raise StateError(msg)

        # Perform rollback
        await self._perform_rollback(state.state_id, reason="manual")

        return True

    def get_status(self) -> dict:
        """Get current status of the network configuration system.

        Returns:
            Dictionary with current state information
        """
        pending = self.state_tracker.get_pending_state()

        if pending:
            return {
                "current_state": "pending_confirmation",
                "state_id": pending.state_id,
                "pending_since": pending.created_at.isoformat(),
                "timeout_at": pending.timeout_at.isoformat(),
                "time_remaining_seconds": int(pending.time_remaining().total_seconds()),
                "config_path": str(pending.config_path),
                "backup_path": str(pending.backup_path),
                "systemd_armed": self.systemd.is_service_enabled(pending.state_id),
            }

        return {
            "current_state": "idle",
            "state_id": None,
            "last_backup": str(self.backup_manager.backup_dir / "latest")
            if (self.backup_manager.backup_dir / "latest").exists()
            else None,
        }

    def list_backups(self, limit: int = 10) -> list[Path]:
        """List available backup directories, newest first.

        Args:
            limit: Maximum number of backups to return

        Returns:
            List of backup directory paths
        """
        backups = self.backup_manager.list_backups()
        return [path for path, _ in backups[:limit]]

    async def _perform_rollback(self, state_id: str, reason: str) -> None:
        """Internal method to perform rollback.

        Args:
            state_id: State to rollback
            reason: Reason for rollback
        """
        state = self.state_tracker.get_state(state_id)
        if not state:
            return

        # Cancel timeout watcher
        if self._timeout_watcher:
            self._timeout_watcher.cancel(state_id)

        try:
            # Restore backup
            self.backup_manager.restore_backup(state.backup_path, verify=True)

            # Apply restored config
            await self.netplan_backend.apply_config()

            # Mark as rolled back
            self.state_tracker.mark_rolled_back(state_id, reason=reason)

            # Remove systemd service
            self.systemd.remove_restoration_service(state_id)

            # Show message
            ConfirmationHandler.show_rolled_back(reason=reason)

        except Exception as e:
            # Rollback failed - this is critical
            print(f"\nCRITICAL: Rollback failed: {e}")
            print("Manual intervention required!")
            raise

    def _start_timeout_watcher(self, state_id: str) -> None:
        """Start watching a state for timeout.

        Args:
            state_id: State to watch
        """
        if not self._timeout_watcher:
            self._timeout_watcher = TimeoutWatcher(
                state_tracker=self.state_tracker,
                rollback_callback=lambda sid: self._perform_rollback(sid, "timeout_expired"),
            )

        # Start watching in background
        asyncio.create_task(self._timeout_watcher.watch(state_id))

    @staticmethod
    def _config_uses_dhcp(config) -> bool:  # noqa: ANN001
        """Check if a netplan config uses DHCP on any interface.

        Args:
            config: NetplanConfig object

        Returns:
            True if any interface uses DHCP (dhcp4 or dhcp6)
        """
        if not config or not config.network:
            return False

        # Check ethernet interfaces
        for iface in config.network.ethernets.values():
            if iface.dhcp4 or iface.dhcp6:
                return True

        # Check VLAN interfaces
        if config.network.vlans:
            for vlan in config.network.vlans.values():
                if vlan.dhcp4 or vlan.dhcp6:
                    return True

        # Check bond interfaces
        if config.network.bonds:
            for bond in config.network.bonds.values():
                if bond.dhcp4 or bond.dhcp6:
                    return True

        # Check bridge interfaces
        if config.network.bridges:
            for bridge in config.network.bridges.values():
                if bridge.dhcp4 or bridge.dhcp6:
                    return True

        return False

    @staticmethod
    def _calculate_hash(file_path: Path) -> str:
        """Calculate SHA256 hash of a file.

        Args:
            file_path: File to hash

        Returns:
            Hex digest
        """
        if not file_path.exists():
            return ""

        sha256 = hashlib.sha256()
        with file_path.open("rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()
