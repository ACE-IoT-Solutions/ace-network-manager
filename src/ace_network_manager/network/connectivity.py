"""Network connectivity validation."""

import asyncio
import socket
import subprocess
from typing import NamedTuple


class ConnectivityResult(NamedTuple):
    """Result of connectivity check."""

    success: bool
    failures: list[str]


class ConnectivityChecker:
    """Validates network connectivity after configuration changes."""

    async def check_connectivity(
        self,
        check_gateway: bool = True,
        check_dns: bool = True,
        check_internet: bool = True,
        timeout: int = 10,
    ) -> ConnectivityResult:
        """Perform comprehensive connectivity checks.

        Args:
            check_gateway: Test default gateway reachability
            check_dns: Test DNS resolution
            check_internet: Test external connectivity
            timeout: Seconds to wait for each check

        Returns:
            ConnectivityResult with success status and failures
        """
        failures: list[str] = []

        # Check default gateway
        if check_gateway:
            gateway_ok = await self._check_gateway(timeout)
            if not gateway_ok:
                failures.append("Cannot reach default gateway")

        # Check DNS resolution
        if check_dns:
            dns_ok = await self._check_dns(timeout)
            if not dns_ok:
                failures.append("DNS resolution failed")

        # Check internet connectivity
        if check_internet:
            internet_ok = await self._check_internet(timeout)
            if not internet_ok:
                failures.append("Cannot reach internet (8.8.8.8)")

        success = len(failures) == 0
        return ConnectivityResult(success=success, failures=failures)

    async def _check_gateway(self, timeout: int) -> bool:
        """Check if default gateway is reachable.

        Args:
            timeout: Timeout in seconds

        Returns:
            True if gateway is reachable
        """
        try:
            # Get default gateway
            result = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "ip", "route", "show", "default",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=5,
            )
            stdout, _ = await result.communicate()

            if not stdout:
                return False  # No default route

            # Parse gateway IP (format: "default via <IP> dev <interface>")
            parts = stdout.decode().split()
            if len(parts) < 3 or parts[1] != "via":
                return False

            gateway_ip = parts[2]

            # Ping gateway
            return await self._ping(gateway_ip, timeout)

        except Exception:  # noqa: BLE001
            return False

    async def _check_dns(self, timeout: int) -> bool:
        """Check DNS resolution.

        Args:
            timeout: Timeout in seconds

        Returns:
            True if DNS works
        """
        try:
            # Try to resolve a well-known domain
            loop = asyncio.get_event_loop()
            await asyncio.wait_for(
                loop.getaddrinfo("google.com", 80, socket.AF_INET),
                timeout=timeout,
            )
            return True
        except Exception:  # noqa: BLE001
            return False

    async def _check_internet(self, timeout: int) -> bool:
        """Check internet connectivity by pinging 8.8.8.8.

        Args:
            timeout: Timeout in seconds

        Returns:
            True if internet is reachable
        """
        return await self._ping("8.8.8.8", timeout)

    async def _ping(self, host: str, timeout: int) -> bool:
        """Ping a host.

        Args:
            host: IP address or hostname
            timeout: Timeout in seconds

        Returns:
            True if ping succeeds
        """
        try:
            result = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "ping", "-c", "1", "-W", str(timeout), host,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                ),
                timeout=timeout + 1,
            )
            await result.wait()
            return result.returncode == 0
        except Exception:  # noqa: BLE001
            return False
