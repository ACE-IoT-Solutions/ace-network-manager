"""Network connectivity validation."""

import asyncio
import socket
import subprocess
from pathlib import Path
from typing import NamedTuple


class ConnectivityResult(NamedTuple):
    """Result of connectivity check."""

    success: bool
    failures: list[str]
    warnings: list[str] = []


class ConnectivityChecker:
    """Validates network connectivity after configuration changes."""

    async def check_connectivity(
        self,
        check_gateway: bool = True,
        check_dns: bool = True,
        check_internet: bool = True,
        timeout: int = 10,
        dhcp_timeout: int = 30,
    ) -> ConnectivityResult:
        """Perform comprehensive connectivity checks with DHCP awareness.

        This performs multi-stage validation:
        1. Check if DHCP is in use
        2. If yes, wait for DHCP to obtain lease and address
        3. Verify DNS servers are configured (from DHCP or static)
        4. Test DNS resolution
        5. Test gateway reachability

        Args:
            check_gateway: Test default gateway reachability
            check_dns: Test DNS resolution
            check_internet: Test external connectivity
            timeout: Seconds to wait for DNS/gateway checks
            dhcp_timeout: Seconds to wait for DHCP lease acquisition

        Returns:
            ConnectivityResult with success status, failures, and warnings
        """
        failures: list[str] = []
        warnings: list[str] = []

        # Stage 1: Check if DHCP is being used
        dhcp_interfaces = await self._get_dhcp_interfaces()

        if dhcp_interfaces:
            # Stage 2: Wait for DHCP to complete on all interfaces
            dhcp_ok = await self._wait_for_dhcp_leases(dhcp_interfaces, dhcp_timeout)
            if not dhcp_ok:
                failures.append(
                    f"DHCP failed to obtain lease on interfaces: {', '.join(dhcp_interfaces)}"
                )
                # Don't continue - no point checking DNS if we don't have network config
                return ConnectivityResult(success=False, failures=failures, warnings=warnings)

            # Stage 3: Verify we got DNS servers from DHCP or have static ones
            dns_servers = await self._get_configured_dns_servers()
            if not dns_servers:
                failures.append("No DNS servers configured (DHCP did not provide DNS)")
                # Continue anyway - gateway might work

        # Stage 4: Check DNS resolution (with longer timeout for DHCP scenarios)
        if check_dns:
            # Use longer timeout for DNS if we're using DHCP
            dns_timeout = 30 if dhcp_interfaces else timeout
            dns_ok = await self._check_dns(dns_timeout)
            if not dns_ok:
                failures.append(f"DNS resolution failed after {dns_timeout}s timeout")

        # Stage 5: Check default gateway
        if check_gateway:
            gateway_ok = await self._check_gateway(timeout)
            if not gateway_ok:
                failures.append("Cannot reach default gateway")

        # Stage 6: Check internet connectivity
        if check_internet:
            internet_ok = await self._check_internet(timeout)
            if not internet_ok:
                warnings.append("Cannot reach internet (8.8.8.8) - may be expected")

        success = len(failures) == 0
        return ConnectivityResult(success=success, failures=failures, warnings=warnings)

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

    async def _get_dhcp_interfaces(self) -> list[str]:
        """Get list of interfaces configured for DHCP.

        Returns:
            List of interface names using DHCP
        """
        dhcp_interfaces: list[str] = []

        try:
            # Check ip addr output for interfaces with 'dynamic' flag
            result = await asyncio.create_subprocess_exec(
                "ip", "-j", "addr", "show",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await result.communicate()

            if result.returncode == 0:
                import json

                interfaces = json.loads(stdout.decode())
                for iface in interfaces:
                    # Check if interface has addresses with 'dynamic' flag
                    for addr_info in iface.get("addr_info", []):
                        if addr_info.get("dynamic", False):
                            ifname = iface.get("ifname", "")
                            if ifname and ifname not in dhcp_interfaces:
                                dhcp_interfaces.append(ifname)

        except Exception:  # noqa: BLE001
            pass

        return dhcp_interfaces

    async def _wait_for_dhcp_leases(
        self, interfaces: list[str], timeout: int
    ) -> bool:
        """Wait for DHCP to obtain leases on specified interfaces.

        Args:
            interfaces: Interface names to check
            timeout: Maximum seconds to wait

        Returns:
            True if all interfaces obtained addresses
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            # Check if we've exceeded timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                return False

            # Check if all interfaces have addresses
            all_have_addresses = True

            try:
                result = await asyncio.create_subprocess_exec(
                    "ip", "-j", "addr", "show",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await result.communicate()

                if result.returncode == 0:
                    import json

                    iface_data = json.loads(stdout.decode())
                    iface_dict = {iface["ifname"]: iface for iface in iface_data}

                    for ifname in interfaces:
                        iface = iface_dict.get(ifname)
                        if not iface:
                            all_have_addresses = False
                            break

                        # Check if interface has a non-link-local IPv4 address
                        has_valid_address = False
                        for addr_info in iface.get("addr_info", []):
                            if addr_info.get("family") == "inet":
                                addr = addr_info.get("local", "")
                                # Skip link-local addresses (169.254.x.x)
                                if not addr.startswith("169.254."):
                                    has_valid_address = True
                                    break

                        if not has_valid_address:
                            all_have_addresses = False
                            break

                    if all_have_addresses:
                        return True

            except Exception:  # noqa: BLE001
                pass

            # Wait a bit before checking again
            await asyncio.sleep(1)

    async def _get_configured_dns_servers(self) -> list[str]:
        """Get list of configured DNS servers.

        Checks /etc/resolv.conf for nameserver entries.

        Returns:
            List of DNS server IP addresses
        """
        dns_servers: list[str] = []

        try:
            resolv_conf = Path("/etc/resolv.conf")
            if resolv_conf.exists():
                content = resolv_conf.read_text()
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("nameserver"):
                        parts = line.split()
                        if len(parts) >= 2:
                            dns_servers.append(parts[1])
        except Exception:  # noqa: BLE001
            pass

        return dns_servers
