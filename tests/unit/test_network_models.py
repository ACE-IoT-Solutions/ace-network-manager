"""Unit tests for network configuration models."""

import pytest
from pydantic import ValidationError

from ace_network_manager.network.models import (
    NetplanConfig,
    NetplanEthernet,
    NetplanNameservers,
    NetplanNetwork,
    NetplanRoute,
)


class TestNetplanNameservers:
    """Test DNS nameserver validation."""

    def test_valid_dns_servers(self) -> None:
        """Test valid DNS server addresses."""
        ns = NetplanNameservers(addresses=["8.8.8.8", "1.1.1.1"], search=["example.com"])
        assert len(ns.addresses) == 2
        assert "8.8.8.8" in ns.addresses

    def test_invalid_dns_server(self) -> None:
        """Test invalid DNS server address."""
        with pytest.raises(ValidationError, match="Invalid DNS server address"):
            NetplanNameservers(addresses=["not-an-ip"])


class TestNetplanRoute:
    """Test route configuration validation."""

    def test_valid_default_route(self) -> None:
        """Test valid default route."""
        route = NetplanRoute(to="0.0.0.0/0", via="192.168.1.1")
        assert route.to == "0.0.0.0/0"
        assert route.via == "192.168.1.1"

    def test_normalize_default_keyword(self) -> None:
        """Test 'default' is normalized to 0.0.0.0/0."""
        route = NetplanRoute(to="default", via="192.168.1.1")
        assert route.to == "0.0.0.0/0"

    def test_gateway_cannot_be_network_address(self) -> None:
        """Test gateway cannot be .0 or .255 (common error #1)."""
        with pytest.raises(ValidationError, match="appears to be a network address"):
            NetplanRoute(to="0.0.0.0/0", via="192.168.1.0")

        with pytest.raises(ValidationError, match="appears to be a network address"):
            NetplanRoute(to="0.0.0.0/0", via="192.168.1.255")

    def test_invalid_destination_network(self) -> None:
        """Test invalid destination network."""
        with pytest.raises(ValidationError, match="Invalid destination network"):
            NetplanRoute(to="not-a-network", via="192.168.1.1")


class TestNetplanEthernet:
    """Test ethernet interface configuration validation."""

    def test_valid_static_config(self) -> None:
        """Test valid static IP configuration."""
        eth = NetplanEthernet(
            addresses=["192.168.1.10/24"], gateway4="192.168.1.1", dhcp4=False
        )
        assert "192.168.1.10/24" in eth.addresses
        assert eth.gateway4 == "192.168.1.1"

    def test_address_must_have_cidr(self) -> None:
        """Test addresses must have CIDR notation (common error #3)."""
        with pytest.raises(ValidationError, match="missing subnet mask"):
            NetplanEthernet(addresses=["192.168.1.10"])

    def test_address_cannot_be_network_address(self) -> None:
        """Test address cannot be network address."""
        with pytest.raises(ValidationError, match="is a network address"):
            NetplanEthernet(addresses=["192.168.1.0/24"])

    def test_gateway_must_be_in_subnet(self) -> None:
        """Test gateway must be within configured subnet (common error #5)."""
        with pytest.raises(ValidationError, match="not in any configured subnet"):
            NetplanEthernet(addresses=["192.168.1.10/24"], gateway4="192.168.2.1")

    def test_route_gateway_must_be_in_subnet(self) -> None:
        """Test route gateway must be in subnet."""
        with pytest.raises(ValidationError, match="not in any configured subnet"):
            NetplanEthernet(
                addresses=["192.168.1.10/24"],
                routes=[NetplanRoute(to="0.0.0.0/0", via="192.168.2.1")],
            )

    def test_valid_mac_address(self) -> None:
        """Test valid MAC address formats."""
        eth = NetplanEthernet(macaddress="aa:bb:cc:dd:ee:ff")
        assert eth.macaddress == "aa:bb:cc:dd:ee:ff"

        eth2 = NetplanEthernet(macaddress="AA-BB-CC-DD-EE-FF")
        assert eth2.macaddress == "aa:bb:cc:dd:ee:ff"  # Normalized

    def test_invalid_mac_address(self) -> None:
        """Test invalid MAC address."""
        with pytest.raises(ValidationError, match="Invalid MAC address"):
            NetplanEthernet(macaddress="not-a-mac")

    def test_mtu_range_validation(self) -> None:
        """Test MTU must be within valid range (common error #7)."""
        eth = NetplanEthernet(mtu=1500)
        assert eth.mtu == 1500

        with pytest.raises(ValidationError, match="greater than or equal to 68"):
            NetplanEthernet(mtu=50)

        with pytest.raises(ValidationError, match="less than or equal to 9000"):
            NetplanEthernet(mtu=10000)


class TestNetplanNetwork:
    """Test network section validation."""

    def test_valid_network(self) -> None:
        """Test valid network configuration."""
        network = NetplanNetwork(
            version=2,
            renderer="networkd",
            ethernets={
                "eth0": NetplanEthernet(addresses=["192.168.1.10/24"], gateway4="192.168.1.1")
            },
        )
        assert network.version == 2
        assert "eth0" in network.ethernets

    def test_version_must_be_2(self) -> None:
        """Test netplan version must be 2."""
        with pytest.raises(ValidationError):
            NetplanNetwork(version=1, ethernets={})

        with pytest.raises(ValidationError):
            NetplanNetwork(version=3, ethernets={})

    def test_invalid_renderer(self) -> None:
        """Test renderer must be valid."""
        with pytest.raises(ValidationError, match="Invalid renderer"):
            NetplanNetwork(version=2, renderer="invalid", ethernets={})

    def test_no_duplicate_subnets(self) -> None:
        """Test different interfaces cannot share same subnet (common error #2)."""
        from ace_network_manager.core.exceptions import SubnetOverlapError

        with pytest.raises(SubnetOverlapError) as exc_info:
            NetplanNetwork(
                version=2,
                ethernets={
                    "eth0": NetplanEthernet(addresses=["192.168.1.10/24"]),
                    "eth1": NetplanEthernet(addresses=["192.168.1.20/24"]),
                },
            )

        # Check that the exception has the expected attributes
        error = exc_info.value
        assert error.interface1 == "eth1"
        assert error.subnet1 == "192.168.1.0/24"
        assert error.interface2 == "eth0"
        assert error.subnet2 == "192.168.1.0/24"

    def test_same_interface_multiple_ips_same_subnet_allowed(self) -> None:
        """Test that a single interface CAN have multiple IPs in the same subnet."""
        # This should NOT raise an error
        network = NetplanNetwork(
            version=2,
            ethernets={
                "eth0": NetplanEthernet(
                    addresses=[
                        "192.168.1.10/24",
                        "192.168.1.11/24",
                        "192.168.1.12/24",
                    ]
                ),
            },
        )
        assert len(network.ethernets["eth0"].addresses) == 3

    def test_vlan_parent_must_exist(self) -> None:
        """Test VLAN parent interface must exist (common error #8)."""
        from ace_network_manager.network.models import NetplanVLAN

        with pytest.raises(ValidationError, match="non-existent parent interface"):
            NetplanNetwork(
                version=2, ethernets={}, vlans={"vlan10": NetplanVLAN(id=10, link="eth0")}
            )


class TestNetplanConfig:
    """Test top-level configuration."""

    def test_load_from_yaml(self, tmp_path) -> None:
        """Test loading from YAML file."""
        yaml_content = """
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      dhcp4: true
"""
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml_content)

        config = NetplanConfig.from_yaml_file(str(config_file))
        assert config.network.version == 2
        assert "eth0" in config.network.ethernets
        assert config.network.ethernets["eth0"].dhcp4 is True

    def test_load_empty_file(self, tmp_path) -> None:
        """Test loading empty file raises error."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")

        with pytest.raises(ValueError, match="empty"):
            NetplanConfig.from_yaml_file(str(config_file))

    def test_save_to_yaml(self, tmp_path) -> None:
        """Test saving to YAML file."""
        config = NetplanConfig(
            network=NetplanNetwork(
                version=2, ethernets={"eth0": NetplanEthernet(dhcp4=True)}
            )
        )

        output_file = tmp_path / "output.yaml"
        config.to_yaml_file(str(output_file))

        assert output_file.exists()

        # Load it back
        loaded = NetplanConfig.from_yaml_file(str(output_file))
        assert loaded.network.version == 2
        assert loaded.network.ethernets["eth0"].dhcp4 is True
