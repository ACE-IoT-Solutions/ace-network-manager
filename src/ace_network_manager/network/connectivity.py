"""Network connectivity validation."""

import asyncio
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
        config_uses_dhcp: bool = False,
    ) -> ConnectivityResult:
        """Perform comprehensive connectivity checks with DHCP awareness.

        This performs multi-stage validation:
        1. If DHCP is configured, wait for lease acquisition
        2. Add grace period for network to stabilize
        3. Verify DNS servers are configured (from DHCP or static)
        4. Test DNS resolution with appropriate timeout
        5. Test gateway reachability

        Args:
            check_gateway: Test default gateway reachability
            check_dns: Test DNS resolution
            check_internet: Test external connectivity
            timeout: Seconds to wait for DNS/gateway checks (static configs)
            dhcp_timeout: Seconds to wait for DHCP lease acquisition
            config_uses_dhcp: Whether the applied config uses DHCP on any interface

        Returns:
            ConnectivityResult with success status, failures, and warnings
        """
        failures: list[str] = []
        warnings: list[str] = []

        # Stage 1: If DHCP is configured, wait for it to complete
        if config_uses_dhcp:
            # Give netplan a moment to start DHCP clients
            await asyncio.sleep(2)

            # Stage 2: Wait for DHCP to obtain leases
            dhcp_ok = await self._wait_for_dhcp_lease_any(dhcp_timeout)
            if not dhcp_ok:
                failures.append(f"DHCP failed to obtain lease within {dhcp_timeout}s timeout")
                # Don't continue - no point checking DNS if we don't have network config
                return ConnectivityResult(success=False, failures=failures, warnings=warnings)

            # Stage 3: Give routes and DNS time to propagate (systemd-resolved, etc.)
            await asyncio.sleep(3)

            # Stage 4: Verify we got DNS servers
            dns_servers = await self._get_configured_dns_servers()
            if not dns_servers:
                warnings.append(
                    "No DNS servers found in /etc/resolv.conf (DHCP may not have provided DNS)"
                )

        # Stage 5: Check DNS resolution (with longer timeout for DHCP scenarios)
        if check_dns:
            # Use longer timeout for DNS if we're using DHCP
            dns_timeout = 30 if config_uses_dhcp else timeout
            dns_ok = await self._check_dns(dns_timeout)
            if not dns_ok:
                # For DHCP configs, DNS failure is only a warning (gateway is more important)
                if config_uses_dhcp:
                    warnings.append(
                        f"DNS resolution check failed after {dns_timeout}s timeout "
                        "(DHCP config - DNS may take longer to propagate)"
                    )
                else:
                    failures.append(f"DNS resolution failed after {dns_timeout}s timeout")

        # Stage 6: Check default gateway (with longer timeout for DHCP)
        if check_gateway:
            gateway_timeout = 20 if config_uses_dhcp else timeout
            gateway_ok = await self._check_gateway(gateway_timeout)
            if not gateway_ok:
                failures.append(f"Cannot reach default gateway (timeout: {gateway_timeout}s)")

        # Stage 7: Check internet connectivity
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
                    "ip",
                    "route",
                    "show",
                    "default",
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

        except Exception:
            return False

    async def _check_dns(self, timeout: int) -> bool:
        """Check DNS resolution using multiple methods.

        Tries dig, host, and nslookup commands in order to check DNS.
        Falls back through multiple tools to handle different system configurations.

        Args:
            timeout: Timeout in seconds (each tool gets this full timeout)

        Returns:
            True if DNS works
        """
        # Calculate per-tool timeout (give each tool the full timeout)
        tool_timeout = max(timeout, 10)  # At least 10s per tool

        # Try multiple DNS query tools in order of preference
        # Use dynamic timeout values based on the passed timeout parameter
        dns_tools = [
            (["dig", "+short", f"+time={tool_timeout}", "+tries=1", "google.com", "A"], "dig"),
            (["host", "-W", str(tool_timeout), "google.com"], "host"),
            (["nslookup", f"-timeout={tool_timeout}", "google.com"], "nslookup"),
        ]

        for cmd, tool_name in dns_tools:
            try:
                result = await asyncio.wait_for(
                    asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    ),
                    timeout=tool_timeout + 5,  # Extra buffer for process overhead
                )
                stdout, stderr = await result.communicate()

                # Check if we got a successful response
                if result.returncode == 0:
                    output = stdout.decode().strip()
                    # Verify we got some output that looks like a successful resolution
                    if output and len(output) > 0:
                        # For dig: should have IP addresses
                        # For host: should have "has address" or similar
                        # For nslookup: should have "Address:" lines
                        if (
                            tool_name == "dig" and any(line.strip() for line in output.splitlines())
                        ) or (
                            tool_name == "host"
                            and ("has address" in output or "has IPv6" in output)
                        ):
                            return True
                        if tool_name == "nslookup" and "Address:" in output:
                            return True

            except FileNotFoundError:
                # Tool not installed, try next one
                continue
            except asyncio.TimeoutError:
                # This tool timed out, try next one
                continue
            except Exception:
                # Other error, try next tool
                continue

        # All tools failed
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
                    "ping",
                    "-c",
                    "1",
                    "-W",
                    str(timeout),
                    host,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                ),
                timeout=timeout + 1,
            )
            await result.wait()
            return result.returncode == 0
        except Exception:
            return False

    async def _wait_for_dhcp_lease_any(self, timeout: int) -> bool:
        """Wait for at least one interface to obtain a DHCP lease.

        This checks for any interface with a valid (non-link-local) IPv4 address.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            True if at least one interface has a valid address
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            # Check if we've exceeded timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                return False

            try:
                result = await asyncio.create_subprocess_exec(
                    "ip",
                    "-j",
                    "addr",
                    "show",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await result.communicate()

                if result.returncode == 0:
                    import json

                    interfaces = json.loads(stdout.decode())

                    # Check if any interface has a valid IPv4 address
                    for iface in interfaces:
                        # Skip loopback
                        if iface.get("ifname") == "lo":
                            continue

                        for addr_info in iface.get("addr_info", []):
                            if addr_info.get("family") == "inet":
                                addr = addr_info.get("local", "")
                                # Skip link-local addresses (169.254.x.x) and localhost
                                if not addr.startswith("169.254.") and not addr.startswith("127."):
                                    return True

            except Exception:
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
        except Exception:
            pass

        return dns_servers
