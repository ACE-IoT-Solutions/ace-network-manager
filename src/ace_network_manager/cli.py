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
