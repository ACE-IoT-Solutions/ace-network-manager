"""Systemd integration for post-reboot restoration."""

import subprocess
from pathlib import Path

from ace_network_manager.core.constants import DEFAULT_SYSTEMD_DIR, SYSTEMD_SERVICE_PREFIX
from ace_network_manager.core.exceptions import SystemdError
from ace_network_manager.systemd.units import RESTORATION_SERVICE_TEMPLATE


class SystemdIntegration:
    """Manages systemd services for post-reboot restoration.

    Creates temporary one-shot services that run on boot to check
    if a pending configuration was confirmed. If not, rolls back.
    """

    def __init__(self, systemd_dir: Path = DEFAULT_SYSTEMD_DIR) -> None:
        """Initialize systemd integration.

        Args:
            systemd_dir: Where to install unit files
        """
        self.systemd_dir = Path(systemd_dir)

    def install_restoration_service(self, state_id: str) -> None:
        """Install a one-shot service to check state on next boot.

        The service will:
        1. Check if state_id is still pending
        2. If pending, trigger rollback
        3. If confirmed, do nothing and disable itself

        Args:
            state_id: State to check on boot

        Raises:
            SystemdError: Cannot install or enable service
        """
        service_name = f"{SYSTEMD_SERVICE_PREFIX}-{state_id}.service"
        service_file = self.systemd_dir / service_name

        # Generate service content
        service_content = RESTORATION_SERVICE_TEMPLATE.format(state_id=state_id)

        try:
            # Write service file
            service_file.write_text(service_content)
            service_file.chmod(0o644)

            # Reload systemd
            subprocess.run(
                ["systemctl", "daemon-reload"],
                check=True,
                capture_output=True,
                timeout=10,
            )

            # Enable service
            subprocess.run(
                ["systemctl", "enable", service_name],
                check=True,
                capture_output=True,
                timeout=10,
            )

        except subprocess.CalledProcessError as e:
            msg = f"Failed to install systemd service: {e.stderr.decode() if e.stderr else e}"
            raise SystemdError(msg) from e
        except Exception as e:
            msg = f"Failed to install systemd service: {e}"
            raise SystemdError(msg) from e

    def remove_restoration_service(self, state_id: str) -> None:
        """Remove and disable the restoration service.

        Called after user confirms or manual rollback completes.

        Args:
            state_id: State whose service to remove
        """
        service_name = f"{SYSTEMD_SERVICE_PREFIX}-{state_id}.service"
        service_file = self.systemd_dir / service_name

        try:
            # Disable service (ignore errors if not enabled)
            subprocess.run(
                ["systemctl", "disable", service_name],
                capture_output=True,
                timeout=10,
                check=False,
            )

            # Remove service file
            if service_file.exists():
                service_file.unlink()

            # Reload systemd
            subprocess.run(
                ["systemctl", "daemon-reload"],
                check=True,
                capture_output=True,
                timeout=10,
            )

        except Exception:  # noqa: BLE001
            # Best effort - don't fail if cleanup doesn't work
            pass

    def check_and_restore(self, state_id: str) -> bool:
        """Check if a state needs restoration and do it if needed.

        This is called by the systemd service on boot.

        Args:
            state_id: State to check

        Returns:
            True if restoration was performed
        """
        from ace_network_manager.state.tracker import StateTracker

        tracker = StateTracker()
        state = tracker.get_state(state_id)

        if not state:
            # State doesn't exist, nothing to do
            return False

        # Check if still pending
        from ace_network_manager.state.models import StateStatus

        if state.status == StateStatus.PENDING:
            # Still pending after reboot - need to rollback
            from ace_network_manager.backup.manager import BackupManager

            backup_manager = BackupManager()

            try:
                # Restore from backup
                backup_manager.restore_backup(state.backup_path, verify=True)

                # Mark as rolled back
                tracker.mark_rolled_back(state_id, reason="boot_check_pending")

                # Remove this service
                self.remove_restoration_service(state_id)

                return True

            except Exception:  # noqa: BLE001
                # Restoration failed - leave pending for manual intervention
                return False

        # Not pending (was confirmed), clean up service
        self.remove_restoration_service(state_id)
        return False

    def is_service_enabled(self, state_id: str) -> bool:
        """Check if restoration service is enabled.

        Args:
            state_id: State to check

        Returns:
            True if service is enabled
        """
        service_name = f"{SYSTEMD_SERVICE_PREFIX}-{state_id}.service"

        try:
            result = subprocess.run(
                ["systemctl", "is-enabled", service_name],
                capture_output=True,
                timeout=5,
                check=False,
            )
            return result.returncode == 0
        except Exception:  # noqa: BLE001
            return False
