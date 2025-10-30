"""System-wide constants for ACE Network Manager."""

from pathlib import Path

# Default directories
DEFAULT_STATE_DIR = Path("/var/lib/ace-network-manager/state")
DEFAULT_BACKUP_DIR = Path("/var/lib/ace-network-manager/backups")
DEFAULT_CONFIG_DIR = Path("/etc/netplan")
DEFAULT_SYSTEMD_DIR = Path("/etc/systemd/system")
DEFAULT_LOG_DIR = Path("/var/log/ace-network-manager")

# Default timeouts (in seconds)
DEFAULT_TIMEOUT_SECONDS = 300  # 5 minutes
DEFAULT_NETPLAN_APPLY_TIMEOUT = 30
DEFAULT_CONNECTIVITY_CHECK_TIMEOUT = 10

# State file names
STATE_PENDING_DIR = "pending"
STATE_ARCHIVE_DIR = "archive"
LATEST_BACKUP_LINK = "latest"

# Systemd service
SYSTEMD_SERVICE_PREFIX = "ace-network-manager-restore"

# File permissions
STATE_FILE_PERMS = 0o600  # root only
BACKUP_DIR_PERMS = 0o700  # root only
CONFIG_FILE_PERMS = 0o644  # world-readable, root writable
