"""Network configuration validation framework."""

from pathlib import Path
from typing import NamedTuple

from pydantic import ValidationError

from ace_network_manager.core.exceptions import ValidationError as ConfigValidationError
from ace_network_manager.network.models import NetplanConfig


class ValidationResult(NamedTuple):
    """Result of configuration validation."""

    valid: bool
    errors: list[str]
    warnings: list[str]
    config: NetplanConfig | None = None


class NetplanValidator:
    """Validates netplan configuration files.

    Performs comprehensive validation including:
    1. YAML syntax validation
    2. Schema validation via Pydantic models
    3. Network logic validation (gateway in subnet, no overlaps, etc.)
    4. Common error detection (10+ checks built into Pydantic models)
    """

    @staticmethod
    def validate_file(config_path: str | Path) -> ValidationResult:
        """Validate a netplan configuration file.

        Args:
            config_path: Path to netplan YAML file

        Returns:
            ValidationResult with details

        This performs all static validation checks that can be done
        without applying the configuration.
        """
        errors: list[str] = []
        warnings: list[str] = []
        config: NetplanConfig | None = None

        config_path = Path(config_path)

        # Check file exists
        if not config_path.exists():
            errors.append(f"Configuration file not found: {config_path}")
            return ValidationResult(valid=False, errors=errors, warnings=warnings)

        # Check file is readable
        if not config_path.is_file():
            errors.append(f"Path is not a file: {config_path}")
            return ValidationResult(valid=False, errors=errors, warnings=warnings)

        # Try to load and validate with Pydantic
        try:
            config = NetplanConfig.from_yaml_file(str(config_path))
        except FileNotFoundError as e:
            errors.append(f"File not found: {e}")
        except ValueError as e:
            errors.append(f"YAML parsing error: {e}")
        except ValidationError as e:
            # Check if it contains our custom exceptions with structured data
            from ace_network_manager.core.exceptions import (
                DuplicateAddressError,
                SubnetOverlapError,
            )

            # Extract all validation errors from Pydantic
            for error in e.errors():
                # Check if this error wraps one of our custom exceptions
                ctx = error.get("ctx", {})
                error_value = ctx.get("error") if ctx else None

                # Check the exception type in the error context
                if isinstance(error_value, SubnetOverlapError):
                    exc = error_value
                    errors.append(
                        f"Subnet overlap: Interface '{exc.interface1}' ({exc.subnet1}) "
                        f"overlaps with interface '{exc.interface2}' ({exc.subnet2})"
                    )
                elif isinstance(error_value, DuplicateAddressError):
                    exc = error_value
                    errors.append(
                        f"Duplicate address: Interface '{exc.interface}' has "
                        f"duplicate address {exc.address}"
                    )
                else:
                    # Standard Pydantic error formatting
                    location = " -> ".join(str(loc) for loc in error["loc"])
                    message = error["msg"]

                    # Clean up the message if it contains our exception
                    if "SubnetOverlapError:" in message:
                        # Extract our custom exception from the message
                        parts = message.split("SubnetOverlapError:", 1)
                        if len(parts) > 1:
                            errors.append(parts[1].strip())
                        else:
                            errors.append(message)
                    elif "DuplicateAddressError:" in message:
                        parts = message.split("DuplicateAddressError:", 1)
                        if len(parts) > 1:
                            errors.append(parts[1].strip())
                        else:
                            errors.append(message)
                    else:
                        errors.append(f"{location}: {message}")
        except Exception as e:
            # Check if it's one of our custom exceptions that escaped
            from ace_network_manager.core.exceptions import (
                DuplicateAddressError,
                SubnetOverlapError,
            )

            if isinstance(e, SubnetOverlapError):
                errors.append(
                    f"Subnet overlap: Interface '{e.interface1}' ({e.subnet1}) "
                    f"overlaps with interface '{e.interface2}' ({e.subnet2})"
                )
            elif isinstance(e, DuplicateAddressError):
                errors.append(
                    f"Duplicate address: Interface '{e.interface}' has "
                    f"duplicate address {e.address}"
                )
            else:
                errors.append(f"Unexpected error: {type(e).__name__}: {e}")

        # If we got this far without errors, validation passed
        valid = len(errors) == 0

        # Add warnings for best practices (even if valid)
        if config and valid:
            warnings.extend(NetplanValidator._check_best_practices(config))

        return ValidationResult(
            valid=valid, errors=errors, warnings=warnings, config=config if valid else None
        )

    @staticmethod
    def _check_best_practices(config: NetplanConfig) -> list[str]:
        """Check for best practice violations (warnings, not errors).

        Args:
            config: Validated netplan config

        Returns:
            List of warning messages
        """
        warnings: list[str] = []

        # Check for deprecated gateway4/gateway6
        for iface_name, iface in config.network.ethernets.items():
            if iface.gateway4 or iface.gateway6:
                warnings.append(
                    f"Interface '{iface_name}' uses deprecated 'gateway4/gateway6'. "
                    "Consider using 'routes' instead."
                )

        # Check for DHCP without DNS
        for iface_name, iface in config.network.ethernets.items():
            if iface.dhcp4 and not iface.nameservers:
                warnings.append(
                    f"Interface '{iface_name}' uses DHCP without explicit DNS servers. "
                    "Consider adding nameservers for reliability."
                )

        # Check for very short interface names (possible typo)
        for iface_name in config.network.ethernets:
            if len(iface_name) < 3:
                warnings.append(
                    f"Interface name '{iface_name}' is very short. "
                    "Ensure this is correct (common names: eth0, enp1s0, etc.)"
                )

        # Check for MTU values that might cause issues
        for iface_name, iface in config.network.ethernets.items():
            if iface.mtu and iface.mtu < 1280:
                warnings.append(
                    f"Interface '{iface_name}' has MTU {iface.mtu} which is below "
                    "IPv6 minimum (1280). This may cause issues."
                )

        return warnings

    @staticmethod
    def validate_or_raise(config_path: str | Path) -> NetplanConfig:
        """Validate config and raise exception if invalid.

        Args:
            config_path: Path to netplan YAML file

        Returns:
            Validated NetplanConfig object

        Raises:
            ConfigValidationError: If validation fails
        """
        result = NetplanValidator.validate_file(config_path)

        if not result.valid:
            error_msg = "Configuration validation failed:\n"
            for error in result.errors:
                error_msg += f"  - {error}\n"
            raise ConfigValidationError(error_msg)

        if result.config is None:
            msg = "Validation succeeded but config is None (should not happen)"
            raise ConfigValidationError(msg)

        return result.config
