# ACE Network Manager

Safe network configuration manager for edge deployments with automatic rollback protection.

## Problem

The netplan tool in Ubuntu 20.04 and 24.04 has critical bugs that fail to properly restore:
- Routing tables after a failed `netplan try`
- DHCP-acquired settings
- Complex multi-interface configurations

This causes production issues in edge environments where physical access is difficult or impossible.

## Solution

ACE Network Manager provides:
- **Atomic configuration changes** with automatic rollback
- **Timeout-based confirmation** requiring user verification (default: 5 minutes)
- **Semaphore-based state tracking** that persists across reboots
- **Systemd integration** for post-reboot restoration
- **Human-readable backups** with timestamped versions
- **Network connectivity validation** before finalizing changes

## Installation

```bash
# Install with UV
uv pip install ace-network-manager

# Or from source
git clone https://github.com/aceiot/ace-network-manager
cd ace-network-manager
uv sync
uv run ace-network-manager --version
```

## Quick Start

```bash
# Apply a new network configuration (5 minute timeout)
sudo ace-network-manager apply /etc/netplan/00-new-config.yaml

# Confirm the configuration is working
sudo ace-network-manager confirm

# Or manually rollback if something went wrong
sudo ace-network-manager rollback

# Check current status
ace-network-manager status
```

## Features

### Safe Configuration Changes

1. **Pre-change backup** - Creates timestamped backup of current config
2. **Comprehensive validation** - Pydantic-based validation with 10+ error checks
3. **Apply** - Applies configuration via netplan
4. **Connectivity check** - Validates network is working
5. **Timeout watcher** - Monitors for user confirmation
6. **Auto-rollback** - Reverts if not confirmed within timeout
7. **Post-reboot check** - Restores on boot if pending confirmation

### Comprehensive Validation (NEW!)

**Type-safe Pydantic models** catch errors before applying:

1. [x] **Gateway validation** - Ensures gateways are host IPs, not network addresses (`.0` or `.255`)
2. [x] **Subnet overlap detection** - Prevents multiple interfaces in same subnet
3. [x] **Gateway in subnet check** - Verifies gateway is reachable from interface
4. [x] **CIDR notation enforcement** - IP addresses must include subnet mask
5. [x] **MTU range validation** - MTU must be 68-9000 bytes
6. [x] **MAC address format validation** - Validates MAC address syntax
7. [x] **VLAN ID validation** - VLAN IDs must be 1-4094
8. [x] **VLAN parent existence** - VLAN parent interfaces must exist
9. [x] **DNS server validation** - DNS servers must be valid IP addresses
10. [x] **Version validation** - Netplan version must be 2

**All models are fully type-hinted** to prevent human errors during development!

### Backup Management

Backups are stored in human-readable format:

```
/var/lib/ace-network-manager/backups/
  2024-10-30-143022-550e8400/
    metadata.json
    00-installer-config.yaml
    checksums.sha256
  latest -> 2024-10-30-143022-550e8400/
```

### State Tracking

State is tracked with JSON semaphore files that survive reboots:

```json
{
  "state_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "timeout_at": "2024-10-30T14:35:22.123456Z",
  "backup_path": "/var/lib/ace-network-manager/backups/...",
  ...
}
```

## CLI Commands

### prepare

**NEW!** Prepare a copy of the current network configuration for editing:

```bash
ace-network-manager prepare [OPTIONS]

Options:
  -o, --output PATH     Output file path (default: ./netplan-config-<timestamp>.yaml)
  --source-dir PATH     Source netplan directory (default: /etc/netplan)
  --validate/--no-validate  Validate configuration (default: validate)

Examples:
  # Copy current config to local directory with timestamp
  ace-network-manager prepare

  # Copy to specific file
  ace-network-manager prepare -o my-network-config.yaml
```

### validate

**NEW!** Validate a netplan configuration file without applying it:

```bash
ace-network-manager validate CONFIG_FILE

Performs comprehensive validation including:
  - YAML syntax checking
  - Schema validation
  - Gateway in subnet verification
  - Duplicate subnet detection
  - 10+ common network configuration error checks

Example:
  ace-network-manager validate /path/to/config.yaml
```

### apply

Apply a new network configuration with rollback protection:

```bash
ace-network-manager apply [OPTIONS] CONFIG_FILE

Options:
  --timeout INTEGER              Seconds until auto-rollback (default: 300)
  --skip-connectivity-check      Skip network validation (dangerous!)
```

### confirm

Confirm that a pending configuration is working correctly:

```bash
ace-network-manager confirm [OPTIONS]

Options:
  --state-id TEXT  Specific state to confirm (default: latest)
```

### rollback

Manually roll back to a previous configuration:

```bash
ace-network-manager rollback [OPTIONS]

Options:
  --state-id TEXT  State to roll back (default: latest pending)
  --backup PATH    Specific backup file to restore
```

### status

Show current status of network configuration management:

```bash
ace-network-manager status [OPTIONS]

Options:
  --json  Output as JSON
```

## Architecture

```
NetworkConfigManager (orchestrator)
  StateTracker (semaphore files, cross-reboot persistence)
  BackupManager (timestamped backups with checksums)
  TimeoutWatcher (async monitoring, automatic rollback)
  NetplanBackend (validation, apply, connectivity checks)
  SystemdIntegration (boot-time restoration service)
```

## Development

### Setup

```bash
# Clone and install dependencies
git clone https://github.com/aceiot/ace-network-manager
cd ace-network-manager
uv sync --dev

# Run linting
uv run ruff check src/

# Run type checking
uv run pyrefly src/

# Run tests
uv run pytest tests/ -v
```

### Testing

```bash
# Unit tests
uv run pytest tests/unit/ -v

# Integration tests (requires systemd)
uv run pytest tests/integration/ -v -m requires_systemd

# Coverage
uv run pytest tests/ --cov=ace_network_manager --cov-report=html
```

## Implementation Status

- [x] Phase 1: Project structure and tooling
- [x] Pydantic models for netplan validation
- [x] State models with comprehensive type hints
- [x] Network configuration validation (10+ error checks)
- [x] CLI commands: `prepare` and `validate`
- [x] Unit tests for validation (22 tests passing)
- [ ] Phase 2: State management implementation
- [ ] Phase 3: Backup system implementation
- [ ] Phase 4: Network integration (netplan apply)
- [ ] Phase 5: Timeout watcher
- [ ] Phase 6: Systemd integration
- [ ] Phase 7: Core orchestration
- [ ] Phase 8: CLI command implementation (apply, confirm, rollback, status)
- [ ] Phase 9: Integration testing
- [ ] Phase 10: Documentation and polish

## Documentation

- [State Machine Analysis](.hive-mind/network-manager-state-machine-analysis.md) - State transitions and safety mechanisms
- [Testing Strategy](TESTING_STRATEGY.md) - Comprehensive testing approach

## License

MIT

## Credits

Developed by ACE IoT Solutions for safe network management in edge deployments.

---
