# Network Manager State Machine Analysis
**Project:** ace-network-manager
**Date:** 2025-10-30
**Analyst:** ANALYST Agent (Hive Mind Swarm)

---

## Executive Summary

This document provides a comprehensive analysis of safe network configuration change patterns for the ace-network-manager tool. The analysis covers state machine design, safety mechanisms, edge case handling, backup strategies, and system integration patterns. The goal is to ensure zero-downtime network configuration changes with automatic rollback capabilities.

---

## 1. State Machine Design

### 1.1 Core States

The state machine implements a conservative, fail-safe approach with the following states:

```
STABLE (Initial State)
   |
   v
BACKUP_IN_PROGRESS (Transient)
   |
   v
PENDING (Waiting for Apply)
   |
   v
APPLYING (Transient)
   |
   v
APPLIED (Grace Period Active)
   |
   +---> CONFIRMING (User Action Required)
   |        |
   |        +---> CONFIRMED --> STABLE
   |        |
   |        +---> [Timeout] --> ROLLING_BACK
   |
   +---> ROLLING_BACK (Transient)
   |        |
   |        v
   |     ROLLBACK_COMPLETE --> STABLE (with error log)
   |
   +---> FAILED --> STABLE (manual intervention required)
```

### 1.2 State Definitions

#### STABLE
- **Description:** System in known-good configuration
- **Entry Condition:** Fresh start, successful confirmation, or rollback completion
- **Characteristics:**
  - Active configuration matches last confirmed configuration
  - No pending changes
  - No timers active
  - Semaphore file contains last successful configuration metadata
- **Exit Triggers:** User initiates configuration change

#### BACKUP_IN_PROGRESS
- **Description:** Creating backup of current working configuration
- **Duration:** Transient (seconds)
- **Characteristics:**
  - Current configuration being copied to timestamped backup
  - No network changes yet
  - Fully reversible by cancellation
- **Exit Triggers:**
  - Success → PENDING
  - Failure → STABLE (with error)

#### PENDING
- **Description:** New configuration staged, backup complete, awaiting apply command
- **Characteristics:**
  - Backup file created and verified
  - New configuration validated (syntax check)
  - System still running on old configuration
  - User can review/cancel safely
- **Exit Triggers:**
  - User confirms apply → APPLYING
  - User cancels → STABLE
  - System timeout (configurable, default 10 minutes) → STABLE

#### APPLYING
- **Description:** Actively applying network configuration changes
- **Duration:** Transient (seconds)
- **Characteristics:**
  - netplan apply or networkctl reload in progress
  - Critical section - minimize time in this state
  - Network interfaces may be flapping
- **Exit Triggers:**
  - Success → APPLIED
  - Failure → ROLLING_BACK (immediate)

#### APPLIED
- **Description:** New configuration is active, grace period timer started
- **Characteristics:**
  - Network running with new configuration
  - Confirmation timer active (default 120 seconds)
  - Automatic rollback armed
  - Health checks running
- **Exit Triggers:**
  - User confirms → CONFIRMED
  - Timer expires → ROLLING_BACK
  - Health check fails → ROLLING_BACK
  - User manually cancels → ROLLING_BACK

#### CONFIRMING
- **Description:** User actively confirming the change
- **Duration:** Transient (seconds)
- **Characteristics:**
  - Validation that user has connectivity
  - Final safety check before permanent commit
- **Exit Triggers:**
  - Success → CONFIRMED
  - Timeout → ROLLING_BACK

#### CONFIRMED
- **Description:** User has verified network connectivity
- **Duration:** Transient
- **Characteristics:**
  - Timer cancelled
  - Configuration marked as stable
  - Backup retained in history
- **Exit Triggers:** Immediate → STABLE

#### ROLLING_BACK
- **Description:** Reverting to previous known-good configuration
- **Duration:** Transient (seconds)
- **Characteristics:**
  - Restoring backup configuration
  - netplan apply with old config
  - High priority operation
- **Exit Triggers:**
  - Success → ROLLBACK_COMPLETE
  - Failure → FAILED

#### ROLLBACK_COMPLETE
- **Description:** Successfully restored previous configuration
- **Duration:** Transient
- **Characteristics:**
  - Old configuration active
  - Incident logged
  - User notified
- **Exit Triggers:** Immediate → STABLE

#### FAILED
- **Description:** Critical error requiring manual intervention
- **Characteristics:**
  - Both new config and rollback failed
  - System may have network connectivity issues
  - Manual recovery required
  - Detailed error log available
  - Alert mechanisms triggered
- **Exit Triggers:** Manual recovery → STABLE

### 1.3 State Persistence (Semaphore File Structure)

Location: `/var/lib/ace-network-manager/state.json`

```json
{
  "version": "1.0",
  "current_state": "APPLIED",
  "state_entered_at": "2025-10-30T10:15:30.123456Z",
  "timeout_at": "2025-10-30T10:17:30.123456Z",
  "current_config_path": "/etc/netplan/00-installer-config.yaml",
  "backup_path": "/var/lib/ace-network-manager/backups/00-installer-config.yaml.20251030-101520",
  "change_id": "uuid-v4-here",
  "confirmation_methods": ["cli", "api", "watchdog"],
  "health_checks": {
    "last_check": "2025-10-30T10:15:35.123456Z",
    "status": "passing",
    "checks": {
      "interface_up": true,
      "gateway_reachable": true,
      "dns_resolving": true
    }
  },
  "metadata": {
    "initiated_by": "user@hostname",
    "reason": "Adding new static IP",
    "original_config_hash": "sha256:abc123...",
    "new_config_hash": "sha256:def456..."
  }
}
```

---

## 2. Safety Mechanisms Analysis

### 2.1 Timeout Strategy

#### Configurable Timeout Approach (RECOMMENDED)

**Rationale:** Different environments have different requirements:
- Remote servers: Longer timeout (5-10 minutes)
- Local infrastructure: Shorter timeout (2-3 minutes)
- Testing environments: Very short timeout (30 seconds)

**Implementation:**

```yaml
# /etc/ace-network-manager/config.yaml
timeouts:
  pending_stage: 600        # 10 minutes to review before auto-cancel
  confirmation_window: 120   # 2 minutes to confirm after apply
  apply_operation: 30       # 30 seconds for netplan apply
  rollback_operation: 30    # 30 seconds for rollback
  health_check_interval: 5  # 5 seconds between health checks
```

**Adaptive Timeout Logic:**
```python
def calculate_timeout(environment: str, change_complexity: str) -> int:
    """Calculate appropriate timeout based on context"""
    base_timeouts = {
        "production": 300,  # 5 minutes
        "staging": 180,     # 3 minutes
        "development": 60   # 1 minute
    }

    complexity_multipliers = {
        "simple": 1.0,    # Single interface change
        "moderate": 1.5,  # Multiple interfaces
        "complex": 2.0    # Routing changes, VLANs
    }

    base = base_timeouts.get(environment, 180)
    multiplier = complexity_multipliers.get(change_complexity, 1.0)

    return int(base * multiplier)
```

### 2.2 Confirmation Methods

#### Multi-Channel Confirmation (Defense in Depth)

**1. CLI Confirmation (Primary)**
```bash
# User must actively confirm
$ ace-network-manager confirm
✓ Configuration confirmed. Changes are now permanent.

# Or cancel
$ ace-network-manager cancel
⚠ Rolling back to previous configuration...
```

**2. API Confirmation (Automation-Friendly)**
```bash
# HTTP endpoint for automation
curl -X POST http://localhost:8080/api/v1/confirm \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"change_id": "uuid-here"}'
```

**3. Watchdog Confirmation (Automatic)**
```python
# Continuous health monitoring
class NetworkWatchdog:
    def check_connectivity(self) -> bool:
        """Verify network is functional"""
        checks = [
            self.check_interface_status(),
            self.check_gateway_reachability(),
            self.check_dns_resolution(),
            self.check_external_connectivity()
        ]
        return all(checks)

    def auto_confirm_if_healthy(self):
        """Auto-confirm if all health checks pass consistently"""
        if self.consecutive_healthy_checks >= self.threshold:
            self.confirm_change()
```

**4. Dead Man's Switch (Ultimate Fallback)**
```python
# If tool loses contact with monitoring system, rollback
class DeadMansSwitch:
    def __init__(self, heartbeat_interval: int = 10):
        self.last_heartbeat = time.time()
        self.heartbeat_interval = heartbeat_interval

    def check(self):
        if time.time() - self.last_heartbeat > self.heartbeat_interval * 2:
            logger.critical("Heartbeat lost - initiating rollback")
            self.trigger_rollback()
```

### 2.3 Rollback Trigger Conditions

**Automatic Rollback Triggers:**

1. **Timeout Expiration**
   - Confirmation window expires without user action
   - Priority: HIGH
   - Action: Immediate rollback

2. **Health Check Failures**
   ```python
   health_check_failures = {
       "interface_down": {"priority": "CRITICAL", "threshold": 1},
       "gateway_unreachable": {"priority": "HIGH", "threshold": 2},
       "dns_failure": {"priority": "MEDIUM", "threshold": 3},
       "packet_loss_high": {"priority": "LOW", "threshold": 5}
   }
   ```

3. **Connectivity Loss Detection**
   - Loss of connection to monitoring endpoint
   - No response from watchdog
   - SSH session disconnect (if that was the management interface)

4. **System Resource Exhaustion**
   - Network interface errors exceeding threshold
   - Kernel errors in dmesg related to networking

5. **User Manual Cancellation**
   - Explicit `ace-network-manager cancel` command

### 2.4 Race Condition Prevention

#### File-Based Locking

```python
import fcntl
import contextlib

@contextlib.contextmanager
def exclusive_lock(timeout: int = 30):
    """Ensure only one network change operation at a time"""
    lock_file = "/var/run/ace-network-manager.lock"

    with open(lock_file, 'w') as f:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        except BlockingIOError:
            raise OperationInProgress(
                "Another network configuration change is in progress. "
                "Please wait or check status with: ace-network-manager status"
            )
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

#### State Machine Synchronization

```python
class StateManager:
    def transition(self, from_state: State, to_state: State) -> bool:
        """Atomic state transition with validation"""
        with self.state_lock:
            current = self.get_current_state()

            # Verify we're in expected state
            if current != from_state:
                raise InvalidStateTransition(
                    f"Expected {from_state}, but in {current}"
                )

            # Validate transition is allowed
            if not self.is_valid_transition(from_state, to_state):
                raise IllegalTransition(
                    f"Cannot transition from {from_state} to {to_state}"
                )

            # Atomic write
            self.write_state(to_state)
            return True
```

#### Process Restart Safety

```python
def recover_from_crash():
    """Handle recovery if process crashes mid-operation"""
    state = read_state_file()

    recovery_actions = {
        "BACKUP_IN_PROGRESS": lambda: rollback_to_stable(),
        "APPLYING": lambda: check_and_rollback_if_needed(),
        "APPLIED": lambda: continue_confirmation_window(),
        "ROLLING_BACK": lambda: complete_rollback(),
        "FAILED": lambda: alert_administrator()
    }

    action = recovery_actions.get(state.current_state)
    if action:
        logger.warning(f"Recovering from crash in state: {state.current_state}")
        action()
```

---

## 3. Edge Case Analysis

### 3.1 Network Connectivity Loss During Confirmation Window

**Scenario:** User applies configuration change that breaks their SSH connection to the system.

**Problem:**
- User cannot run `ace-network-manager confirm`
- System thinks network is working (locally)
- Timeout may not be appropriate fallback

**Solution Strategy:**

```python
class ConnectivityValidator:
    def __init__(self):
        self.baseline_checks = self.capture_baseline()

    def capture_baseline(self) -> dict:
        """Capture connectivity state before change"""
        return {
            "active_connections": self.get_active_ssh_connections(),
            "ping_targets": self.get_successful_ping_targets(),
            "routes": self.get_routing_table(),
            "monitoring_endpoints": self.get_reachable_endpoints()
        }

    def validate_post_change(self) -> bool:
        """Verify connectivity is at least as good as before"""
        current = self.capture_baseline()

        # Critical: If we had SSH connections, we should still have them
        if self.baseline_checks["active_connections"]:
            if not current["active_connections"]:
                logger.critical("Lost SSH connectivity - triggering rollback")
                return False

        # Verify we can still reach critical endpoints
        for endpoint in self.baseline_checks["monitoring_endpoints"]:
            if endpoint not in current["monitoring_endpoints"]:
                logger.error(f"Lost connectivity to {endpoint}")
                return False

        return True
```

**Multi-Path Confirmation:**
1. Primary: SSH/CLI confirmation
2. Secondary: HTTP API on management interface
3. Tertiary: ICMP ping response to specific pattern
4. Quaternary: Timeout rollback

### 3.2 System Crash Mid-Transition

**Scenario:** Power loss or kernel panic during APPLYING or ROLLING_BACK state.

**Problem:**
- System may boot with partial configuration
- State file may be corrupted
- No daemon running to complete operation

**Solution Strategy:**

**Systemd Service with Crash Recovery:**

```ini
# /etc/systemd/system/ace-network-manager-watchdog.service
[Unit]
Description=ACE Network Manager Watchdog
After=network.target
Before=sshd.service
DefaultDependencies=no

[Service]
Type=oneshot
ExecStart=/usr/bin/ace-network-manager recover
RemainAfterExit=yes
TimeoutSec=60

[Install]
WantedBy=multi-user.target
```

**Recovery Logic:**

```python
def recover():
    """Run at boot to handle interrupted operations"""
    try:
        state = load_state_file()
    except (FileNotFoundError, json.JSONDecodeError):
        # No state file or corrupted - assume stable
        logger.info("No valid state file - assuming STABLE")
        initialize_stable_state()
        return

    age_seconds = (datetime.now() - state.state_entered_at).total_seconds()

    recovery_matrix = {
        "BACKUP_IN_PROGRESS": {
            "action": "rollback",
            "reason": "Backup interrupted"
        },
        "PENDING": {
            "action": "cancel",
            "reason": "System rebooted during pending state"
        },
        "APPLYING": {
            "action": "verify_and_rollback",
            "reason": "System crashed during apply",
            "check_connectivity": True
        },
        "APPLIED": {
            "action": "evaluate_timeout",
            "reason": "System rebooted during confirmation window"
        },
        "ROLLING_BACK": {
            "action": "complete_rollback",
            "reason": "Rollback interrupted"
        }
    }

    recovery = recovery_matrix.get(state.current_state)
    if recovery:
        logger.warning(f"Recovery needed: {recovery['reason']}")
        execute_recovery_action(recovery, state)
```

### 3.3 Concurrent Change Attempts

**Scenario:** Multiple administrators or automation tools try to change network config simultaneously.

**Problem:**
- Race conditions
- Conflicting changes
- State corruption

**Solution Strategy:**

**Distributed Lock with Advisory Notices:**

```python
class ChangeCoordinator:
    def acquire_change_lock(self, requester: str, reason: str) -> bool:
        """Acquire exclusive right to make network changes"""
        lock_path = "/var/run/ace-network-manager.lock"

        try:
            # Try to acquire exclusive lock
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)

            # Write lock metadata
            lock_info = {
                "requester": requester,
                "reason": reason,
                "timestamp": datetime.now().isoformat(),
                "pid": os.getpid()
            }
            os.write(lock_fd, json.dumps(lock_info).encode())

            return True

        except FileExistsError:
            # Lock already held
            lock_info = self.read_lock_info()

            # Check if holder is still alive
            if not self.is_process_alive(lock_info["pid"]):
                logger.warning("Lock holder is dead - stealing lock")
                os.unlink(lock_path)
                return self.acquire_change_lock(requester, reason)

            logger.error(
                f"Network change already in progress by {lock_info['requester']}: "
                f"{lock_info['reason']}"
            )
            return False
```

**Change Queue (Alternative Approach):**

```python
class ChangeQueue:
    """Queue changes instead of rejecting them"""
    def submit_change(self, change: NetworkChange) -> str:
        """Submit change request, returns change_id"""
        change_id = str(uuid.uuid4())

        queue_entry = {
            "change_id": change_id,
            "submitted_at": datetime.now().isoformat(),
            "submitted_by": change.requester,
            "priority": change.priority,
            "config": change.config
        }

        # Add to persistent queue
        self.queue.append(queue_entry)
        self.save_queue()

        # Notify user
        logger.info(
            f"Change queued as {change_id}. "
            f"Position in queue: {len(self.queue)}"
        )

        return change_id
```

### 3.4 Partial Configuration Application Failures

**Scenario:** netplan apply succeeds but some interfaces fail to come up, or routing changes partially apply.

**Problem:**
- Configuration is technically "applied" but non-functional
- Not a clean failure
- May pass some health checks but fail others

**Solution Strategy:**

**Comprehensive Post-Apply Validation:**

```python
class ConfigurationValidator:
    def validate_applied_config(self, expected_config: dict) -> ValidationResult:
        """Verify applied configuration matches expectations"""

        validations = [
            self.validate_interfaces(expected_config),
            self.validate_addresses(expected_config),
            self.validate_routes(expected_config),
            self.validate_dns(expected_config),
            self.validate_connectivity(expected_config)
        ]

        failures = [v for v in validations if not v.success]

        if failures:
            return ValidationResult(
                success=False,
                failures=failures,
                recommendation="ROLLBACK"
            )

        return ValidationResult(success=True)

    def validate_interfaces(self, config: dict) -> ValidationCheck:
        """Verify all configured interfaces are UP"""
        expected_interfaces = self.extract_interfaces(config)

        for interface in expected_interfaces:
            if not self.is_interface_up(interface):
                return ValidationCheck(
                    name="interface_status",
                    success=False,
                    message=f"Interface {interface} is not UP",
                    severity="CRITICAL"
                )

        return ValidationCheck(name="interface_status", success=True)

    def validate_routes(self, config: dict) -> ValidationCheck:
        """Verify routing table matches expectations"""
        expected_routes = self.extract_routes(config)
        actual_routes = self.get_routing_table()

        for route in expected_routes:
            if not self.route_exists(route, actual_routes):
                return ValidationCheck(
                    name="routing",
                    success=False,
                    message=f"Route {route} not in routing table",
                    severity="HIGH"
                )

        return ValidationCheck(name="routing", success=True)
```

**Atomic Rollback on Partial Failure:**

```python
def apply_with_validation(new_config: str, timeout: int = 30):
    """Apply config and validate, rollback on any validation failure"""

    # Apply configuration
    try:
        subprocess.run(
            ["netplan", "apply"],
            timeout=timeout,
            check=True,
            capture_output=True
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"netplan apply failed: {e.stderr}")
        raise ApplyFailed("netplan command failed")

    # Wait for interfaces to settle
    time.sleep(5)

    # Validate result
    validator = ConfigurationValidator()
    result = validator.validate_applied_config(new_config)

    if not result.success:
        logger.error(f"Validation failed: {result.failures}")
        logger.warning("Initiating automatic rollback due to validation failure")
        raise ValidationFailed(result.failures)

    logger.info("Configuration applied and validated successfully")
```

### 3.5 Reboot During PENDING State

**Scenario:** System reboots while configuration change is staged but not yet applied.

**Problem:**
- New configuration file may be in place
- But not yet applied to running system
- User may have forgotten about pending change

**Solution Strategy:**

**Clear State on Boot:**

```python
def handle_pending_after_reboot():
    """Handle PENDING state after system reboot"""

    state = load_state_file()

    if state.current_state != "PENDING":
        return

    age = (datetime.now() - state.state_entered_at).total_seconds()

    # If change was recent (< 5 minutes old), notify and maintain PENDING
    if age < 300:
        logger.warning(
            f"Network change was pending before reboot (age: {age}s). "
            "Maintaining PENDING state. Use 'ace-network-manager apply' to continue "
            "or 'ace-network-manager cancel' to abort."
        )
        # Send notification to user
        send_notification(
            f"Network change from {state.metadata['initiated_by']} "
            "is still pending after reboot"
        )
        return

    # If change was old, auto-cancel
    logger.info(
        f"Stale PENDING state detected (age: {age}s). "
        "Auto-cancelling due to system reboot."
    )
    cancel_change(state.change_id)
```

---

## 4. Backup Strategy Analysis

### 4.1 File Naming Convention

**Recommended Structure:**

```
/var/lib/ace-network-manager/backups/
├── 00-installer-config.yaml.20251030-101520.backup
├── 00-installer-config.yaml.20251030-103045.backup
├── 00-installer-config.yaml.20251030-105612.backup
└── metadata.json
```

**Naming Pattern:**
```
{original_filename}.{timestamp}.backup

timestamp format: YYYYMMDD-HHMMSS
```

**Rationale:**
- Preserves original filename for easy identification
- Timestamp ensures uniqueness and chronological sorting
- `.backup` extension prevents accidental application
- Compatible with standard shell globbing

**Metadata File:**
```json
{
  "backups": [
    {
      "filename": "00-installer-config.yaml.20251030-101520.backup",
      "original_path": "/etc/netplan/00-installer-config.yaml",
      "created_at": "2025-10-30T10:15:20.123456Z",
      "created_by": "user@hostname",
      "reason": "Before applying static IP change",
      "config_hash": "sha256:abc123...",
      "change_id": "uuid-v4-here",
      "state_at_backup": "STABLE",
      "validation_status": "confirmed",
      "size_bytes": 1234
    }
  ]
}
```

### 4.2 Retention Policy

**Multi-Tier Retention Strategy:**

```python
class BackupRetentionPolicy:
    """Intelligent backup retention"""

    def __init__(self):
        self.policies = {
            # Keep all backups for last 24 hours
            "recent": {
                "age_hours": 24,
                "keep_all": True
            },
            # Keep daily backups for last week
            "daily": {
                "age_days": 7,
                "keep_per_day": 1,
                "priority": "last"  # Keep last backup of each day
            },
            # Keep weekly backups for last month
            "weekly": {
                "age_days": 30,
                "keep_per_week": 1,
                "priority": "last"
            },
            # Keep monthly backups for 6 months
            "monthly": {
                "age_days": 180,
                "keep_per_month": 1,
                "priority": "last"
            }
        }

    def apply_retention(self, backups: List[Backup]) -> List[Backup]:
        """Determine which backups to keep"""
        to_keep = set()
        now = datetime.now()

        for backup in backups:
            age = now - backup.created_at

            # Recent: keep all
            if age.total_seconds() < self.policies["recent"]["age_hours"] * 3600:
                to_keep.add(backup)
                continue

            # Daily: keep one per day
            if age.days < self.policies["daily"]["age_days"]:
                if self.is_last_of_day(backup, backups):
                    to_keep.add(backup)
                continue

            # Weekly: keep one per week
            if age.days < self.policies["weekly"]["age_days"]:
                if self.is_last_of_week(backup, backups):
                    to_keep.add(backup)
                continue

            # Monthly: keep one per month
            if age.days < self.policies["monthly"]["age_days"]:
                if self.is_last_of_month(backup, backups):
                    to_keep.add(backup)
                continue

        # Always keep confirmed stable backups
        confirmed_backups = [b for b in backups if b.validation_status == "confirmed"]
        to_keep.update(confirmed_backups)

        return list(to_keep)
```

**Minimum Retention Rules:**
- Always keep at least 3 most recent backups
- Always keep last confirmed working configuration
- Never delete a backup that is referenced by current state
- Keep backups referenced in incident logs

### 4.3 Storage Space Management

**Proactive Space Monitoring:**

```python
class StorageManager:
    def __init__(self, backup_dir: str, max_size_mb: int = 100):
        self.backup_dir = backup_dir
        self.max_size_mb = max_size_mb
        self.warning_threshold = 0.8  # 80%

    def check_space(self) -> StorageStatus:
        """Monitor backup storage usage"""
        total_size = self.get_total_backup_size()
        max_size_bytes = self.max_size_mb * 1024 * 1024

        usage_ratio = total_size / max_size_bytes

        if usage_ratio > self.warning_threshold:
            logger.warning(
                f"Backup storage at {usage_ratio*100:.1f}% capacity. "
                f"Consider increasing storage or adjusting retention policy."
            )

        return StorageStatus(
            total_size=total_size,
            max_size=max_size_bytes,
            usage_ratio=usage_ratio
        )

    def enforce_storage_limit(self):
        """Remove old backups if exceeding storage limit"""
        status = self.check_space()

        if status.usage_ratio > 1.0:
            logger.warning("Backup storage exceeded. Removing old backups.")

            backups = self.list_backups()
            retention_policy = BackupRetentionPolicy()

            # Apply retention policy more aggressively
            to_keep = retention_policy.apply_retention(backups)
            to_remove = [b for b in backups if b not in to_keep]

            # Sort by priority (keep confirmed, important changes)
            to_remove.sort(key=lambda b: self.backup_priority(b))

            # Remove until under limit
            for backup in to_remove:
                if self.check_space().usage_ratio <= self.warning_threshold:
                    break
                self.remove_backup(backup)
                logger.info(f"Removed old backup: {backup.filename}")
```

### 4.4 Quick Restore vs Full History

**Two-Tier Backup System:**

**1. Quick Restore (Hot Backup):**
```
/var/lib/ace-network-manager/last-good-config.yaml
```
- Always points to last confirmed working configuration
- Optimized for fastest possible rollback
- Used during automatic rollback
- Atomic symlink updates

**2. Full History (Cold Storage):**
```
/var/lib/ace-network-manager/backups/
└── [timestamped backups]
```
- Complete audit trail
- Used for manual recovery
- Support for rollback to specific point in time
- Integrated with metadata

**Implementation:**

```python
class BackupManager:
    def create_backup(self, config_path: str, reason: str) -> Backup:
        """Create timestamped backup and update quick-restore link"""

        # Create timestamped backup
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{os.path.basename(config_path)}.{timestamp}.backup"
        backup_path = os.path.join(self.backup_dir, filename)

        # Copy with metadata preservation
        shutil.copy2(config_path, backup_path)

        # Verify backup
        if not self.verify_backup(config_path, backup_path):
            raise BackupVerificationFailed("Backup hash mismatch")

        # Create backup metadata
        backup = Backup(
            filename=filename,
            original_path=config_path,
            created_at=datetime.now(),
            reason=reason,
            config_hash=self.calculate_hash(backup_path)
        )

        # Update quick-restore link (will be updated after confirmation)
        # Don't update yet - wait for confirmation

        logger.info(f"Backup created: {backup_path}")
        return backup

    def confirm_backup_as_stable(self, backup: Backup):
        """Mark backup as confirmed working configuration"""
        backup.validation_status = "confirmed"

        # Update quick-restore symlink
        quick_restore_link = os.path.join(
            self.backup_dir,
            "last-good-config.yaml"
        )

        # Atomic symlink update
        temp_link = f"{quick_restore_link}.tmp"
        os.symlink(backup.filename, temp_link)
        os.rename(temp_link, quick_restore_link)

        logger.info(f"Quick-restore link updated to {backup.filename}")

    def quick_rollback(self) -> bool:
        """Fast rollback using quick-restore link"""
        quick_restore = os.path.join(
            self.backup_dir,
            "last-good-config.yaml"
        )

        if not os.path.exists(quick_restore):
            logger.error("No quick-restore backup available")
            return False

        try:
            # Copy back to original location
            target = self.get_config_path()
            shutil.copy2(quick_restore, target)

            # Apply configuration
            subprocess.run(["netplan", "apply"], check=True, timeout=30)

            logger.info("Quick rollback successful")
            return True

        except Exception as e:
            logger.error(f"Quick rollback failed: {e}")
            return False
```

---

## 5. System Integration

### 5.1 Detecting Configuration-Induced Connectivity Loss

**Multi-Layer Detection Strategy:**

**Layer 1: Interface Health**
```python
def check_interface_health() -> bool:
    """Verify network interfaces are operational"""

    # Get expected interfaces from configuration
    expected_interfaces = parse_netplan_config()

    for interface in expected_interfaces:
        # Check if interface exists
        if not os.path.exists(f"/sys/class/net/{interface}"):
            logger.error(f"Interface {interface} does not exist")
            return False

        # Check if interface is UP
        with open(f"/sys/class/net/{interface}/operstate") as f:
            state = f.read().strip()
            if state not in ["up", "unknown"]:
                logger.error(f"Interface {interface} is {state}")
                return False

        # Check for errors
        with open(f"/sys/class/net/{interface}/statistics/tx_errors") as f:
            tx_errors = int(f.read().strip())
        with open(f"/sys/class/net/{interface}/statistics/rx_errors") as f:
            rx_errors = int(f.read().strip())

        if tx_errors > 100 or rx_errors > 100:
            logger.warning(
                f"Interface {interface} has high error rate: "
                f"tx={tx_errors}, rx={rx_errors}"
            )
            return False

    return True
```

**Layer 2: Gateway Reachability**
```python
def check_gateway_reachability() -> bool:
    """Verify we can reach configured gateways"""

    # Get default gateway
    result = subprocess.run(
        ["ip", "route", "show", "default"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        logger.error("No default gateway configured")
        return False

    # Extract gateway IP
    gateway_match = re.search(r'default via ([\d.]+)', result.stdout)
    if not gateway_match:
        logger.error("Could not parse gateway from route")
        return False

    gateway = gateway_match.group(1)

    # Ping gateway
    ping_result = subprocess.run(
        ["ping", "-c", "3", "-W", "2", gateway],
        capture_output=True
    )

    if ping_result.returncode != 0:
        logger.error(f"Cannot reach gateway {gateway}")
        return False

    logger.debug(f"Gateway {gateway} is reachable")
    return True
```

**Layer 3: DNS Resolution**
```python
def check_dns_resolution() -> bool:
    """Verify DNS is working"""

    test_domains = [
        "google.com",
        "cloudflare.com",
        "one.one.one.one"
    ]

    for domain in test_domains:
        try:
            socket.getaddrinfo(domain, None)
            logger.debug(f"Successfully resolved {domain}")
            return True
        except socket.gaierror:
            logger.warning(f"Failed to resolve {domain}")
            continue

    logger.error("DNS resolution is not working")
    return False
```

**Layer 4: External Connectivity**
```python
def check_external_connectivity() -> bool:
    """Verify we can reach the internet"""

    test_endpoints = [
        "http://connectivitycheck.gstatic.com/generate_204",
        "http://detectportal.firefox.com/success.txt",
        "http://www.msftconnecttest.com/connecttest.txt"
    ]

    for endpoint in test_endpoints:
        try:
            response = requests.get(endpoint, timeout=5)
            if response.status_code in [200, 204]:
                logger.debug(f"Successfully reached {endpoint}")
                return True
        except requests.RequestException as e:
            logger.warning(f"Failed to reach {endpoint}: {e}")
            continue

    logger.error("Cannot reach external connectivity check endpoints")
    return False
```

**Layer 5: Management Interface Accessibility**
```python
def check_management_access() -> bool:
    """Verify management interfaces remain accessible"""

    # Check SSH is listening
    ssh_listening = self.is_port_listening(22)
    if not ssh_listening:
        logger.error("SSH is not listening")
        return False

    # Check API is listening (if applicable)
    api_listening = self.is_port_listening(8080)

    # Check for active management connections
    active_connections = self.get_active_connections()

    # If we had management connections before, we should still have them
    if self.baseline_connections and not active_connections:
        logger.critical("Lost all management connections")
        return False

    return True
```

**Comprehensive Health Check:**
```python
class NetworkHealthMonitor:
    def __init__(self):
        self.checks = [
            ("Interface Health", self.check_interface_health, "CRITICAL"),
            ("Gateway Reachability", self.check_gateway_reachability, "HIGH"),
            ("DNS Resolution", self.check_dns_resolution, "MEDIUM"),
            ("External Connectivity", self.check_external_connectivity, "LOW"),
            ("Management Access", self.check_management_access, "CRITICAL")
        ]

    def run_health_checks(self) -> HealthStatus:
        """Run all health checks and aggregate results"""
        results = []

        for name, check_func, severity in self.checks:
            try:
                passed = check_func()
                results.append({
                    "name": name,
                    "passed": passed,
                    "severity": severity
                })
            except Exception as e:
                logger.error(f"Health check {name} raised exception: {e}")
                results.append({
                    "name": name,
                    "passed": False,
                    "severity": severity,
                    "error": str(e)
                })

        # Determine overall health
        critical_failures = [r for r in results
                           if not r["passed"] and r["severity"] == "CRITICAL"]
        high_failures = [r for r in results
                        if not r["passed"] and r["severity"] == "HIGH"]

        if critical_failures:
            status = "CRITICAL"
            recommendation = "IMMEDIATE_ROLLBACK"
        elif len(high_failures) >= 2:
            status = "DEGRADED"
            recommendation = "ROLLBACK"
        elif high_failures:
            status = "WARNING"
            recommendation = "MONITOR"
        else:
            status = "HEALTHY"
            recommendation = "CONFIRM"

        return HealthStatus(
            status=status,
            recommendation=recommendation,
            check_results=results
        )
```

### 5.2 Ensuring Tool Accessibility

**Problem:** If the tool modifies network configuration, it must not break its own ability to operate.

**Solution Strategies:**

**1. Out-of-Band Management Interface:**
```python
def preserve_management_interface():
    """Ensure management interface is never modified"""

    # Detect current management interface
    mgmt_interface = detect_management_interface()

    logger.info(f"Management interface detected: {mgmt_interface}")

    # Add to protected interfaces list
    config = load_config()
    config["protected_interfaces"] = config.get("protected_interfaces", [])

    if mgmt_interface not in config["protected_interfaces"]:
        config["protected_interfaces"].append(mgmt_interface)
        save_config(config)

    logger.info(f"Protected interfaces: {config['protected_interfaces']}")

def validate_change_safety(new_config: dict) -> ValidationResult:
    """Ensure change won't break management access"""

    protected = load_config()["protected_interfaces"]

    for interface in protected:
        # Check if protected interface is being modified
        if interface in new_config["ethernets"]:
            new_settings = new_config["ethernets"][interface]
            current_settings = get_current_interface_config(interface)

            # Warn if management interface is being modified
            if new_settings != current_settings:
                logger.warning(
                    f"Modifying management interface {interface}. "
                    "This could break access to the system!"
                )

                # Require explicit confirmation
                if not confirm_dangerous_change():
                    return ValidationResult(
                        success=False,
                        message="User aborted management interface change"
                    )

    return ValidationResult(success=True)
```

**2. Systemd Watchdog Integration:**
```python
# Integration with systemd watchdog
import sdnotify

class ServiceWatchdog:
    def __init__(self):
        self.notifier = sdnotify.SystemdNotifier()
        self.watchdog_interval = self.get_watchdog_interval()

    def notify_ready(self):
        """Tell systemd we're ready"""
        self.notifier.notify("READY=1")

    def notify_stopping(self):
        """Tell systemd we're stopping"""
        self.notifier.notify("STOPPING=1")

    def heartbeat(self):
        """Send watchdog heartbeat"""
        self.notifier.notify("WATCHDOG=1")

    def run_with_heartbeat(self, func, *args, **kwargs):
        """Run function with periodic heartbeat"""
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True
        )
        heartbeat_thread.start()

        try:
            return func(*args, **kwargs)
        finally:
            self._stop_heartbeat = True
```

**3. Recovery Console Access:**
```python
def ensure_recovery_access():
    """Ensure there's always a way to recover"""

    # Install recovery script in initramfs
    recovery_script = """#!/bin/sh
# Emergency network recovery script
# Usage: boot with 'recovery' kernel parameter

if grep -q 'recovery' /proc/cmdline; then
    echo "Emergency network recovery mode"

    # Restore last known good config
    if [ -f /var/lib/ace-network-manager/backups/last-good-config.yaml ]; then
        cp /var/lib/ace-network-manager/backups/last-good-config.yaml \\
           /etc/netplan/00-installer-config.yaml
        netplan apply
        echo "Network configuration restored"
    fi

    # Drop to shell
    /bin/sh
fi
"""

    # Install script
    script_path = "/etc/initramfs-tools/scripts/local-bottom/network-recovery"
    with open(script_path, 'w') as f:
        f.write(recovery_script)
    os.chmod(script_path, 0o755)

    # Update initramfs
    subprocess.run(["update-initramfs", "-u"])

    logger.info("Recovery console access configured")
```

### 5.3 Monitoring and Alerting Patterns

**Event-Driven Alerting:**

```python
class AlertManager:
    def __init__(self):
        self.alert_channels = [
            SyslogChannel(),
            JournalChannel(),
            EmailChannel(),
            WebhookChannel()
        ]

    def send_alert(self, severity: str, message: str, context: dict):
        """Send alert through all configured channels"""

        alert = Alert(
            severity=severity,
            message=message,
            timestamp=datetime.now(),
            context=context,
            hostname=socket.gethostname()
        )

        for channel in self.alert_channels:
            try:
                channel.send(alert)
            except Exception as e:
                logger.error(f"Failed to send alert via {channel}: {e}")

class AlertTriggers:
    """Define when to send alerts"""

    def __init__(self, alert_manager: AlertManager):
        self.alert_manager = alert_manager

    def on_rollback_triggered(self, reason: str, state: dict):
        """Alert when automatic rollback occurs"""
        self.alert_manager.send_alert(
            severity="WARNING",
            message=f"Automatic network configuration rollback triggered: {reason}",
            context={
                "state": state,
                "reason": reason,
                "change_id": state.get("change_id")
            }
        )

    def on_change_confirmed(self, change_id: str, state: dict):
        """Alert when change is successfully confirmed"""
        self.alert_manager.send_alert(
            severity="INFO",
            message=f"Network configuration change confirmed: {change_id}",
            context={
                "state": state,
                "change_id": change_id
            }
        )

    def on_failed_state(self, error: str, state: dict):
        """Alert when entering FAILED state"""
        self.alert_manager.send_alert(
            severity="CRITICAL",
            message=f"Network configuration in FAILED state: {error}",
            context={
                "state": state,
                "error": error,
                "requires": "MANUAL_INTERVENTION"
            }
        )
```

**Metrics and Observability:**

```python
class MetricsCollector:
    """Collect operational metrics"""

    def __init__(self):
        self.metrics = {
            "changes_applied": 0,
            "changes_confirmed": 0,
            "rollbacks_triggered": 0,
            "health_checks_failed": 0,
            "average_confirmation_time": 0.0
        }

    def record_change_applied(self, change_id: str):
        """Record configuration change application"""
        self.metrics["changes_applied"] += 1
        self.emit_metric("network_config_changes_applied", 1)

    def record_rollback(self, reason: str):
        """Record rollback event"""
        self.metrics["rollbacks_triggered"] += 1
        self.emit_metric("network_config_rollbacks", 1, {"reason": reason})

    def record_confirmation_time(self, seconds: float):
        """Record how long user took to confirm"""
        # Update running average
        n = self.metrics["changes_confirmed"]
        avg = self.metrics["average_confirmation_time"]
        self.metrics["average_confirmation_time"] = (avg * n + seconds) / (n + 1)
        self.metrics["changes_confirmed"] += 1

        self.emit_metric("network_config_confirmation_time", seconds)

    def emit_metric(self, name: str, value: float, labels: dict = None):
        """Emit metric to monitoring system"""
        # Implement integration with Prometheus, InfluxDB, etc.
        pass
```

---

## 6. Risk Assessment and Mitigation

### 6.1 Risk Matrix

| Risk | Likelihood | Impact | Severity | Mitigation |
|------|-----------|---------|----------|------------|
| Network connectivity loss during apply | Medium | Critical | HIGH | Automatic rollback, health checks, timeout |
| System crash during state transition | Low | High | MEDIUM | Boot recovery, state persistence, idempotent operations |
| Concurrent configuration changes | Low | Medium | LOW | File locking, change queue |
| Backup corruption | Very Low | High | MEDIUM | Hash verification, multiple backup copies |
| Rollback failure | Very Low | Critical | HIGH | Backup verification, quick-restore, manual recovery |
| Full state file corruption | Very Low | Medium | LOW | JSON schema validation, backup state files |
| Storage exhaustion for backups | Low | Low | LOW | Retention policy, storage monitoring |
| Race condition in state transitions | Low | Medium | LOW | Atomic operations, state machine validation |
| Partial configuration application | Medium | High | MEDIUM | Post-apply validation, comprehensive health checks |
| Management interface loss | Low | Critical | HIGH | Protected interfaces, out-of-band access |

### 6.2 Mitigation Strategies Summary

**1. Prevention (Avoid risks before they occur)**
- Configuration validation before apply
- Syntax checking
- Protected interface detection
- Concurrent change prevention via locking
- Pre-change health check baseline

**2. Detection (Identify issues quickly)**
- Multi-layer health monitoring
- Continuous connectivity validation
- State file integrity checks
- Log analysis for errors
- Watchdog monitoring

**3. Response (React to issues automatically)**
- Automatic rollback on timeout
- Rollback on health check failure
- State machine recovery on boot
- Alert generation
- Metric collection

**4. Recovery (Restore service after failure)**
- Quick-restore backup system
- Manual recovery procedures
- Emergency boot recovery
- Administrator notifications
- Detailed incident logging

### 6.3 Failure Mode Analysis

**Single Point of Failure Analysis:**

1. **State File Corruption**
   - **Mitigation:** Atomic writes, backup state files, validation on read
   - **Recovery:** Reconstruct state from backup, running config, and logs

2. **Backup Storage Failure**
   - **Mitigation:** Multiple backup locations, remote backup option
   - **Recovery:** Reconstruct configuration from running system

3. **Timer/Watchdog Failure**
   - **Mitigation:** Multiple timer mechanisms (systemd, internal thread, cron)
   - **Recovery:** Boot-time recovery detects stale states

4. **Both New and Old Configuration Fail**
   - **Mitigation:** Backup verification before apply, fallback to DHCP
   - **Recovery:** Boot to recovery mode, manual configuration

**Cascading Failure Prevention:**

```python
class FailSafeManager:
    """Prevent cascading failures"""

    def __init__(self):
        self.failure_count = 0
        self.failure_window = 3600  # 1 hour
        self.failure_threshold = 3
        self.lockout_duration = 7200  # 2 hours

    def record_failure(self, failure_type: str):
        """Record configuration change failure"""
        self.failure_count += 1

        if self.failure_count >= self.failure_threshold:
            logger.critical(
                f"Failure threshold reached ({self.failure_count} failures). "
                f"Entering lockout mode for {self.lockout_duration}s"
            )
            self.enter_lockout_mode()

    def enter_lockout_mode(self):
        """Prevent further changes after repeated failures"""
        lockout = {
            "active": True,
            "started_at": datetime.now().isoformat(),
            "expires_at": (
                datetime.now() + timedelta(seconds=self.lockout_duration)
            ).isoformat(),
            "reason": "Repeated configuration failures"
        }

        with open("/var/lib/ace-network-manager/lockout", 'w') as f:
            json.dump(lockout, f)

        self.send_alert(
            "CRITICAL",
            "Network configuration changes locked out due to repeated failures"
        )

    def check_lockout(self) -> bool:
        """Check if system is in lockout mode"""
        lockout_file = "/var/lib/ace-network-manager/lockout"

        if not os.path.exists(lockout_file):
            return False

        with open(lockout_file) as f:
            lockout = json.load(f)

        if not lockout.get("active"):
            return False

        expires_at = datetime.fromisoformat(lockout["expires_at"])

        if datetime.now() > expires_at:
            # Lockout expired
            os.unlink(lockout_file)
            return False

        logger.error(
            f"System in lockout mode until {expires_at}. "
            "Manual override required."
        )
        return True
```

---

## 7. Data Flow Diagrams

### 7.1 Normal Configuration Change Flow

```
User Request
    |
    v
[Validate Request]
    |
    v
[Acquire Lock] -----> (Lock Failure) -----> [Reject: Change in Progress]
    |
    v
[Create Backup]
    |
    v
[Verify Backup]
    |
    v
[State: PENDING]
    |
    v
[User Reviews]
    |
    +---> [User Cancels] -----> [State: STABLE]
    |
    v
[User Confirms Apply]
    |
    v
[Capture Baseline]
    |
    v
[State: APPLYING]
    |
    v
[netplan apply]
    |
    v
[Wait for Settle]
    |
    v
[Validate Applied Config]
    |
    +---> (Validation Fails) -----> [State: ROLLING_BACK]
    |
    v
[State: APPLIED]
    |
    v
[Start Confirmation Timer]
    |
    v
[Run Health Checks]
    |
    +---> (Health Fails) -----> [State: ROLLING_BACK]
    |
    v
[Wait for Confirmation]
    |
    +---> (Timeout) -----> [State: ROLLING_BACK]
    |
    v
[User Confirms]
    |
    v
[Cancel Timer]
    |
    v
[State: CONFIRMED]
    |
    v
[Update Quick-Restore]
    |
    v
[Release Lock]
    |
    v
[State: STABLE]
```

### 7.2 Rollback Flow

```
[Rollback Trigger]
    |
    v
[State: ROLLING_BACK]
    |
    v
[Stop Health Checks]
    |
    v
[Load Backup Config]
    |
    v
[Verify Backup Integrity]
    |
    +---> (Backup Corrupted) -----> [Load Quick-Restore]
    |
    v
[Apply Backup Config]
    |
    v
[netplan apply]
    |
    +---> (Apply Failed) -----> [State: FAILED]
    |                                |
    |                                v
    |                          [Alert Admin]
    |                                |
    |                                v
    |                          [Log Incident]
    v
[Wait for Settle]
    |
    v
[Validate Rollback]
    |
    +---> (Validation Failed) -----> [State: FAILED]
    |
    v
[Run Health Checks]
    |
    +---> (Health Failed) -----> [State: FAILED]
    |
    v
[State: ROLLBACK_COMPLETE]
    |
    v
[Log Incident]
    |
    v
[Send Alert]
    |
    v
[Release Lock]
    |
    v
[State: STABLE]
```

### 7.3 Boot Recovery Flow

```
[System Boot]
    |
    v
[Load State File]
    |
    +---> (File Missing) -----> [Initialize: STABLE]
    |
    +---> (File Corrupted) -----> [Initialize: STABLE]
    |
    v
[Check Current State]
    |
    +---> (STABLE) -----> [Normal Operation]
    |
    +---> (PENDING) -----> [Evaluate Age]
    |                          |
    |                          +---> (Recent) -----> [Notify User]
    |                          |
    |                          +---> (Old) -----> [Auto-Cancel]
    |
    +---> (APPLYING) -----> [Check Network]
    |                          |
    |                          +---> (Working) -----> [Continue to APPLIED]
    |                          |
    |                          +---> (Broken) -----> [Rollback]
    |
    +---> (APPLIED) -----> [Check Timeout]
    |                          |
    |                          +---> (Expired) -----> [Rollback]
    |                          |
    |                          +---> (Valid) -----> [Continue Timer]
    |
    +---> (ROLLING_BACK) -----> [Complete Rollback]
    |
    +---> (FAILED) -----> [Alert Admin]
    |
    v
[Normal Operation]
```

### 7.4 Health Check Flow

```
[Timer Tick]
    |
    v
[Check Interface Status]
    |
    +---> (Failed) -----> [Increment Failure Count]
    |                          |
    v                          v
[Check Gateway Reachability]   [Check Threshold]
    |                          |
    +---> (Failed) -----> [Increment Failure Count]
    |                          |
    v                          v
[Check DNS Resolution]         [Threshold Exceeded?]
    |                          |
    +---> (Failed) -----> [Increment Failure Count]
    |                          |
    v                          +---> (Yes) -----> [Trigger Rollback]
[Check External Connectivity]  |
    |                          +---> (No) -----> [Continue Monitoring]
    +---> (Failed) -----> [Increment Failure Count]
    |
    v
[Check Management Access]
    |
    +---> (Failed) -----> [CRITICAL: Trigger Rollback]
    |
    v
[All Checks Passed]
    |
    v
[Reset Failure Count]
    |
    v
[Update Health Status]
    |
    v
[Emit Metrics]
```

---

## 8. Implementation Recommendations

### 8.1 Phase 1: Core State Machine (MVP)

**Priority: HIGH**
**Duration: 2-3 weeks**

Implement:
- Basic state machine (STABLE, PENDING, APPLYING, APPLIED, ROLLING_BACK, FAILED)
- State persistence (JSON semaphore file)
- File locking for concurrent access prevention
- Basic backup/restore functionality
- Simple timeout-based rollback
- CLI commands: apply, confirm, cancel, status

### 8.2 Phase 2: Safety Mechanisms

**Priority: HIGH**
**Duration: 2-3 weeks**

Implement:
- Health check system (interfaces, gateway, DNS)
- Automatic rollback on health failure
- Backup verification
- Configuration validation
- Protected interface detection
- Basic alerting (syslog)

### 8.3 Phase 3: Advanced Features

**Priority: MEDIUM**
**Duration: 2-3 weeks**

Implement:
- Multi-channel confirmation (API, watchdog)
- Advanced health checks (external connectivity, management access)
- Backup retention policies
- Storage management
- Metrics collection
- Boot recovery

### 8.4 Phase 4: Reliability & Observability

**Priority: MEDIUM**
**Duration: 1-2 weeks**

Implement:
- Cascading failure prevention
- Lockout mode after repeated failures
- Advanced alerting (email, webhooks)
- Detailed incident logging
- Recovery console
- Documentation

### 8.5 Testing Strategy

**Unit Tests:**
- State transition validation
- Health check logic
- Backup/restore operations
- Configuration validation

**Integration Tests:**
- Full configuration change flow
- Rollback scenarios
- Concurrent access handling
- Boot recovery

**Chaos Testing:**
- Network interface failures during apply
- System crashes at various states
- Corrupted state files
- Storage exhaustion

---

## 9. Configuration File Design

### 9.1 Main Configuration

**Location:** `/etc/ace-network-manager/config.yaml`

```yaml
# ACE Network Manager Configuration

# Timeout settings (seconds)
timeouts:
  pending_stage: 600           # Time to review before auto-cancel
  confirmation_window: 120     # Time to confirm after apply
  apply_operation: 30          # Timeout for netplan apply
  rollback_operation: 30       # Timeout for rollback
  health_check_interval: 5     # Interval between health checks

# Paths
paths:
  netplan_config: /etc/netplan/00-installer-config.yaml
  state_file: /var/lib/ace-network-manager/state.json
  backup_dir: /var/lib/ace-network-manager/backups
  lock_file: /var/run/ace-network-manager.lock
  log_file: /var/log/ace-network-manager.log

# Backup settings
backup:
  retention:
    keep_recent_hours: 24      # Keep all backups for 24 hours
    keep_daily_days: 7         # Keep daily backups for 7 days
    keep_weekly_days: 30       # Keep weekly backups for 30 days
    keep_monthly_days: 180     # Keep monthly backups for 6 months
    minimum_keep: 3            # Always keep at least 3 backups
  max_storage_mb: 100          # Maximum backup storage size
  verify_backups: true         # Verify backups with hash

# Health check settings
health_checks:
  enabled: true
  failure_threshold: 3         # Consecutive failures before rollback
  checks:
    - name: interface_status
      enabled: true
      severity: CRITICAL
    - name: gateway_reachability
      enabled: true
      severity: HIGH
    - name: dns_resolution
      enabled: true
      severity: MEDIUM
    - name: external_connectivity
      enabled: true
      severity: LOW
    - name: management_access
      enabled: true
      severity: CRITICAL

# Protected interfaces (never modify without confirmation)
protected_interfaces: []       # Auto-detected at runtime

# Confirmation methods
confirmation:
  methods:
    - cli                      # Command-line confirmation
    - api                      # HTTP API confirmation
  api:
    enabled: false
    listen: 127.0.0.1
    port: 8080
    token_file: /etc/ace-network-manager/api-token

# Alerting
alerts:
  syslog:
    enabled: true
    facility: daemon
    level: info
  email:
    enabled: false
    smtp_server: localhost
    smtp_port: 25
    from: network-manager@localhost
    to: []
  webhook:
    enabled: false
    url: ""
    headers: {}

# Fail-safe settings
failsafe:
  enabled: true
  failure_threshold: 3         # Number of failures before lockout
  failure_window: 3600         # Time window for counting failures
  lockout_duration: 7200       # Lockout duration after threshold

# Logging
logging:
  level: INFO                  # DEBUG, INFO, WARNING, ERROR, CRITICAL
  format: json                 # json or text
  max_size_mb: 10
  max_files: 5
```

---

## 10. Key Recommendations Summary

### 10.1 Must-Have Features

1. **State Persistence:** Reliable JSON-based state file with atomic writes
2. **Automatic Rollback:** Timeout-based rollback with health check acceleration
3. **Backup Verification:** Hash-based backup verification before and after
4. **File Locking:** Prevent concurrent configuration changes
5. **Boot Recovery:** Detect and recover from mid-operation crashes
6. **Health Monitoring:** Multi-layer connectivity validation

### 10.2 Configuration Decisions

1. **Timeouts Should Be Configurable:** Different environments need different timeouts
2. **Default Timeout: 120 seconds** for confirmation window (balance safety and convenience)
3. **Multiple Confirmation Methods:** CLI primary, API secondary, watchdog optional
4. **Conservative Retention:** Keep all backups for 24 hours, then tiered retention
5. **Quick-Restore Link:** For fastest possible rollback

### 10.3 Safety Philosophy

1. **Fail-Safe by Default:** When in doubt, rollback
2. **Defense in Depth:** Multiple layers of validation and monitoring
3. **Explicit Confirmation Required:** User must actively confirm, not just wait
4. **Protected Management Interface:** Never break remote access without warning
5. **Detailed Logging:** Every action logged for audit and debugging

### 10.4 Critical Success Factors

1. **State Machine Robustness:** Must handle all edge cases correctly
2. **Rollback Reliability:** Rollback must be more reliable than forward changes
3. **Clear User Feedback:** User must always know what state system is in
4. **Minimal Time in Critical Sections:** Reduce time in APPLYING state
5. **Comprehensive Testing:** Must test all failure scenarios

---

## 11. Conclusion

This analysis provides a comprehensive foundation for implementing a safe, reliable network configuration management tool. The state machine design balances safety with usability, while the multi-layered safety mechanisms ensure network changes can be made confidently with automatic rollback on any issues.

The key insight is that network configuration changes are inherently risky operations that require:
- **Conservative defaults** (automatic rollback)
- **Multiple validation layers** (syntax, health checks, user confirmation)
- **Comprehensive observability** (logging, metrics, alerts)
- **Robust recovery mechanisms** (boot recovery, manual override)

By implementing these recommendations in phases, starting with the core state machine and safety mechanisms, the ace-network-manager tool will provide a production-ready solution for safe network configuration management.

---

**Document Status:** COMPLETE
**Review Status:** Ready for Implementation
**Next Steps:** Technical review, implementation planning, prototype development
