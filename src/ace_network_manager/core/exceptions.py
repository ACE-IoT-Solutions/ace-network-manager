"""Exception hierarchy for network manager."""


class NetworkManagerError(Exception):
    """Base exception for all network manager errors."""


class ValidationError(NetworkManagerError):
    """Configuration validation failed."""


class SubnetOverlapError(ValidationError):
    """Subnet overlap detected between interfaces.

    Attributes:
        interface1: First interface name
        interface2: Second interface name
        subnet1: First interface subnet (CIDR notation)
        subnet2: Second interface subnet (CIDR notation)
    """

    def __init__(
        self,
        interface1: str,
        subnet1: str,
        interface2: str,
        subnet2: str,
        message: str | None = None,
    ) -> None:
        """Initialize subnet overlap error.

        Args:
            interface1: First interface name
            subnet1: First interface subnet
            interface2: Second interface name
            subnet2: Second interface subnet
            message: Optional custom message
        """
        self.interface1 = interface1
        self.subnet1 = subnet1
        self.interface2 = interface2
        self.subnet2 = subnet2

        if message is None:
            if interface1 == interface2 and subnet1 == subnet2:
                message = (
                    f"Duplicate subnet on interface '{interface1}': "
                    f"subnet {subnet1} is defined multiple times"
                )
            else:
                message = (
                    f"Subnet overlap detected: interface '{interface1}' ({subnet1}) "
                    f"overlaps with interface '{interface2}' ({subnet2})"
                )

        super().__init__(message)


class DuplicateAddressError(ValidationError):
    """Duplicate IP address detected on same interface.

    Attributes:
        interface: Interface name
        address: Duplicate IP address
    """

    def __init__(self, interface: str, address: str, message: str | None = None) -> None:
        """Initialize duplicate address error.

        Args:
            interface: Interface name
            address: Duplicate IP address
            message: Optional custom message
        """
        self.interface = interface
        self.address = address

        if message is None:
            message = (
                f"Duplicate address on interface '{interface}': {address} is defined multiple times"
            )

        super().__init__(message)


class BackupError(NetworkManagerError):
    """Backup creation or restoration failed."""


class StateError(NetworkManagerError):
    """State tracking or semaphore operation failed."""


class NetworkError(NetworkManagerError):
    """Network operation (apply, connectivity check) failed."""


class SystemdError(NetworkManagerError):
    """Systemd integration operation failed."""
