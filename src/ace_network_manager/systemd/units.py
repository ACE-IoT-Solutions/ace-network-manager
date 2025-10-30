"""Systemd unit file templates."""

RESTORATION_SERVICE_TEMPLATE = """[Unit]
Description=ACE Network Manager - Restore Configuration (State: {state_id})
After=network.target
Before=network-online.target
DefaultDependencies=no

[Service]
Type=oneshot
ExecStart=/usr/bin/env ace-network-manager systemd-restore --state-id {state_id}
RemainAfterExit=yes
StandardOutput=journal
StandardError=journal
TimeoutStartSec=60

[Install]
WantedBy=multi-user.target
"""
