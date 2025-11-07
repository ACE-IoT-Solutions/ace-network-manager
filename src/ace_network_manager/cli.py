"""CLI interface for ACE Network Manager."""

import asyncio
import json
import os
from datetime import timedelta
from pathlib import Path

import click

from ace_network_manager import __version__
from ace_network_manager.core.manager import NetworkConfigManager
from ace_network_manager.network.validator import NetplanValidator


@click.group()
@click.version_option(version=__version__)
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx: click.Context, debug: bool) -> None:
    """ACE Network Manager - Safe network configuration management.

    Apply network configurations with automatic rollback protection,
    timeout-based confirmation, and post-reboot restoration.
    """
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug


@cli.command()
@click.argument("config_file", type=click.Path(exists=True))
@click.option("--timeout", default=300, help="Seconds until auto-rollback (default: 300)")
@click.option(
    "--skip-connectivity-check", is_flag=True, help="Skip network validation (dangerous!)"
)
@click.pass_context
def apply(
    ctx: click.Context,  # noqa: ARG001
    config_file: str,
    timeout: int,
    skip_connectivity_check: bool,
) -> None:
    """Apply a new network configuration with rollback protection.

    The configuration will be applied and you'll have TIMEOUT seconds
    to confirm it's working. If not confirmed, it will automatically
    roll back.

    Example:
        ace-network-manager apply /etc/netplan/00-new-config.yaml --timeout 600
    """
    # Check for root
    if os.geteuid() != 0:
        click.secho("Error: This command must be run as root", fg="red", err=True)
        raise click.Abort

    manager = NetworkConfigManager()

    async def _apply() -> None:
        result = await manager.apply_config(
            config_path=Path(config_file),
            timeout=timedelta(seconds=timeout),
            skip_connectivity_check=skip_connectivity_check,
        )

        if not result.success:
            click.secho(f"\nFailed to apply configuration: {result.message}", fg="red")
            if result.errors:
                for error in result.errors:
                    click.secho(f"  - {error}", fg="red")
            raise click.Abort

        click.secho(f"\n✓ {result.message}", fg="green")

    asyncio.run(_apply())


@cli.command()
@click.option("--state-id", help="Specific state to confirm (default: latest)")
@click.pass_context
def confirm(ctx: click.Context, state_id: str | None) -> None:  # noqa: ARG001
    """Confirm that a pending configuration is working correctly.

    This stops the rollback timer and makes the change permanent.

    Example:
        ace-network-manager confirm
    """
    # Check for root
    if os.geteuid() != 0:
        click.secho("Error: This command must be run as root", fg="red", err=True)
        raise click.Abort

    manager = NetworkConfigManager()

    async def _confirm() -> None:
        try:
            await manager.confirm(state_id=state_id)
        except Exception as e:
            click.secho(f"\nFailed to confirm: {e}", fg="red", err=True)
            raise click.Abort from e

    asyncio.run(_confirm())


@cli.command()
@click.option("--state-id", help="State to roll back (default: latest pending)")
@click.option("--backup", type=click.Path(exists=True), help="Specific backup to restore")
@click.pass_context
def rollback(
    ctx: click.Context,  # noqa: ARG001
    state_id: str | None,
    backup: str | None,
) -> None:
    """Manually roll back to a previous configuration.

    Example:
        ace-network-manager rollback
    """
    # Check for root
    if os.geteuid() != 0:
        click.secho("Error: This command must be run as root", fg="red", err=True)
        raise click.Abort

    manager = NetworkConfigManager()

    async def _rollback() -> None:
        try:
            await manager.rollback(
                state_id=state_id,
                to_backup=Path(backup) if backup else None,
            )
            click.secho("\n✓ Configuration rolled back successfully", fg="green")
        except Exception as e:
            click.secho(f"\nFailed to rollback: {e}", fg="red", err=True)
            raise click.Abort from e

    asyncio.run(_rollback())


@cli.command()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def status(ctx: click.Context, output_json: bool) -> None:  # noqa: ARG001
    """Show current status of network configuration management.

    Displays:
    - Current state (idle/pending/rolling_back)
    - Time remaining until auto-rollback
    - Last backup information
    - Systemd service status
    """
    manager = NetworkConfigManager()
    status_info = manager.get_status()

    if output_json:
        click.echo(json.dumps(status_info, indent=2))
    else:
        if status_info["current_state"] == "idle":
            click.secho("Status: IDLE", fg="green", bold=True)
            click.echo("\nNo pending configuration changes.")
            if status_info.get("last_backup"):
                click.echo(f"\nLast backup: {status_info['last_backup']}")
        else:
            click.secho("Status: PENDING CONFIRMATION", fg="yellow", bold=True)
            click.echo(f"\nState ID: {status_info['state_id']}")
            click.echo(f"Config: {status_info['config_path']}")
            click.echo(f"Pending since: {status_info['pending_since']}")
            click.echo(f"Timeout at: {status_info['timeout_at']}")

            remaining = status_info['time_remaining_seconds']
            minutes = remaining // 60
            seconds = remaining % 60
            click.secho(
                f"\nTime remaining: {minutes}m {seconds}s",
                fg="yellow" if remaining > 60 else "red",
                bold=True,
            )

            if status_info['systemd_armed']:
                click.secho("\n✓ Systemd restoration service is armed", fg="green")
            else:
                click.secho("\n✗ Systemd restoration service not armed", fg="red")

            click.echo(f"\nBackup: {status_info['backup_path']}")
            click.echo("\nTo confirm: ace-network-manager confirm")
            click.echo("To rollback: ace-network-manager rollback")


@cli.command()
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file path (default: ./netplan-config-<timestamp>.yaml)",
)
@click.option(
    "--source-dir",
    type=click.Path(exists=True),
    default="/etc/netplan",
    help="Source netplan directory (default: /etc/netplan)",
)
@click.option(
    "--validate/--no-validate",
    default=True,
    help="Validate configuration before copying (default: validate)",
)
@click.pass_context
def prepare(
    ctx: click.Context,
    output: str | None,
    source_dir: str,
    validate: bool,  # noqa: ARG001
) -> None:
    """Prepare a copy of the current network configuration for editing.

    This command copies the currently applied netplan configuration to the
    local directory (or specified path) so you can edit it safely before
    applying with 'ace-network-manager apply'.

    The copied configuration will be validated to ensure it's syntactically
    correct before being saved (unless --no-validate is specified).

    Examples:
        # Copy current config to local directory with timestamp
        ace-network-manager prepare

        # Copy to specific file
        ace-network-manager prepare -o my-network-config.yaml

        # Copy without validation
        ace-network-manager prepare --no-validate
    """
    import shutil
    from datetime import datetime
    from pathlib import Path

    source_path = Path(source_dir)

    # Find all netplan YAML files
    yaml_files = sorted(source_path.glob("*.yaml"))
    if not yaml_files:
        click.secho(f"No netplan YAML files found in {source_dir}", fg="red", err=True)
        raise click.Abort

    # Use first file (typically 00-installer-config.yaml)
    source_file = yaml_files[0]

    # Determine output path
    if output:
        output_path = Path(output)
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        output_path = Path(f"netplan-config-{timestamp}.yaml")

    # Ensure we're not overwriting the source
    if output_path.resolve() == source_file.resolve():
        click.secho("Error: Cannot overwrite source file", fg="red", err=True)
        raise click.Abort

    # Copy the file
    try:
        shutil.copy2(source_file, output_path)
        click.secho(f"✓ Copied configuration from {source_file}", fg="green")
        click.secho(f"  to {output_path}", fg="green")

        # Show file size
        size = output_path.stat().st_size
        click.echo(f"  Size: {size} bytes")

        # Preview first few lines
        click.echo("\nConfiguration preview:")
        with output_path.open("r") as f:
            for i, line in enumerate(f):
                if i >= 10:
                    click.echo("  ...")
                    break
                click.echo(f"  {line.rstrip()}")

        click.echo(f"\nYou can now edit {output_path} and apply it with:")
        click.secho(
            f"  ace-network-manager apply {output_path} --timeout 300", fg="cyan", bold=True
        )

    except Exception as e:
        click.secho(f"Error copying configuration: {e}", fg="red", err=True)
        raise click.Abort from e


@cli.command()
@click.argument("config_file", type=click.Path(exists=True))
@click.pass_context
def validate(ctx: click.Context, config_file: str) -> None:  # noqa: ARG001
    """Validate a netplan configuration file without applying it.

    This performs comprehensive validation including:
    - YAML syntax checking
    - Schema validation
    - Network configuration logic (gateway in subnet, no duplicate subnets, etc.)
    - Common error detection (10+ checks)

    Example:
        ace-network-manager validate /path/to/config.yaml
    """
    click.echo(f"Validating {config_file}...")

    result = NetplanValidator.validate_file(config_file)

    if result.valid:
        click.secho("\n✓ Configuration is valid", fg="green", bold=True)
        if result.warnings:
            click.echo("\nWarnings:")
            for warning in result.warnings:
                click.secho(f"  ⚠ {warning}", fg="yellow")
    else:
        click.secho("\n✗ Configuration validation failed", fg="red", bold=True)
        click.echo("\nErrors:")
        for error in result.errors:
            click.secho(f"  • {error}", fg="red")
        raise click.Abort


@cli.command()
@click.option("--check-interval", default=5, help="Seconds between state checks (default: 5)")
@click.pass_context
def daemon(ctx: click.Context, check_interval: int) -> None:  # noqa: ARG001
    """Run background daemon to monitor pending configurations.

    The daemon continuously monitors for pending network configurations
    and automatically rolls them back if they expire without confirmation.

    This should typically be run as a systemd service.

    Example:
        ace-network-manager daemon
    """
    # Check for root
    if os.geteuid() != 0:
        click.secho("Error: This command must be run as root", fg="red", err=True)
        raise click.Abort

    from ace_network_manager.daemon.monitor import run_daemon

    try:
        asyncio.run(run_daemon(check_interval=check_interval))
    except KeyboardInterrupt:
        click.echo("\nDaemon stopped")


@cli.command()
@click.pass_context
def install_daemon(ctx: click.Context) -> None:  # noqa: ARG001
    """Install and enable the background daemon as a systemd service.

    This command will:
    1. Create the systemd service file in /etc/systemd/system/
    2. Reload systemd configuration
    3. Enable the service to start on boot
    4. Start the service immediately

    Example:
        sudo ace-network-manager install-daemon
    """
    import shutil
    import subprocess

    # Check for root
    if os.geteuid() != 0:
        click.secho("Error: This command must be run as root", fg="red", err=True)
        raise click.Abort

    # Use Python interpreter directly for systemd compatibility
    # This works reliably even with virtual environments
    import sys

    python_path = sys.executable
    click.echo(f"Using Python interpreter: {python_path}")

    # Embedded service file content
    # This ensures it's always available regardless of installation method
    # Using -m flag to run as module is more reliable for systemd than wrapper scripts
    service_content = f"""[Unit]
Description=ACE Network Manager Daemon
Documentation=https://github.com/ACE-IoT-Solutions/ace-network-manager
After=network.target

[Service]
Type=simple
ExecStart={python_path} -m ace_network_manager.cli daemon
Restart=always
RestartSec=10
User=root
StandardOutput=journal
StandardError=journal

# Security settings
PrivateTmp=yes
NoNewPrivileges=yes
ProtectSystem=full
ProtectHome=yes
ReadWritePaths=/var/lib/ace-network-manager /etc/netplan

[Install]
WantedBy=multi-user.target
"""

    systemd_dest = Path("/etc/systemd/system/ace-network-manager-daemon.service")

    try:
        click.echo("Installing daemon systemd service...")

        # Write service file
        click.echo(f"→ Writing service file to {systemd_dest}")
        systemd_dest.write_text(service_content)

        # Reload systemd
        click.echo("→ Reloading systemd daemon")
        subprocess.run(["systemctl", "daemon-reload"], check=True)

        # Enable service
        click.echo("→ Enabling service to start on boot")
        subprocess.run(["systemctl", "enable", "ace-network-manager-daemon"], check=True)

        # Start service
        click.echo("→ Starting service")
        subprocess.run(["systemctl", "start", "ace-network-manager-daemon"], check=True)

        # Check status
        click.echo("\n" + "=" * 70)
        click.secho("✓ Daemon installed and started successfully!", fg="green", bold=True)
        click.echo("=" * 70)

        # Show status
        click.echo("\nService status:")
        subprocess.run(["systemctl", "status", "ace-network-manager-daemon", "--no-pager"])

        click.echo("\n" + "=" * 70)
        click.echo("The daemon will now automatically monitor pending configurations")
        click.echo("and trigger rollbacks when they expire.")
        click.echo("\nUseful commands:")
        click.echo("  View logs:    sudo journalctl -u ace-network-manager-daemon -f")
        click.echo("  Stop daemon:  sudo systemctl stop ace-network-manager-daemon")
        click.echo("  Restart:      sudo systemctl restart ace-network-manager-daemon")
        click.echo("  Uninstall:    sudo ace-network-manager uninstall-daemon")
        click.echo("=" * 70)

    except subprocess.CalledProcessError as e:
        click.secho(f"\nError: Failed to install daemon: {e}", fg="red", err=True)
        raise click.Abort from e
    except Exception as e:
        click.secho(f"\nError: {e}", fg="red", err=True)
        raise click.Abort from e


@cli.command()
@click.pass_context
def uninstall_daemon(ctx: click.Context) -> None:  # noqa: ARG001
    """Uninstall the background daemon systemd service.

    This command will:
    1. Stop the daemon service
    2. Disable the service from starting on boot
    3. Remove the systemd service file
    4. Reload systemd configuration

    Example:
        sudo ace-network-manager uninstall-daemon
    """
    import subprocess

    # Check for root
    if os.geteuid() != 0:
        click.secho("Error: This command must be run as root", fg="red", err=True)
        raise click.Abort

    systemd_file = Path("/etc/systemd/system/ace-network-manager-daemon.service")

    if not systemd_file.exists():
        click.secho("Daemon is not installed", fg="yellow")
        return

    try:
        click.echo("Uninstalling daemon systemd service...")

        # Stop service
        click.echo("→ Stopping service")
        subprocess.run(["systemctl", "stop", "ace-network-manager-daemon"], check=False)

        # Disable service
        click.echo("→ Disabling service")
        subprocess.run(
            ["systemctl", "disable", "ace-network-manager-daemon"], check=False
        )

        # Remove service file
        click.echo(f"→ Removing service file from {systemd_file}")
        systemd_file.unlink()

        # Reload systemd
        click.echo("→ Reloading systemd daemon")
        subprocess.run(["systemctl", "daemon-reload"], check=True)

        click.echo("\n" + "=" * 70)
        click.secho("✓ Daemon uninstalled successfully!", fg="green", bold=True)
        click.echo("=" * 70)
        click.echo("\nAutomatic rollback monitoring has been disabled.")
        click.echo("You can reinstall it anytime with:")
        click.echo("  sudo ace-network-manager install-daemon")
        click.echo("=" * 70)

    except Exception as e:
        click.secho(f"\nError: Failed to uninstall daemon: {e}", fg="red", err=True)
        raise click.Abort from e


@cli.command(hidden=True)
@click.option("--state-id", required=True, help="State to check and restore if needed")
@click.pass_context
def systemd_restore(ctx: click.Context, state_id: str) -> None:  # noqa: ARG001
    """Internal command called by systemd service on boot.

    This command is executed by the systemd restoration service to check
    if a pending configuration state needs to be rolled back after a reboot.
    """
    from ace_network_manager.systemd.integration import SystemdIntegration

    systemd = SystemdIntegration()

    try:
        restored = systemd.check_and_restore(state_id)
        if restored:
            click.echo(f"Configuration state {state_id} was pending - rolled back")
        else:
            click.echo(f"Configuration state {state_id} was already confirmed - no action")
    except Exception as e:
        click.echo(f"Failed to check/restore state {state_id}: {e}", err=True)
        raise click.Abort from e


if __name__ == "__main__":
    cli()
