"""Pydantic models for netplan configuration validation."""

import ipaddress
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from ace_network_manager.core.exceptions import SubnetOverlapError


class NetplanNameservers(BaseModel):
    """DNS nameserver configuration."""

    model_config = ConfigDict(extra="forbid")

    addresses: list[str] = Field(default_factory=list, description="DNS server IP addresses")
    search: list[str] = Field(default_factory=list, description="DNS search domains")

    @field_validator("addresses")
    @classmethod
    def validate_dns_addresses(cls, v: list[str]) -> list[str]:
        """Validate DNS server addresses are valid IPs."""
        for addr in v:
            try:
                ipaddress.ip_address(addr)
            except ValueError as e:
                msg = f"Invalid DNS server address '{addr}': {e}"
                raise ValueError(msg) from e
        return v


class NetplanRoute(BaseModel):
    """Route configuration."""

    model_config = ConfigDict(extra="forbid")

    to: str = Field(..., description="Destination network (e.g., '0.0.0.0/0' for default)")
    via: str = Field(..., description="Gateway IP address")
    metric: int | None = Field(None, ge=0, description="Route metric/priority")
    table: int | None = Field(None, ge=0, le=4294967295, description="Routing table number")
    on_link: bool | None = Field(None, description="Route is on-link")

    @field_validator("to")
    @classmethod
    def validate_destination(cls, v: str) -> str:
        """Validate destination is a valid network or 'default'."""
        if v == "default":
            return "0.0.0.0/0"  # Normalize to CIDR

        try:
            ipaddress.ip_network(v, strict=False)
        except ValueError as e:
            msg = f"Invalid destination network '{v}': {e}"
            raise ValueError(msg) from e
        return v

    @field_validator("via")
    @classmethod
    def validate_gateway(cls, v: str) -> str:
        """Validate gateway is a valid IP address (not a network)."""
        try:
            ip = ipaddress.ip_address(v)
            # Check it's not a network address (this is common error #1)
            if str(ip).endswith(".0") or str(ip).endswith(".255"):
                msg = f"Gateway '{v}' appears to be a network address, not a host IP"
                raise ValueError(msg)
        except ValueError as e:
            msg = f"Invalid gateway address '{v}': {e}"
            raise ValueError(msg) from e
        return v


class NetplanEthernet(BaseModel):
    """Ethernet interface configuration."""

    model_config = ConfigDict(extra="allow")  # Allow backend-specific fields

    dhcp4: bool | None = Field(None, description="Enable DHCPv4")
    dhcp6: bool | None = Field(None, description="Enable DHCPv6")
    addresses: list[str] = Field(default_factory=list, description="Static IP addresses")
    gateway4: str | None = Field(None, description="IPv4 gateway (deprecated)")
    gateway6: str | None = Field(None, description="IPv6 gateway (deprecated)")
    nameservers: NetplanNameservers | None = Field(None, description="DNS configuration")
    routes: list[NetplanRoute] = Field(default_factory=list, description="Static routes")
    mtu: int | None = Field(None, ge=68, le=9000, description="MTU size")
    macaddress: str | None = Field(None, description="MAC address")
    match: dict[str, Any] | None = Field(None, description="Match criteria")
    set_name: str | None = Field(None, description="Rename interface")
    optional: bool | None = Field(None, description="Interface is optional")

    @field_validator("addresses")
    @classmethod
    def validate_addresses(cls, v: list[str]) -> list[str]:
        """Validate IP addresses are valid with CIDR notation."""
        validated = []
        for addr in v:
            try:
                # Must have CIDR notation
                if "/" not in addr:
                    msg = f"IP address '{addr}' missing subnet mask (use CIDR notation like '{addr}/24')"
                    raise ValueError(msg)
                network = ipaddress.ip_network(addr, strict=False)
                # Warn if using network address instead of host
                ip = ipaddress.ip_interface(addr)
                if ip.ip == network.network_address and network.prefixlen < 31:
                    msg = f"Address '{addr}' is a network address, should be a host address"
                    raise ValueError(msg)
                validated.append(addr)
            except ValueError as e:
                msg = f"Invalid IP address '{addr}': {e}"
                raise ValueError(msg) from e
        return validated

    @field_validator("gateway4", "gateway6")
    @classmethod
    def validate_gateway(cls, v: str | None) -> str | None:
        """Validate gateway is a valid IP address."""
        if v is None:
            return v
        try:
            ip = ipaddress.ip_address(v)
            # Check it's not obviously a network address
            if str(ip).endswith(".0") or str(ip).endswith(".255"):
                msg = f"Gateway '{v}' appears to be a network address, not a host IP"
                raise ValueError(msg)
        except ValueError as e:
            msg = f"Invalid gateway address '{v}': {e}"
            raise ValueError(msg) from e
        return v

    @field_validator("macaddress")
    @classmethod
    def validate_mac(cls, v: str | None) -> str | None:
        """Validate MAC address format."""
        if v is None:
            return v
        # Simple MAC validation (can be enhanced)
        parts = v.lower().replace("-", ":").split(":")
        if len(parts) != 6:
            msg = f"Invalid MAC address '{v}': must have 6 octets"
            raise ValueError(msg)
        for part in parts:
            if len(part) != 2 or not all(c in "0123456789abcdef" for c in part):
                msg = f"Invalid MAC address '{v}': invalid octet '{part}'"
                raise ValueError(msg)
        return v.lower().replace("-", ":")

    @model_validator(mode="after")
    def validate_gateway_in_subnet(self) -> "NetplanEthernet":
        """Validate gateway is within one of the configured subnets."""
        if not self.addresses:
            return self

        # Check gateway4
        if self.gateway4:
            gateway_ip = ipaddress.ip_address(self.gateway4)
            gateway_in_subnet = False
            for addr_str in self.addresses:
                network = ipaddress.ip_network(addr_str, strict=False)
                if gateway_ip in network:
                    gateway_in_subnet = True
                    break
            if not gateway_in_subnet:
                msg = f"Gateway {self.gateway4} is not in any configured subnet: {self.addresses}"
                raise ValueError(msg)

        # Check routes have gateways in subnets
        for route in self.routes:
            gateway_ip = ipaddress.ip_address(route.via)
            gateway_in_subnet = False
            for addr_str in self.addresses:
                network = ipaddress.ip_network(addr_str, strict=False)
                if gateway_ip in network:
                    gateway_in_subnet = True
                    break
            if not gateway_in_subnet:
                msg = f"Route gateway {route.via} is not in any configured subnet: {self.addresses}"
                raise ValueError(msg)

        return self


class NetplanVLAN(BaseModel):
    """VLAN interface configuration."""

    model_config = ConfigDict(extra="allow")

    id: Annotated[int, Field(ge=1, le=4094, description="VLAN ID")]
    link: str = Field(..., description="Parent interface name")
    dhcp4: bool | None = None
    dhcp6: bool | None = None
    addresses: list[str] = Field(default_factory=list)
    gateway4: str | None = None
    gateway6: str | None = None
    nameservers: NetplanNameservers | None = None
    routes: list[NetplanRoute] = Field(default_factory=list)


class NetplanBridge(BaseModel):
    """Bridge interface configuration."""

    model_config = ConfigDict(extra="allow")

    interfaces: list[str] = Field(..., description="Bridge member interfaces")
    dhcp4: bool | None = None
    dhcp6: bool | None = None
    addresses: list[str] = Field(default_factory=list)
    gateway4: str | None = None
    gateway6: str | None = None
    parameters: dict[str, Any] | None = Field(None, description="Bridge parameters")


class NetplanNetwork(BaseModel):
    """Network configuration section."""

    model_config = ConfigDict(extra="forbid")

    version: Annotated[int, Field(ge=2, le=2, description="Netplan version (must be 2)")]
    renderer: str | None = Field(None, description="Network renderer (networkd or NetworkManager)")
    ethernets: dict[str, NetplanEthernet] = Field(default_factory=dict)
    vlans: dict[str, NetplanVLAN] = Field(default_factory=dict)
    bridges: dict[str, NetplanBridge] = Field(default_factory=dict)

    @field_validator("renderer")
    @classmethod
    def validate_renderer(cls, v: str | None) -> str | None:
        """Validate renderer is supported."""
        if v is not None and v not in {"networkd", "NetworkManager"}:
            msg = f"Invalid renderer '{v}': must be 'networkd' or 'NetworkManager'"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def validate_no_duplicate_subnets(self) -> "NetplanNetwork":
        """Validate no two DIFFERENT interfaces share the same subnet (common error #2).

        Note: A single interface CAN have multiple addresses in the same subnet.
        This only checks for subnet overlap between DIFFERENT interfaces.
        """
        # Map: subnet -> interface name
        subnet_map: dict[str, str] = {}

        def check_interface(name: str, addrs: list[str]) -> None:
            """Check if interface's subnets overlap with OTHER interfaces."""
            for addr_str in addrs:
                network = ipaddress.ip_network(addr_str, strict=False)
                subnet_key = str(network)

                # Check against existing subnets from OTHER interfaces
                for existing_subnet_str, existing_iface in subnet_map.items():
                    # Allow same interface to have multiple IPs in same subnet
                    if existing_iface == name:
                        continue

                    existing_subnet = ipaddress.ip_network(existing_subnet_str)

                    # Check if networks overlap between DIFFERENT interfaces
                    if network.overlaps(existing_subnet):
                        raise SubnetOverlapError(
                            interface1=name,
                            subnet1=subnet_key,
                            interface2=existing_iface,
                            subnet2=existing_subnet_str,
                        )

                # Track this subnet for this interface
                subnet_map[subnet_key] = name

        # Check all ethernet interfaces
        for iface_name, iface_config in self.ethernets.items():
            if iface_config.addresses:
                check_interface(iface_name, iface_config.addresses)

        # Check VLANs
        for vlan_name, vlan_config in self.vlans.items():
            if vlan_config.addresses:
                check_interface(vlan_name, vlan_config.addresses)

        # Check bridges
        for bridge_name, bridge_config in self.bridges.items():
            if bridge_config.addresses:
                check_interface(bridge_name, bridge_config.addresses)

        return self

    @model_validator(mode="after")
    def validate_vlan_parents_exist(self) -> "NetplanNetwork":
        """Validate VLAN parent interfaces exist."""
        all_interfaces = set(self.ethernets.keys()) | set(self.bridges.keys())

        for vlan_name, vlan_config in self.vlans.items():
            if vlan_config.link not in all_interfaces:
                msg = (
                    f"VLAN '{vlan_name}' references non-existent parent interface "
                    f"'{vlan_config.link}'"
                )
                raise ValueError(msg)

        return self

    @model_validator(mode="after")
    def validate_bridge_members_exist(self) -> "NetplanNetwork":
        """Validate bridge member interfaces exist."""
        all_interfaces = set(self.ethernets.keys()) | set(self.vlans.keys())

        for bridge_name, bridge_config in self.bridges.items():
            for member in bridge_config.interfaces:
                if member not in all_interfaces:
                    msg = (
                        f"Bridge '{bridge_name}' references non-existent member "
                        f"interface '{member}'"
                    )
                    raise ValueError(msg)

        return self


class NetplanConfig(BaseModel):
    """Top-level netplan configuration."""

    model_config = ConfigDict(extra="forbid")

    network: NetplanNetwork = Field(..., description="Network configuration")

    @classmethod
    def from_yaml_file(cls, path: str) -> "NetplanConfig":
        """Load and validate netplan config from YAML file."""
        from pathlib import Path

        import yaml

        yaml_path = Path(path)
        if not yaml_path.exists():
            msg = f"Config file not found: {path}"
            raise FileNotFoundError(msg)

        with yaml_path.open("r") as f:
            data = yaml.safe_load(f)

        if not data:
            msg = f"Config file is empty: {path}"
            raise ValueError(msg)

        return cls.model_validate(data)

    def to_yaml_file(self, path: str) -> None:
        """Save config to YAML file."""
        from pathlib import Path

        import yaml

        yaml_path = Path(path)
        yaml_path.parent.mkdir(parents=True, exist_ok=True)

        data = self.model_dump(exclude_none=True, mode="json")

        with yaml_path.open("w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
