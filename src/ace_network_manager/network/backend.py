"""Network backend integration for netplan."""

import subprocess
from pathlib import Path

from ace_network_manager.core.exceptions import NetworkError


class NetplanBackend:
    """Interface to netplan for applying configurations."""

    def __init__(self, config_dir: Path = Path("/etc/netplan")) -> None:
        """Initialize netplan backend.

        Args:
            config_dir: Netplan configuration directory
        """
        self.config_dir = Path(config_dir)

    def validate_config(self, config_path: Path) -> tuple[bool, str]:
        """Validate a netplan config file syntax using netplan generate.

        Args:
            config_path: Path to YAML config

        Returns:
            (is_valid, error_message)
        """
        try:
            # Use netplan generate --dry-run to validate
            result = subprocess.run(
                ["netplan", "generate"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            if result.returncode == 0:
                return True, ""

            return False, result.stderr or result.stdout

        except subprocess.TimeoutExpired:
            return False, "Validation timed out"
        except FileNotFoundError:
            return False, "netplan command not found - is netplan installed?"
        except Exception as e:
            return False, f"Validation error: {e}"

    async def apply_config(self, timeout: int = 30) -> None:
        """Run 'netplan apply' to activate configuration.

        Args:
            timeout: Seconds to wait for apply to complete

        Raises:
            NetworkError: Apply failed
        """
        try:
            # Run netplan apply
            result = subprocess.run(
                ["netplan", "apply"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "Unknown error"
                msg = f"netplan apply failed: {error_msg}"
                raise NetworkError(msg)

        except subprocess.TimeoutExpired as e:
            msg = f"netplan apply timed out after {timeout}s"
            raise NetworkError(msg) from e
        except FileNotFoundError as e:
            msg = "netplan command not found - is netplan installed?"
            raise NetworkError(msg) from e
        except Exception as e:
            msg = f"Failed to apply network configuration: {e}"
            raise NetworkError(msg) from e

    def get_current_config(self) -> dict[str, str]:
        """Get all current netplan config files.

        Returns:
            Dictionary mapping filename to file content
        """
        configs: dict[str, str] = {}

        if not self.config_dir.exists():
            return configs

        for yaml_file in sorted(self.config_dir.glob("*.yaml")):
            try:
                configs[yaml_file.name] = yaml_file.read_text()
            except Exception:
                # Skip files we can't read
                continue

        return configs
