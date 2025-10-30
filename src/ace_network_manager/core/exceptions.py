"""Exception hierarchy for network manager."""


class NetworkManagerError(Exception):
    """Base exception for all network manager errors."""


class ValidationError(NetworkManagerError):
    """Configuration validation failed."""


class BackupError(NetworkManagerError):
    """Backup creation or restoration failed."""


class StateError(NetworkManagerError):
    """State tracking or semaphore operation failed."""


class NetworkError(NetworkManagerError):
    """Network operation (apply, connectivity check) failed."""


class SystemdError(NetworkManagerError):
    """Systemd integration operation failed."""
