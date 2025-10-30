# Comprehensive Testing Strategy for Safe Network Configuration Manager

## Executive Summary

This document outlines a comprehensive testing strategy for the safe network configuration manager tool designed for Ubuntu 20.04/24.04 edge deployments. Given the critical nature of network configuration changes in production environments, this strategy prioritizes safety, reliability, and thorough validation of all failure modes.

## Table of Contents

1. [Testing Philosophy](#testing-philosophy)
2. [Test Strategy Overview](#test-strategy-overview)
3. [Component-Based Testing](#component-based-testing)
4. [Critical Test Scenarios](#critical-test-scenarios)
5. [Testing Challenges and Solutions](#testing-challenges-and-solutions)
6. [Test Fixtures and Data](#test-fixtures-and-data)
7. [Safety Testing](#safety-testing)
8. [Testing Tools and Infrastructure](#testing-tools-and-infrastructure)
9. [CI/CD Integration](#cicd-integration)
10. [Risk Areas and Mitigation](#risk-areas-and-mitigation)

---

## Testing Philosophy

### Core Principles

1. **Safety First**: All tests must validate that the system can never leave the network in an unrecoverable state
2. **Fail-Safe Design**: Every failure mode must have a tested rollback path
3. **Isolation**: Tests must not interfere with the host system's actual network configuration
4. **Reproducibility**: All tests must be deterministic and repeatable
5. **Real-World Scenarios**: Tests must simulate actual edge deployment conditions

### Testing Pyramid

```
                    /\
                   /  \
                  / E2E \          <- 10% End-to-End Tests
                 /______\
                /        \
               /Integration\       <- 30% Integration Tests
              /____________\
             /              \
            /  Unit Tests    \     <- 60% Unit Tests
           /________________\
```

---

## Test Strategy Overview

### 1. Unit Testing Approach

**Scope**: Individual functions, classes, and modules in isolation

**Coverage Target**: 90%+ for core logic, 100% for critical safety functions

**Key Areas**:
- Configuration file parsing and validation
- Backup file management and rotation
- Semaphore file state management
- Timeout calculation and monitoring
- Configuration difference detection
- System command construction (without execution)

**Tools**:
- pytest for test framework
- pytest-cov for coverage reporting
- pytest-mock for mocking
- freezegun for time-based testing
- hypothesis for property-based testing

### 2. Integration Testing Approach

**Scope**: Component interactions and state transitions

**Coverage Target**: All state machine transitions and component boundaries

**Key Areas**:
- State machine transitions (pending → applied → confirmed/rolled-back)
- Configuration backup → apply → restore workflows
- Semaphore file coordination between system restart
- Timeout monitoring and automatic rollback triggers
- Lock file management for concurrent operation prevention

**Tools**:
- pytest with fixtures for state setup
- pytest-timeout for timeout testing
- pytest-asyncio if async operations are used
- temporary filesystem fixtures

### 3. End-to-End Testing

**Scope**: Complete workflows from user command to final system state

**Coverage Target**: All primary use cases and critical failure scenarios

**Key Areas**:
- Full apply-confirm-success workflow
- Full apply-timeout-rollback workflow
- Post-reboot restoration scenarios
- Multiple configuration change cycles
- Error recovery and user feedback

**Tools**:
- Docker containers with Ubuntu 20.04/24.04
- Network namespaces for network isolation
- systemd service simulation
- pytest-bdd for behavior-driven scenarios

### 4. Chaos Testing

**Scope**: Unexpected failures and edge cases

**Coverage Target**: All identified failure modes

**Key Areas**:
- Process termination during configuration apply
- Filesystem full during backup creation
- Corrupted semaphore files
- Concurrent process attempts
- System crashes at various stages
- Network interface disappearance
- Permission errors

**Tools**:
- chaos-mesh or custom chaos injection
- pytest-xdist for parallel test execution
- Custom fault injection framework

### 5. Performance Testing

**Scope**: Resource usage and timing characteristics

**Coverage Target**: All timeout-critical operations

**Key Areas**:
- Configuration apply time for various complexity levels
- Backup file creation and restoration time
- Semaphore file I/O performance
- Memory usage during operations
- Filesystem space requirements

**Tools**:
- pytest-benchmark
- memory_profiler
- Custom timing assertions

---

## Component-Based Testing

### Component 1: Configuration Manager

**Responsibility**: Parse, validate, and manage network configuration files

#### Unit Tests

```python
# test_config_manager.py

class TestConfigurationParser:
    """Test configuration file parsing"""

    def test_parse_valid_netplan_config(self):
        """Should successfully parse valid netplan YAML"""

    def test_parse_invalid_yaml_raises_error(self):
        """Should raise ParseError for invalid YAML"""

    def test_parse_missing_required_fields_raises_error(self):
        """Should raise ValidationError for missing required fields"""

    def test_parse_netplan_with_dhcp(self):
        """Should correctly parse DHCP configuration"""

    def test_parse_netplan_with_static_ip(self):
        """Should correctly parse static IP configuration"""

    def test_parse_netplan_with_multiple_interfaces(self):
        """Should handle multiple network interfaces"""

    def test_validate_ip_address_format(self):
        """Should validate IP address format"""

    def test_validate_cidr_notation(self):
        """Should validate CIDR notation"""

    def test_detect_configuration_changes(self):
        """Should correctly identify differences between configs"""

    def test_configuration_equality(self):
        """Should correctly determine config equality"""

class TestConfigurationComparison:
    """Test configuration difference detection"""

    def test_no_changes_detected_for_identical_configs(self):
        """Should return no changes for identical configurations"""

    def test_detect_added_interface(self):
        """Should detect newly added network interface"""

    def test_detect_removed_interface(self):
        """Should detect removed network interface"""

    def test_detect_ip_address_change(self):
        """Should detect IP address changes"""

    def test_detect_dhcp_to_static_change(self):
        """Should detect DHCP to static IP transition"""

    def test_detect_gateway_change(self):
        """Should detect gateway changes"""
```

#### Integration Tests

```python
# test_config_integration.py

class TestConfigurationWorkflow:
    """Test configuration workflows"""

    def test_load_apply_restore_cycle(self, temp_config_dir):
        """Should complete full config load-apply-restore cycle"""

    def test_configuration_validation_before_apply(self):
        """Should validate config before attempting to apply"""

    def test_configuration_backup_on_change(self):
        """Should create backup before applying changes"""
```

### Component 2: Backup Manager

**Responsibility**: Create, manage, and restore configuration backups

#### Unit Tests

```python
# test_backup_manager.py

class TestBackupCreation:
    """Test backup file creation"""

    def test_create_backup_with_timestamp(self):
        """Should create backup file with timestamp in name"""

    def test_backup_file_naming_convention(self):
        """Should use correct naming: config.yaml.bak.YYYYMMDD-HHMMSS"""

    def test_backup_preserves_file_permissions(self):
        """Should preserve original file permissions in backup"""

    def test_backup_preserves_file_ownership(self):
        """Should preserve original file ownership in backup"""

    def test_backup_atomic_write(self):
        """Should use atomic write for backup creation"""

    def test_backup_verification_after_creation(self):
        """Should verify backup integrity after creation"""

class TestBackupRestoration:
    """Test backup restoration"""

    def test_restore_from_latest_backup(self):
        """Should restore from most recent backup"""

    def test_restore_from_specific_backup(self):
        """Should restore from specified backup file"""

    def test_restore_with_verification(self):
        """Should verify restored file matches backup"""

    def test_restore_handles_missing_backup(self):
        """Should handle missing backup file gracefully"""

    def test_restore_atomic_write(self):
        """Should use atomic write for restoration"""

class TestBackupRotation:
    """Test backup file rotation and cleanup"""

    def test_list_backups_in_chronological_order(self):
        """Should list backups from newest to oldest"""

    def test_delete_old_backups_beyond_retention(self):
        """Should delete backups older than retention period"""

    def test_keep_minimum_backup_count(self):
        """Should always keep minimum number of backups"""

    def test_backup_rotation_with_disk_full(self):
        """Should handle disk full during backup rotation"""
```

#### Integration Tests

```python
# test_backup_integration.py

class TestBackupWorkflow:
    """Test complete backup workflows"""

    def test_backup_before_config_change(self):
        """Should create backup before applying config change"""

    def test_multiple_backup_cycle(self):
        """Should handle multiple backup creation cycles"""

    def test_rollback_uses_correct_backup(self):
        """Should use appropriate backup for rollback"""

    def test_backup_with_concurrent_operations(self):
        """Should handle concurrent backup operations safely"""
```

### Component 3: State Manager

**Responsibility**: Manage configuration change state using semaphore files

#### Unit Tests

```python
# test_state_manager.py

class TestStateTracking:
    """Test state tracking with semaphore files"""

    def test_create_pending_state(self):
        """Should create semaphore file for pending state"""

    def test_transition_to_applied_state(self):
        """Should transition from pending to applied"""

    def test_transition_to_confirmed_state(self):
        """Should transition from applied to confirmed"""

    def test_transition_to_rolled_back_state(self):
        """Should transition from applied to rolled back"""

    def test_invalid_state_transition_raises_error(self):
        """Should raise error for invalid state transitions"""

    def test_state_persistence_across_process_restart(self):
        """Should persist state information across restarts"""

    def test_state_includes_timestamp(self):
        """Should include timestamp in state information"""

    def test_state_includes_backup_reference(self):
        """Should reference backup file in state"""

    def test_state_includes_timeout_value(self):
        """Should store timeout value in state"""

class TestSemaphoreFiles:
    """Test semaphore file management"""

    def test_semaphore_file_location(self):
        """Should use correct location for semaphore files"""

    def test_semaphore_file_format(self):
        """Should use correct JSON format for semaphore"""

    def test_semaphore_atomic_write(self):
        """Should write semaphore files atomically"""

    def test_semaphore_read_with_corruption(self):
        """Should handle corrupted semaphore files"""

    def test_semaphore_cleanup_on_completion(self):
        """Should clean up semaphore file after confirmation"""

    def test_semaphore_preserved_on_rollback(self):
        """Should preserve semaphore for audit after rollback"""

class TestStateRecovery:
    """Test state recovery scenarios"""

    def test_detect_pending_state_on_startup(self):
        """Should detect pending changes on system startup"""

    def test_auto_rollback_expired_changes_on_startup(self):
        """Should rollback expired changes after reboot"""

    def test_ignore_confirmed_state_on_startup(self):
        """Should ignore confirmed changes on startup"""

    def test_handle_missing_backup_during_recovery(self):
        """Should handle missing backup during state recovery"""
```

#### Integration Tests

```python
# test_state_integration.py

class TestStateWorkflow:
    """Test complete state management workflows"""

    def test_full_state_lifecycle(self):
        """Should complete full state lifecycle"""

    def test_state_persistence_across_mock_reboot(self):
        """Should maintain state across simulated reboot"""

    def test_concurrent_state_check_operations(self):
        """Should handle concurrent state checks safely"""
```

### Component 4: Timeout Monitor

**Responsibility**: Monitor configuration changes and trigger automatic rollback

#### Unit Tests

```python
# test_timeout_monitor.py

class TestTimeoutCalculation:
    """Test timeout calculation and tracking"""

    def test_calculate_timeout_deadline(self):
        """Should correctly calculate timeout deadline"""

    def test_check_timeout_not_expired(self):
        """Should return False when timeout not expired"""

    def test_check_timeout_expired(self):
        """Should return True when timeout expired"""

    def test_timeout_with_custom_duration(self):
        """Should respect custom timeout duration"""

    def test_timeout_default_value(self):
        """Should use default timeout when not specified"""

class TestTimeoutMonitoring:
    """Test timeout monitoring behavior"""

    def test_monitor_starts_on_config_apply(self):
        """Should start monitoring after config application"""

    def test_monitor_stops_on_confirmation(self):
        """Should stop monitoring after confirmation"""

    def test_monitor_triggers_rollback_on_timeout(self):
        """Should trigger rollback when timeout expires"""

    def test_monitor_respects_grace_period(self):
        """Should include grace period in timeout calculation"""
```

#### Integration Tests

```python
# test_timeout_integration.py

class TestTimeoutWorkflow:
    """Test timeout monitoring workflows"""

    def test_timeout_with_automatic_rollback(self):
        """Should automatically rollback after timeout"""

    def test_confirmation_before_timeout(self):
        """Should accept confirmation before timeout"""

    def test_timeout_after_system_restart(self):
        """Should enforce timeout after system restart"""
```

### Component 5: Network Applier

**Responsibility**: Apply network configuration changes to the system

#### Unit Tests

```python
# test_network_applier.py

class TestNetplanCommands:
    """Test netplan command generation"""

    def test_generate_netplan_apply_command(self):
        """Should generate correct netplan apply command"""

    def test_generate_netplan_try_command(self):
        """Should generate correct netplan try command"""

    def test_command_with_timeout_parameter(self):
        """Should include timeout in command when specified"""

    def test_command_validation_before_execution(self):
        """Should validate command before execution"""

class TestConfigurationApplication:
    """Test configuration application (mocked execution)"""

    def test_apply_configuration_success(self, mock_subprocess):
        """Should successfully apply configuration"""

    def test_apply_configuration_failure(self, mock_subprocess):
        """Should handle configuration apply failure"""

    def test_apply_with_validation(self, mock_subprocess):
        """Should validate before applying"""

    def test_apply_preserves_backup_reference(self):
        """Should maintain backup reference during apply"""

class TestNetworkManagerSupport:
    """Test NetworkManager configuration support"""

    def test_detect_networkmanager_system(self):
        """Should detect NetworkManager-based system"""

    def test_apply_networkmanager_config(self):
        """Should apply NetworkManager configuration"""

    def test_fallback_to_netplan(self):
        """Should fallback to netplan when NetworkManager unavailable"""
```

#### Integration Tests

```python
# test_network_applier_integration.py

class TestApplicationWorkflow:
    """Test network configuration application workflows"""

    def test_full_apply_workflow(self, isolated_network):
        """Should complete full configuration apply in isolation"""

    def test_rollback_restores_previous_config(self, isolated_network):
        """Should restore previous config on rollback"""

    def test_apply_with_network_namespace(self, network_namespace):
        """Should work correctly in network namespace"""
```

### Component 6: Lock Manager

**Responsibility**: Prevent concurrent configuration changes

#### Unit Tests

```python
# test_lock_manager.py

class TestLockAcquisition:
    """Test lock acquisition and release"""

    def test_acquire_lock_when_available(self):
        """Should acquire lock when available"""

    def test_fail_to_acquire_when_locked(self):
        """Should fail when lock already held"""

    def test_release_lock(self):
        """Should release lock successfully"""

    def test_lock_with_timeout(self):
        """Should timeout if lock cannot be acquired"""

    def test_lock_automatic_release_on_process_exit(self):
        """Should release lock when process exits"""

class TestLockPersistence:
    """Test lock file persistence"""

    def test_lock_file_creation(self):
        """Should create lock file with PID"""

    def test_stale_lock_detection(self):
        """Should detect stale lock from dead process"""

    def test_stale_lock_cleanup(self):
        """Should clean up stale locks"""

    def test_lock_file_permissions(self):
        """Should set appropriate lock file permissions"""

class TestConcurrency:
    """Test concurrent operation prevention"""

    def test_prevent_concurrent_applies(self):
        """Should prevent concurrent apply operations"""

    def test_prevent_concurrent_rollbacks(self):
        """Should prevent concurrent rollback operations"""

    def test_allow_concurrent_status_checks(self):
        """Should allow concurrent status checks"""
```

### Component 7: System Service Integration

**Responsibility**: Integrate with systemd for boot-time recovery

#### Unit Tests

```python
# test_service_integration.py

class TestServiceConfiguration:
    """Test systemd service configuration"""

    def test_service_file_format(self):
        """Should generate valid systemd service file"""

    def test_service_dependencies(self):
        """Should declare correct service dependencies"""

    def test_service_runs_before_network_target(self):
        """Should run before network target"""

    def test_service_oneshot_type(self):
        """Should use oneshot service type"""

class TestBootRecovery:
    """Test boot-time recovery logic"""

    def test_check_for_pending_changes(self):
        """Should check for pending changes at boot"""

    def test_rollback_expired_changes(self):
        """Should rollback expired changes at boot"""

    def test_preserve_valid_changes(self):
        """Should preserve non-expired changes at boot"""

    def test_log_boot_recovery_actions(self):
        """Should log all boot recovery actions"""
```

---

## Critical Test Scenarios

### Scenario 1: Successful Configuration Application

**Objective**: Verify complete happy-path workflow

```python
# test_scenarios.py

class TestSuccessfulConfiguration:
    """Test successful configuration scenarios"""

    def test_apply_and_confirm_static_ip(self):
        """
        Given: System with DHCP configuration
        When: User applies static IP and confirms within timeout
        Then: Configuration persists and backups are created
        """

    def test_apply_and_confirm_multiple_interfaces(self):
        """
        Given: System with single interface
        When: User adds multiple interfaces and confirms
        Then: All interfaces are configured correctly
        """

    def test_apply_and_confirm_with_custom_timeout(self):
        """
        Given: User specifies custom timeout of 300 seconds
        When: User confirms within custom timeout
        Then: Configuration persists correctly
        """
```

### Scenario 2: Timeout-Triggered Automatic Rollback

**Objective**: Verify automatic rollback after timeout expiration

```python
class TestTimeoutRollback:
    """Test automatic rollback scenarios"""

    def test_rollback_after_timeout_expiration(self):
        """
        Given: User applies configuration with 60s timeout
        When: User does not confirm within timeout
        Then: System automatically rolls back to previous config
        """

    def test_rollback_restores_network_connectivity(self):
        """
        Given: Configuration change that breaks connectivity
        When: Timeout expires without confirmation
        Then: Network connectivity is restored
        """

    def test_rollback_preserves_audit_trail(self):
        """
        Given: Configuration change that times out
        When: Automatic rollback occurs
        Then: All state transitions are logged for audit
        """
```

### Scenario 3: Post-Reboot Restoration

**Objective**: Verify recovery after system restart

```python
class TestPostRebootRecovery:
    """Test post-reboot recovery scenarios"""

    def test_restore_after_reboot_during_timeout_window(self):
        """
        Given: Configuration applied but not confirmed
        When: System reboots before timeout expires
        Then: System rolls back to previous configuration
        """

    def test_preserve_confirmed_config_after_reboot(self):
        """
        Given: Configuration applied and confirmed
        When: System reboots
        Then: Configuration persists across reboot
        """

    def test_handle_multiple_reboots_during_timeout(self):
        """
        Given: Configuration applied but not confirmed
        When: System reboots multiple times
        Then: System eventually rolls back after timeout
        """
```

### Scenario 4: Network Loss During Confirmation Window

**Objective**: Verify handling of network connectivity loss

```python
class TestNetworkLoss:
    """Test network loss scenarios"""

    def test_rollback_when_unable_to_confirm(self):
        """
        Given: Configuration breaks network connectivity
        When: User cannot reach system to confirm
        Then: System automatically rolls back after timeout
        """

    def test_out_of_band_confirmation(self):
        """
        Given: Primary network is down
        When: User confirms via console/serial/IPMI
        Then: Configuration is confirmed successfully
        """
```

### Scenario 5: System Crash Recovery

**Objective**: Verify recovery from system crashes

```python
class TestCrashRecovery:
    """Test crash recovery scenarios"""

    def test_recover_from_crash_during_apply(self):
        """
        Given: System crashes during config application
        When: System restarts
        Then: System detects incomplete apply and rolls back
        """

    def test_recover_from_crash_during_rollback(self):
        """
        Given: System crashes during rollback
        When: System restarts
        Then: System completes rollback operation
        """

    def test_recover_from_corrupted_state_file(self):
        """
        Given: State file corrupted during crash
        When: System attempts to read state
        Then: System handles corruption gracefully
        """
```

### Scenario 6: Concurrent Change Attempts

**Objective**: Verify prevention of concurrent operations

```python
class TestConcurrentOperations:
    """Test concurrent operation handling"""

    def test_reject_concurrent_apply_operations(self):
        """
        Given: Configuration change in progress
        When: Second apply is attempted
        Then: Second apply is rejected with clear error
        """

    def test_reject_apply_during_pending_confirmation(self):
        """
        Given: Configuration awaiting confirmation
        When: New configuration change attempted
        Then: New change is rejected until current resolved
        """

    def test_allow_status_check_during_pending_state(self):
        """
        Given: Configuration awaiting confirmation
        When: Status check is requested
        Then: Status check succeeds with current state info
        """
```

### Scenario 7: Partial Failure Scenarios

**Objective**: Verify handling of partial failures

```python
class TestPartialFailures:
    """Test partial failure scenarios"""

    def test_handle_backup_creation_failure(self):
        """
        Given: Disk full or permission error
        When: Backup creation fails
        Then: Apply operation is aborted with error
        """

    def test_handle_state_file_write_failure(self):
        """
        Given: State directory is readonly
        When: State file write attempted
        Then: Operation fails safely with error
        """

    def test_handle_partial_config_application(self):
        """
        Given: Multi-interface configuration
        When: One interface fails to configure
        Then: Entire operation is rolled back
        """
```

---

## Testing Challenges and Solutions

### Challenge 1: Testing Network Changes Safely

**Problem**: Cannot test actual network changes on host system without breaking connectivity

**Solutions**:

1. **Network Namespaces** (Primary Approach)
```python
# conftest.py

import subprocess
import pytest

@pytest.fixture
def network_namespace():
    """Create isolated network namespace for testing"""
    ns_name = f"test_ns_{uuid.uuid4().hex[:8]}"

    # Create namespace
    subprocess.run(['ip', 'netns', 'add', ns_name], check=True)

    # Create veth pair
    subprocess.run([
        'ip', 'link', 'add', f'veth0_{ns_name}',
        'type', 'veth', 'peer', 'name', f'veth1_{ns_name}'
    ], check=True)

    # Move one end to namespace
    subprocess.run([
        'ip', 'link', 'set', f'veth1_{ns_name}',
        'netns', ns_name
    ], check=True)

    yield ns_name

    # Cleanup
    subprocess.run(['ip', 'netns', 'del', ns_name], check=False)

@pytest.fixture
def isolated_network_config(network_namespace):
    """Provide isolated network configuration environment"""
    return NetworkConfigEnvironment(
        namespace=network_namespace,
        config_dir=f"/tmp/test_netplan_{uuid.uuid4().hex}",
        backup_dir=f"/tmp/test_backups_{uuid.uuid4().hex}",
        state_dir=f"/tmp/test_state_{uuid.uuid4().hex}"
    )
```

2. **Docker Containers**
```yaml
# docker-compose.test.yml

services:
  ubuntu-2004-test:
    image: ubuntu:20.04
    cap_add:
      - NET_ADMIN
      - NET_RAW
    volumes:
      - ./src:/app/src
      - ./tests:/app/tests
    networks:
      test_net:
        ipv4_address: 172.28.0.10

  ubuntu-2404-test:
    image: ubuntu:24.04
    cap_add:
      - NET_ADMIN
      - NET_RAW
    volumes:
      - ./src:/app/src
      - ./tests:/app/tests
    networks:
      test_net:
        ipv4_address: 172.28.0.11

networks:
  test_net:
    driver: bridge
    ipam:
      config:
        - subnet: 172.28.0.0/16
```

3. **Mock Network Commands**
```python
# tests/mocks/network_mock.py

class MockNetworkCommandExecutor:
    """Mock executor for network commands"""

    def __init__(self):
        self.executed_commands = []
        self.command_results = {}
        self.should_fail = False

    def execute(self, command):
        """Mock execution of network commands"""
        self.executed_commands.append(command)

        if self.should_fail:
            raise subprocess.CalledProcessError(1, command)

        return self.command_results.get(command, "")

    def set_failure_mode(self, should_fail=True):
        """Configure mock to simulate failures"""
        self.should_fail = should_fail

    def set_result(self, command, result):
        """Set result for specific command"""
        self.command_results[command] = result
```

### Challenge 2: Testing System Reboots

**Problem**: Cannot actually reboot system during tests

**Solutions**:

1. **State Persistence Simulation**
```python
# tests/fixtures/reboot_simulator.py

class RebootSimulator:
    """Simulate system reboot for testing"""

    def __init__(self, state_dir, config_dir):
        self.state_dir = state_dir
        self.config_dir = config_dir
        self.pre_reboot_state = None

    def capture_pre_reboot_state(self):
        """Capture state before simulated reboot"""
        self.pre_reboot_state = {
            'state_files': self._copy_state_files(),
            'config_files': self._copy_config_files(),
            'timestamp': time.time()
        }

    def simulate_reboot(self, time_passed=0):
        """Simulate reboot with time passage"""
        # Restore file system state
        self._restore_state_files(self.pre_reboot_state['state_files'])

        # Advance time
        if time_passed > 0:
            with freeze_time(
                datetime.now() + timedelta(seconds=time_passed)
            ):
                # Run boot recovery service
                BootRecoveryService(
                    state_dir=self.state_dir,
                    config_dir=self.config_dir
                ).check_and_recover()
```

2. **Service Integration Tests**
```python
# tests/integration/test_boot_recovery.py

def test_boot_recovery_service(reboot_simulator):
    """Test boot recovery service behavior"""
    # Apply configuration
    config_manager.apply_config(new_config, timeout=60)

    # Capture state before "reboot"
    reboot_simulator.capture_pre_reboot_state()

    # Simulate reboot after timeout expiration
    reboot_simulator.simulate_reboot(time_passed=70)

    # Verify rollback occurred
    assert config_manager.get_current_config() == original_config
```

### Challenge 3: Testing Time-Based Behavior

**Problem**: Testing timeouts requires waiting or complex time manipulation

**Solutions**:

1. **freezegun for Time Control**
```python
# tests/unit/test_timeout_behavior.py

from freezegun import freeze_time
from datetime import datetime, timedelta

def test_timeout_expiration():
    """Test timeout detection with time control"""
    start_time = datetime(2025, 1, 1, 12, 0, 0)

    with freeze_time(start_time) as frozen_time:
        # Start timeout monitor
        monitor = TimeoutMonitor(timeout_seconds=60)
        monitor.start()

        # Check before timeout
        assert not monitor.is_expired()

        # Advance time past timeout
        frozen_time.move_to(start_time + timedelta(seconds=61))

        # Check after timeout
        assert monitor.is_expired()
```

2. **Configurable Timeouts for Tests**
```python
# tests/conftest.py

@pytest.fixture
def fast_timeout_config():
    """Provide configuration with reduced timeouts for testing"""
    return ConfigManager(
        default_timeout=1,  # 1 second instead of 60
        grace_period=0.1    # 100ms instead of 5s
    )
```

### Challenge 4: Testing Filesystem Operations

**Problem**: Need to test filesystem errors without corrupting host

**Solutions**:

1. **Temporary Directories with pytest**
```python
# tests/conftest.py

@pytest.fixture
def temp_config_environment(tmp_path):
    """Create temporary configuration environment"""
    config_dir = tmp_path / "config"
    backup_dir = tmp_path / "backups"
    state_dir = tmp_path / "state"

    config_dir.mkdir()
    backup_dir.mkdir()
    state_dir.mkdir()

    return ConfigEnvironment(
        config_dir=str(config_dir),
        backup_dir=str(backup_dir),
        state_dir=str(state_dir)
    )
```

2. **Filesystem Fault Injection**
```python
# tests/mocks/filesystem_mock.py

class FailingFilesystem:
    """Mock filesystem that can simulate various failures"""

    def __init__(self, real_path):
        self.real_path = real_path
        self.fail_on_write = False
        self.fail_on_read = False
        self.disk_full = False

    def write_file(self, path, content):
        """Write file with potential failures"""
        if self.disk_full:
            raise OSError(28, "No space left on device")
        if self.fail_on_write:
            raise OSError(13, "Permission denied")
        # Actual write
        with open(os.path.join(self.real_path, path), 'w') as f:
            f.write(content)
```

### Challenge 5: Testing Concurrent Operations

**Problem**: Need to verify concurrent operation handling reliably

**Solutions**:

1. **pytest-xdist for Parallel Execution**
```python
# tests/concurrency/test_concurrent_operations.py

import pytest
import multiprocessing

def test_concurrent_apply_attempts(config_manager):
    """Test that concurrent applies are properly rejected"""

    def attempt_apply(config, result_queue):
        try:
            config_manager.apply_config(config)
            result_queue.put(('success', None))
        except ConcurrentOperationError as e:
            result_queue.put(('error', str(e)))

    result_queue = multiprocessing.Queue()

    # Start two processes attempting concurrent applies
    p1 = multiprocessing.Process(
        target=attempt_apply,
        args=(config1, result_queue)
    )
    p2 = multiprocessing.Process(
        target=attempt_apply,
        args=(config2, result_queue)
    )

    p1.start()
    p2.start()
    p1.join()
    p2.join()

    # Collect results
    results = [result_queue.get() for _ in range(2)]

    # Verify one succeeded and one failed
    assert sum(1 for r in results if r[0] == 'success') == 1
    assert sum(1 for r in results if r[0] == 'error') == 1
```

2. **Threading-based Tests**
```python
import threading
import time

def test_lock_prevents_concurrent_access():
    """Test lock manager prevents concurrent access"""
    lock_manager = LockManager()
    results = []

    def try_acquire(delay=0):
        time.sleep(delay)
        acquired = lock_manager.try_acquire(timeout=1)
        results.append(acquired)
        if acquired:
            time.sleep(0.5)
            lock_manager.release()

    # Start threads
    t1 = threading.Thread(target=try_acquire, args=(0,))
    t2 = threading.Thread(target=try_acquire, args=(0.1,))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # One should succeed, one should fail
    assert results.count(True) == 1
    assert results.count(False) == 1
```

---

## Test Fixtures and Data

### Sample Netplan Configurations

```python
# tests/fixtures/netplan_configs.py

NETPLAN_DHCP_SINGLE_INTERFACE = """
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      dhcp4: true
"""

NETPLAN_STATIC_SINGLE_INTERFACE = """
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      addresses:
        - 192.168.1.100/24
      gateway4: 192.168.1.1
      nameservers:
        addresses:
          - 8.8.8.8
          - 8.8.4.4
"""

NETPLAN_MULTIPLE_INTERFACES = """
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      addresses:
        - 192.168.1.100/24
      gateway4: 192.168.1.1
      nameservers:
        addresses:
          - 8.8.8.8
    eth1:
      addresses:
        - 192.168.2.1/24
    eth2:
      dhcp4: true
"""

NETPLAN_COMPLEX_ROUTING = """
network:
  version: 2
  renderer: networkd
  ethernets:
    enp1s0:
      addresses:
        - 172.21.198.44/24
        - 192.168.10.1/24
      dhcp4: true
    enp2s0:
      addresses:
        - 192.168.9.1/24
      dhcp4: true
    enp3s0:
      addresses:
        - 192.168.7.1/24
      dhcp4: true
    enp4s0:
      addresses:
        - 192.168.8.1/24
      dhcp4: true
"""

NETPLAN_INVALID_YAML = """
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      addresses:
        - 192.168.1.100/24
      gateway4: 192.168.1.1
    # Missing closing bracket
"""

NETPLAN_INVALID_IP = """
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      addresses:
        - 999.999.999.999/24
"""
```

### Sample NetworkManager Configurations

```python
# tests/fixtures/networkmanager_configs.py

NM_DHCP_CONNECTION = """
[connection]
id=Wired connection 1
uuid=12345678-1234-1234-1234-123456789abc
type=ethernet
interface-name=eth0

[ethernet]

[ipv4]
method=auto

[ipv6]
method=ignore
"""

NM_STATIC_CONNECTION = """
[connection]
id=Wired connection 1
uuid=12345678-1234-1234-1234-123456789abc
type=ethernet
interface-name=eth0

[ethernet]

[ipv4]
method=manual
address1=192.168.1.100/24,192.168.1.1
dns=8.8.8.8;8.8.4.4;

[ipv6]
method=ignore
"""
```

### Mock Semaphore File States

```python
# tests/fixtures/semaphore_states.py

SEMAPHORE_PENDING = {
    "state": "pending",
    "timestamp": "2025-01-01T12:00:00Z",
    "timeout_seconds": 60,
    "backup_file": "/etc/netplan/.backups/00-installer-config.yaml.bak.20250101-120000",
    "config_file": "/etc/netplan/00-installer-config.yaml",
    "user": "admin"
}

SEMAPHORE_APPLIED = {
    "state": "applied",
    "timestamp": "2025-01-01T12:00:30Z",
    "timeout_seconds": 60,
    "deadline": "2025-01-01T12:01:30Z",
    "backup_file": "/etc/netplan/.backups/00-installer-config.yaml.bak.20250101-120000",
    "config_file": "/etc/netplan/00-installer-config.yaml",
    "user": "admin"
}

SEMAPHORE_CONFIRMED = {
    "state": "confirmed",
    "timestamp": "2025-01-01T12:00:45Z",
    "applied_timestamp": "2025-01-01T12:00:30Z",
    "confirmed_timestamp": "2025-01-01T12:00:45Z",
    "backup_file": "/etc/netplan/.backups/00-installer-config.yaml.bak.20250101-120000",
    "config_file": "/etc/netplan/00-installer-config.yaml",
    "user": "admin"
}

SEMAPHORE_ROLLED_BACK = {
    "state": "rolled_back",
    "timestamp": "2025-01-01T12:02:00Z",
    "applied_timestamp": "2025-01-01T12:00:30Z",
    "rollback_timestamp": "2025-01-01T12:02:00Z",
    "rollback_reason": "timeout_expired",
    "backup_file": "/etc/netplan/.backups/00-installer-config.yaml.bak.20250101-120000",
    "config_file": "/etc/netplan/00-installer-config.yaml",
    "user": "admin"
}

SEMAPHORE_CORRUPTED = """
{
    "state": "applied",
    "timestamp": "2025-01-01T12:00:30Z"
    # Missing comma and closing brace - corrupted JSON
"""
```

### Backup File Test Cases

```python
# tests/fixtures/backup_scenarios.py

@pytest.fixture
def backup_history(tmp_path):
    """Create mock backup file history"""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    # Create sequence of backup files
    backups = [
        "00-installer-config.yaml.bak.20250101-100000",
        "00-installer-config.yaml.bak.20250101-110000",
        "00-installer-config.yaml.bak.20250101-120000",
        "00-installer-config.yaml.bak.20250101-130000",
        "00-installer-config.yaml.bak.20250101-140000",
    ]

    for backup in backups:
        (backup_dir / backup).write_text(NETPLAN_DHCP_SINGLE_INTERFACE)

    return backup_dir
```

---

## Safety Testing

### Principle: Never Leave System in Unrecoverable State

All safety tests must verify that the system can recover from any failure mode.

### Test Category 1: Rollback Verification

```python
# tests/safety/test_rollback_verification.py

class TestRollbackSafety:
    """Verify rollback safety in all scenarios"""

    def test_rollback_restores_exact_previous_config(self):
        """Rollback must restore byte-for-byte identical config"""
        original_config = config_manager.get_current_config()

        # Apply new config
        config_manager.apply_config(new_config)

        # Trigger rollback
        config_manager.rollback()

        # Verify exact restoration
        restored_config = config_manager.get_current_config()
        assert restored_config == original_config
        assert hashlib.sha256(restored_config.encode()).hexdigest() == \
               hashlib.sha256(original_config.encode()).hexdigest()

    def test_rollback_works_with_corrupted_new_config(self):
        """Rollback must work even if new config is corrupted"""
        original_config = config_manager.get_current_config()

        # Apply config
        config_manager.apply_config(new_config)

        # Corrupt the new config file
        with open(config_manager.config_path, 'w') as f:
            f.write("corrupted garbage data")

        # Rollback should still work
        config_manager.rollback()

        restored_config = config_manager.get_current_config()
        assert restored_config == original_config

    def test_rollback_works_after_partial_apply(self):
        """Rollback must work even after partial application"""
        # Test with multi-interface config where one fails
        # Rollback should restore all interfaces correctly

    def test_rollback_works_after_system_crash(self, reboot_simulator):
        """Rollback must complete even after system crash"""
        # Apply config
        config_manager.apply_config(new_config)

        # Simulate crash during apply
        reboot_simulator.simulate_crash_during_operation()

        # Boot recovery should complete rollback
        reboot_simulator.simulate_reboot()

        assert config_manager.get_current_config() == original_config
```

### Test Category 2: Configuration Integrity

```python
# tests/safety/test_config_integrity.py

class TestConfigurationIntegrity:
    """Verify configuration file integrity"""

    def test_backup_matches_original_exactly(self):
        """Backup must be byte-for-byte identical to original"""
        original_content = read_file(config_path)
        original_hash = hashlib.sha256(original_content.encode()).hexdigest()

        # Create backup
        backup_manager.create_backup(config_path)

        # Verify backup
        backup_content = read_file(backup_manager.latest_backup)
        backup_hash = hashlib.sha256(backup_content.encode()).hexdigest()

        assert original_hash == backup_hash

    def test_atomic_writes_prevent_corruption(self):
        """Configuration writes must be atomic"""
        # Start write operation
        write_thread = threading.Thread(
            target=lambda: config_manager.write_config(large_config)
        )
        write_thread.start()

        # Interrupt during write
        time.sleep(0.01)
        write_thread._stop()  # Simulate process kill

        # File should either have old content or new content, never partial
        current_content = read_file(config_path)
        assert current_content in [original_config, large_config]

    def test_backup_verification_detects_corruption(self):
        """Backup verification must detect corrupted backups"""
        # Create backup
        backup_path = backup_manager.create_backup(config_path)

        # Corrupt backup
        with open(backup_path, 'a') as f:
            f.write("corrupted data")

        # Verification should fail
        with pytest.raises(BackupCorruptionError):
            backup_manager.verify_backup(backup_path)
```

### Test Category 3: State Machine Correctness

```python
# tests/safety/test_state_machine.py

class TestStateMachineSafety:
    """Verify state machine cannot enter invalid states"""

    def test_all_valid_state_transitions(self):
        """Test all valid state transitions"""
        valid_transitions = [
            (None, "pending"),
            ("pending", "applied"),
            ("applied", "confirmed"),
            ("applied", "rolled_back"),
        ]

        for from_state, to_state in valid_transitions:
            state_manager.set_state(from_state)
            state_manager.transition_to(to_state)
            assert state_manager.current_state == to_state

    def test_invalid_state_transitions_rejected(self):
        """Invalid state transitions must be rejected"""
        invalid_transitions = [
            (None, "confirmed"),
            (None, "rolled_back"),
            ("pending", "confirmed"),
            ("pending", "rolled_back"),
            ("confirmed", "pending"),
            ("confirmed", "applied"),
            ("rolled_back", "pending"),
            ("rolled_back", "applied"),
        ]

        for from_state, to_state in invalid_transitions:
            state_manager.set_state(from_state)
            with pytest.raises(InvalidStateTransitionError):
                state_manager.transition_to(to_state)

    def test_state_persistence_across_failures(self):
        """State must be persistent across process failures"""
        # Set state
        state_manager.set_state("applied")

        # Simulate process crash
        del state_manager

        # Create new instance
        new_state_manager = StateManager()

        # State should be restored
        assert new_state_manager.current_state == "applied"
```

### Test Category 4: Race Condition Prevention

```python
# tests/safety/test_race_conditions.py

class TestRaceConditionPrevention:
    """Verify prevention of race conditions"""

    def test_concurrent_applies_prevented(self):
        """Concurrent applies must be prevented"""
        barrier = threading.Barrier(2)
        results = []

        def try_apply():
            barrier.wait()  # Synchronize start
            try:
                config_manager.apply_config(new_config)
                results.append("success")
            except ConcurrentOperationError:
                results.append("rejected")

        t1 = threading.Thread(target=try_apply)
        t2 = threading.Thread(target=try_apply)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly one should succeed
        assert results.count("success") == 1
        assert results.count("rejected") == 1

    def test_state_file_locking(self):
        """State file must be locked during writes"""
        # Implementation depends on locking mechanism
        pass

    def test_backup_directory_locking(self):
        """Backup directory must be locked during operations"""
        pass
```

### Test Category 5: Data Loss Prevention

```python
# tests/safety/test_data_loss_prevention.py

class TestDataLossPrevention:
    """Verify no data loss in failure scenarios"""

    def test_backup_always_created_before_apply(self):
        """Backup must be created before applying changes"""
        # Track filesystem operations
        fs_monitor = FilesystemMonitor()

        with fs_monitor:
            config_manager.apply_config(new_config)

        operations = fs_monitor.get_operations()

        # Find backup creation and config modification
        backup_time = next(
            op.timestamp for op in operations
            if "backup" in op.path
        )
        config_time = next(
            op.timestamp for op in operations
            if "00-installer-config.yaml" in op.path
        )

        # Backup must come first
        assert backup_time < config_time

    def test_backups_never_deleted_without_confirmation(self):
        """Backups must not be deleted without confirmation"""
        # Apply and rollback multiple times
        for _ in range(5):
            config_manager.apply_config(new_config)
            config_manager.rollback()

        # All backups should still exist
        backups = backup_manager.list_backups()
        assert len(backups) >= 5

    def test_minimum_backup_retention(self):
        """Minimum number of backups must always be retained"""
        # Create many backups
        for i in range(20):
            config_manager.apply_config(new_config)
            config_manager.confirm()

        # Trigger cleanup
        backup_manager.cleanup_old_backups(keep_minimum=5)

        # At least 5 should remain
        assert len(backup_manager.list_backups()) >= 5
```

---

## Testing Tools and Infrastructure

### pytest Configuration

```ini
# pytest.ini

[pytest]
minversion = 8.0
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# Output options
addopts =
    -ra
    --strict-markers
    --strict-config
    --showlocals
    --tb=short
    --cov=ace_network_manager
    --cov-report=term-missing
    --cov-report=html
    --cov-report=xml
    --cov-fail-under=85

# Test markers
markers =
    unit: Unit tests
    integration: Integration tests
    e2e: End-to-end tests
    safety: Safety-critical tests
    chaos: Chaos testing
    slow: Slow-running tests
    requires_root: Tests requiring root privileges
    requires_docker: Tests requiring Docker
    ubuntu_2004: Tests specific to Ubuntu 20.04
    ubuntu_2404: Tests specific to Ubuntu 24.04

# Timeout configuration
timeout = 300
timeout_method = thread

# Coverage configuration
[coverage:run]
source = ace_network_manager
omit =
    */tests/*
    */test_*.py
    */__pycache__/*
    */site-packages/*

[coverage:report]
precision = 2
show_missing = True
skip_covered = False

exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
    if TYPE_CHECKING:
    @abstractmethod
```

### pytest Plugins and Extensions

```toml
# pyproject.toml - testing dependencies

[dependency-groups]
test = [
    "pytest>=8.4.2",
    "pytest-cov>=6.0.0",
    "pytest-mock>=3.14.0",
    "pytest-asyncio>=0.25.2",
    "pytest-timeout>=2.3.1",
    "pytest-xdist>=3.6.1",
    "pytest-bdd>=8.0.0",
    "pytest-benchmark>=5.1.0",
    "pytest-randomly>=3.16.0",
    "freezegun>=1.5.1",
    "hypothesis>=6.122.3",
    "faker>=34.0.0",
]
```

### Mock/Patch Strategies

```python
# tests/conftest.py

import pytest
from unittest.mock import Mock, patch, MagicMock
from ace_network_manager import (
    ConfigManager,
    BackupManager,
    StateManager,
    NetworkApplier
)

@pytest.fixture
def mock_subprocess():
    """Mock subprocess for command execution"""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(
            returncode=0,
            stdout="",
            stderr=""
        )
        yield mock_run

@pytest.fixture
def mock_file_operations():
    """Mock file operations"""
    with patch('builtins.open', create=True) as mock_open:
        yield mock_open

@pytest.fixture
def mock_network_applier():
    """Mock network applier for testing without actual network changes"""
    with patch('ace_network_manager.NetworkApplier') as mock_applier:
        instance = mock_applier.return_value
        instance.apply_config = Mock(return_value=True)
        instance.rollback_config = Mock(return_value=True)
        instance.validate_config = Mock(return_value=True)
        yield instance

@pytest.fixture
def mock_systemd():
    """Mock systemd interactions"""
    with patch('subprocess.run') as mock_run:
        def systemctl_side_effect(cmd, *args, **kwargs):
            if 'systemctl' in cmd:
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = systemctl_side_effect
        yield mock_run
```

### Fixtures and Factories

```python
# tests/factories.py

import factory
from faker import Faker
from datetime import datetime, timedelta

fake = Faker()

class NetworkConfigFactory(factory.Factory):
    """Factory for generating test network configurations"""

    class Meta:
        model = dict

    version = 2
    renderer = "networkd"

    @factory.lazy_attribute
    def ethernets(self):
        return {
            f"eth{i}": {
                "addresses": [f"192.168.{i}.1/24"],
                "gateway4": f"192.168.{i}.254"
            }
            for i in range(1, fake.random_int(min=1, max=4))
        }

class BackupFileFactory(factory.Factory):
    """Factory for generating test backup files"""

    class Meta:
        model = dict

    filename = factory.LazyAttribute(
        lambda o: f"00-installer-config.yaml.bak.{o.timestamp}"
    )
    timestamp = factory.LazyAttribute(
        lambda o: datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    path = factory.LazyAttribute(
        lambda o: f"/tmp/backups/{o.filename}"
    )
    size = factory.LazyAttribute(
        lambda o: fake.random_int(min=100, max=5000)
    )

class SemaphoreStateFactory(factory.Factory):
    """Factory for generating test semaphore states"""

    class Meta:
        model = dict

    state = factory.Iterator(["pending", "applied", "confirmed", "rolled_back"])
    timestamp = factory.LazyAttribute(
        lambda o: datetime.now().isoformat()
    )
    timeout_seconds = 60
    backup_file = factory.LazyAttribute(
        lambda o: f"/tmp/backups/backup.{fake.uuid4()}.yaml"
    )
```

### Coverage Requirements

```python
# tests/coverage_requirements.py

# Minimum coverage requirements by component
COVERAGE_REQUIREMENTS = {
    "ace_network_manager.config_manager": 95,
    "ace_network_manager.backup_manager": 98,
    "ace_network_manager.state_manager": 98,
    "ace_network_manager.timeout_monitor": 95,
    "ace_network_manager.network_applier": 85,  # Lower due to system interaction
    "ace_network_manager.lock_manager": 100,
    "ace_network_manager.service_integration": 90,
}

# Functions that must have 100% coverage (safety-critical)
CRITICAL_FUNCTIONS = [
    "backup_manager.create_backup",
    "backup_manager.restore_backup",
    "state_manager.transition_state",
    "timeout_monitor.check_timeout",
    "network_applier.rollback_configuration",
    "lock_manager.acquire_lock",
    "lock_manager.release_lock",
]
```

### Testing in Network Namespaces

```python
# tests/infrastructure/network_namespace.py

import subprocess
import uuid
from contextlib import contextmanager

class NetworkNamespace:
    """Manage network namespaces for testing"""

    def __init__(self, name=None):
        self.name = name or f"test_ns_{uuid.uuid4().hex[:8]}"
        self.created = False

    def create(self):
        """Create the network namespace"""
        subprocess.run(['ip', 'netns', 'add', self.name], check=True)
        self.created = True

    def execute(self, command):
        """Execute command in namespace"""
        full_command = ['ip', 'netns', 'exec', self.name] + command
        return subprocess.run(full_command, capture_output=True, text=True)

    def add_veth_pair(self, peer_name="veth0"):
        """Add virtual ethernet pair to namespace"""
        veth_host = f"veth_host_{self.name}"
        veth_ns = f"veth_ns_{self.name}"

        # Create veth pair
        subprocess.run([
            'ip', 'link', 'add', veth_host,
            'type', 'veth', 'peer', 'name', veth_ns
        ], check=True)

        # Move one end to namespace
        subprocess.run([
            'ip', 'link', 'set', veth_ns,
            'netns', self.name
        ], check=True)

        # Bring up interfaces
        subprocess.run(['ip', 'link', 'set', veth_host, 'up'], check=True)
        self.execute(['ip', 'link', 'set', veth_ns, 'up'])

        return veth_host, veth_ns

    def configure_interface(self, interface, ip_address):
        """Configure interface in namespace"""
        self.execute(['ip', 'addr', 'add', ip_address, 'dev', interface])

    def cleanup(self):
        """Delete the network namespace"""
        if self.created:
            subprocess.run(['ip', 'netns', 'del', self.name], check=False)
            self.created = False

    def __enter__(self):
        self.create()
        return self

    def __exit__(self, *args):
        self.cleanup()

# Pytest fixture
@pytest.fixture
def network_namespace():
    """Provide isolated network namespace for testing"""
    ns = NetworkNamespace()
    ns.create()
    ns.add_veth_pair()

    yield ns

    ns.cleanup()
```

---

## CI/CD Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/test.yml

name: Test Suite

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

jobs:
  unit-tests:
    name: Unit Tests
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13"]

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh

      - name: Set up Python ${{ matrix.python-version }}
        run: uv python install ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          uv sync --all-groups

      - name: Run ruff lint
        run: uv run ruff check src tests

      - name: Run ruff format check
        run: uv run ruff format --check src tests

      - name: Run pyrefly type checking
        run: uv run pyrefly check src

      - name: Run unit tests
        run: |
          uv run pytest tests/unit -v \
            --cov=ace_network_manager \
            --cov-report=xml \
            --cov-report=term \
            --junit-xml=junit-unit.xml

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
          flags: unit-tests
          name: unit-${{ matrix.python-version }}

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: unit-test-results-${{ matrix.python-version }}
          path: junit-unit.xml

  integration-tests:
    name: Integration Tests
    runs-on: ubuntu-latest
    needs: unit-tests

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh

      - name: Install dependencies
        run: uv sync --all-groups

      - name: Run integration tests
        run: |
          uv run pytest tests/integration -v \
            --cov=ace_network_manager \
            --cov-report=xml \
            --junit-xml=junit-integration.xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
          flags: integration-tests

  e2e-tests-ubuntu-2004:
    name: E2E Tests (Ubuntu 20.04)
    runs-on: ubuntu-20.04
    needs: integration-tests

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh

      - name: Install dependencies
        run: uv sync --all-groups

      - name: Set up network namespace capabilities
        run: |
          sudo setcap cap_net_admin+eip $(which python3)

      - name: Run E2E tests
        run: |
          uv run pytest tests/e2e -v \
            -m "ubuntu_2004" \
            --junit-xml=junit-e2e-2004.xml

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: e2e-test-results-2004
          path: junit-e2e-2004.xml

  e2e-tests-ubuntu-2404:
    name: E2E Tests (Ubuntu 24.04)
    runs-on: ubuntu-24.04
    needs: integration-tests

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh

      - name: Install dependencies
        run: uv sync --all-groups

      - name: Set up network namespace capabilities
        run: |
          sudo setcap cap_net_admin+eip $(which python3)

      - name: Run E2E tests
        run: |
          uv run pytest tests/e2e -v \
            -m "ubuntu_2404" \
            --junit-xml=junit-e2e-2404.xml

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: e2e-test-results-2404
          path: junit-e2e-2404.xml

  safety-tests:
    name: Safety & Chaos Tests
    runs-on: ubuntu-latest
    needs: integration-tests

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh

      - name: Install dependencies
        run: uv sync --all-groups

      - name: Run safety tests
        run: |
          uv run pytest tests/safety -v \
            --junit-xml=junit-safety.xml

      - name: Run chaos tests
        run: |
          uv run pytest tests/chaos -v \
            --junit-xml=junit-chaos.xml

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: safety-chaos-test-results
          path: |
            junit-safety.xml
            junit-chaos.xml

  docker-tests:
    name: Docker Container Tests
    runs-on: ubuntu-latest
    needs: unit-tests

    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build test containers
        run: |
          docker-compose -f docker-compose.test.yml build

      - name: Run tests in Ubuntu 20.04 container
        run: |
          docker-compose -f docker-compose.test.yml run \
            ubuntu-2004-test \
            pytest tests/e2e -v -m "ubuntu_2004"

      - name: Run tests in Ubuntu 24.04 container
        run: |
          docker-compose -f docker-compose.test.yml run \
            ubuntu-2404-test \
            pytest tests/e2e -v -m "ubuntu_2404"

      - name: Cleanup
        if: always()
        run: docker-compose -f docker-compose.test.yml down

  performance-tests:
    name: Performance Tests
    runs-on: ubuntu-latest
    needs: integration-tests

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh

      - name: Install dependencies
        run: uv sync --all-groups

      - name: Run performance benchmarks
        run: |
          uv run pytest tests/performance -v \
            --benchmark-only \
            --benchmark-json=benchmark-results.json

      - name: Store benchmark results
        uses: benchmark-action/github-action-benchmark@v1
        with:
          tool: 'pytest'
          output-file-path: benchmark-results.json
          github-token: ${{ secrets.GITHUB_TOKEN }}
          auto-push: true

  coverage-report:
    name: Coverage Report
    runs-on: ubuntu-latest
    needs: [unit-tests, integration-tests, e2e-tests-ubuntu-2004, e2e-tests-ubuntu-2404]

    steps:
      - uses: actions/checkout@v4

      - name: Download all coverage artifacts
        uses: actions/download-artifact@v4

      - name: Combine coverage reports
        run: |
          pip install coverage
          coverage combine
          coverage report
          coverage html

      - name: Upload combined coverage
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
          flags: combined
```

### Pre-commit Hooks

```yaml
# .pre-commit-config.yaml

repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.2
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: local
    hooks:
      - id: pyrefly
        name: pyrefly type checking
        entry: uv run pyrefly check
        language: system
        types: [python]
        pass_filenames: false

      - id: pytest-unit
        name: pytest unit tests
        entry: uv run pytest tests/unit -v
        language: system
        pass_filenames: false
        stages: [commit]

      - id: pytest-safety
        name: pytest safety tests
        entry: uv run pytest tests/safety -v
        language: system
        pass_filenames: false
        stages: [push]
```

### Test Environment Setup Script

```bash
#!/bin/bash
# scripts/setup_test_environment.sh

set -e

echo "Setting up test environment..."

# Install system dependencies
sudo apt-get update
sudo apt-get install -y \
    iproute2 \
    netplan.io \
    network-manager \
    systemd

# Install uv if not present
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# Create virtual environment and install dependencies
uv sync --all-groups

# Set up test directories
mkdir -p tests/{unit,integration,e2e,safety,chaos,performance}
mkdir -p tests/fixtures/{configs,states,backups}

# Set up network namespace capabilities (requires root)
if [ "$EUID" -eq 0 ]; then
    echo "Setting network capabilities for testing..."
    PYTHON_PATH=$(which python3)
    setcap cap_net_admin+eip "$PYTHON_PATH"
else
    echo "Warning: Not running as root. Network namespace tests may fail."
    echo "Run with sudo to set network capabilities."
fi

echo "Test environment setup complete!"
echo "Run tests with: uv run pytest"
```

---

## Risk Areas and Mitigation

### High-Risk Area 1: Network Connectivity Loss

**Risk**: Configuration change breaks network connectivity, preventing confirmation

**Severity**: CRITICAL

**Mitigation Strategy**:
1. **Mandatory timeout with automatic rollback**
   - Default timeout: 60 seconds
   - Maximum timeout: 300 seconds (5 minutes)
   - No option to disable timeout

2. **Pre-apply validation**
   - Validate configuration syntax before applying
   - Check for obvious misconfigurations (invalid IPs, missing gateways)
   - Warn about risky changes (removing all interfaces, changing primary interface)

3. **Multiple confirmation methods**
   - SSH/network confirmation (primary)
   - Console confirmation (fallback)
   - Serial console confirmation (remote datacenter)
   - IPMI/iLO confirmation (out-of-band)

4. **Testing Requirements**:
   ```python
   def test_broken_network_auto_rollback():
       """Must rollback when network becomes unreachable"""
       # Apply config that breaks network
       # Verify automatic rollback after timeout
       # Verify network connectivity restored
   ```

### High-Risk Area 2: Backup Corruption or Loss

**Risk**: Backup file corrupted or lost, preventing rollback

**Severity**: CRITICAL

**Mitigation Strategy**:
1. **Backup verification**
   - Verify backup immediately after creation
   - Store checksum with backup
   - Test restoration before applying changes (optional mode)

2. **Multiple backup retention**
   - Keep minimum 5 backups
   - Never delete last known-good backup
   - Implement backup rotation with retention policy

3. **Backup redundancy**
   - Store backups in multiple locations
   - Consider remote backup storage for critical systems

4. **Testing Requirements**:
   ```python
   def test_handle_corrupted_backup():
       """Must handle corrupted backup files"""

   def test_rollback_to_older_backup():
       """Must rollback to older backup if latest corrupted"""
   ```

### High-Risk Area 3: State File Corruption

**Risk**: Semaphore/state file corrupted, losing track of pending changes

**Severity**: HIGH

**Mitigation Strategy**:
1. **Atomic state file writes**
   - Write to temporary file, then rename
   - Use fsync to ensure durability

2. **State file validation**
   - Validate JSON format on read
   - Include checksum in state file
   - Handle corruption gracefully

3. **State recovery from context**
   - If state file lost, infer state from filesystem
   - Compare timestamps of config vs backups
   - Conservative approach: assume pending if uncertain

4. **Testing Requirements**:
   ```python
   def test_recover_from_missing_state_file():
       """Must infer state from filesystem if state file missing"""

   def test_recover_from_corrupted_state_file():
       """Must handle corrupted state file gracefully"""
   ```

### High-Risk Area 4: Concurrent Operations

**Risk**: Multiple processes attempting configuration changes simultaneously

**Severity**: HIGH

**Mitigation Strategy**:
1. **Mandatory locking**
   - Use file-based locks (flock)
   - Acquire lock before any operation
   - Automatic lock cleanup on process death

2. **Clear error messages**
   - Inform user of conflicting operation
   - Show which process holds lock
   - Suggest retry after resolution

3. **Lock timeout**
   - Detect stale locks from crashed processes
   - Clean up after verification

4. **Testing Requirements**:
   ```python
   def test_concurrent_applies_rejected():
       """Must reject concurrent apply operations"""

   def test_stale_lock_cleanup():
       """Must clean up stale locks from dead processes"""
   ```

### High-Risk Area 5: Timeout Calculation Errors

**Risk**: Incorrect timeout calculation leads to premature or delayed rollback

**Severity**: HIGH

**Mitigation Strategy**:
1. **Use monotonic time**
   - Use `time.monotonic()` instead of `time.time()`
   - Immune to system clock changes
   - Handles DST transitions correctly

2. **Timeout grace period**
   - Add small grace period to timeout
   - Account for system load delays
   - Log when grace period is used

3. **Explicit timeout storage**
   - Store absolute deadline time
   - Store original timeout duration
   - Allow recalculation if needed

4. **Testing Requirements**:
   ```python
   def test_timeout_with_clock_change():
       """Timeout must work correctly even if system clock changes"""

   def test_timeout_across_dst_transition():
       """Timeout must handle DST transitions correctly"""
   ```

### High-Risk Area 6: Partial Application Failures

**Risk**: Some network interfaces configured successfully, others fail

**Severity**: MEDIUM-HIGH

**Mitigation Strategy**:
1. **Transactional application**
   - All-or-nothing approach
   - Rollback partial changes on any failure
   - Validate all interfaces before committing

2. **Interface dependency checking**
   - Detect interface dependencies
   - Apply in correct order
   - Rollback in reverse order

3. **Testing Requirements**:
   ```python
   def test_rollback_partial_application():
       """Must rollback all changes if any interface fails"""
   ```

### High-Risk Area 7: System Boot Race Conditions

**Risk**: Boot recovery service runs too early or too late

**Severity**: MEDIUM

**Mitigation Strategy**:
1. **Correct systemd dependencies**
   - Run after filesystem mounted
   - Run before network target
   - Use appropriate systemd ordering

2. **Retry logic**
   - Retry if required files not yet available
   - Timeout after reasonable period
   - Log all retry attempts

3. **Testing Requirements**:
   ```python
   def test_boot_recovery_timing():
       """Boot recovery must run at correct time in boot sequence"""
   ```

### High-Risk Area 8: Permission and Ownership Issues

**Risk**: Files created with wrong permissions, preventing access

**Severity**: MEDIUM

**Mitigation Strategy**:
1. **Explicit permission setting**
   - Set permissions explicitly on all created files
   - Preserve permissions when copying
   - Use appropriate umask

2. **Root requirement checking**
   - Verify running as root before starting
   - Clear error message if not root
   - No silent permission failures

3. **Testing Requirements**:
   ```python
   def test_backup_preserves_permissions():
       """Backup must preserve file permissions and ownership"""
   ```

---

## Test Execution Matrix

### Test Execution Priority

| Priority | Test Type | Frequency | Trigger | Duration |
|----------|-----------|-----------|---------|----------|
| P0 | Safety Tests | Every commit | Pre-commit hook | < 1 min |
| P0 | Unit Tests | Every commit | Pre-commit hook | < 2 min |
| P1 | Integration Tests | Every push | CI pipeline | < 5 min |
| P1 | Linting & Type Checking | Every commit | Pre-commit hook | < 30 sec |
| P2 | E2E Tests (Ubuntu 20.04) | Every PR | CI pipeline | < 10 min |
| P2 | E2E Tests (Ubuntu 24.04) | Every PR | CI pipeline | < 10 min |
| P3 | Chaos Tests | Every PR | CI pipeline | < 15 min |
| P3 | Performance Tests | Every PR | CI pipeline | < 10 min |
| P4 | Full Test Suite | Nightly | Scheduled | < 30 min |

### Platform Test Matrix

| Platform | Python Version | Test Types | Container | Required |
|----------|---------------|------------|-----------|----------|
| Ubuntu 20.04 | 3.8, 3.9, 3.10 | All | Docker | Yes |
| Ubuntu 24.04 | 3.11, 3.12, 3.13 | All | Docker | Yes |
| Ubuntu 22.04 | 3.10, 3.11 | Unit, Integration | Docker | Optional |
| Local Dev | 3.10+ | Unit, Integration | Native | Yes |

---

## Appendix: Test Command Reference

### Run All Tests
```bash
uv run pytest
```

### Run Tests by Type
```bash
# Unit tests only
uv run pytest tests/unit -v

# Integration tests only
uv run pytest tests/integration -v

# E2E tests only
uv run pytest tests/e2e -v

# Safety tests only
uv run pytest tests/safety -v

# Chaos tests only
uv run pytest tests/chaos -v
```

### Run Tests by Marker
```bash
# Run only Ubuntu 20.04 tests
uv run pytest -m ubuntu_2004

# Run only Ubuntu 24.04 tests
uv run pytest -m ubuntu_2404

# Run only safety-critical tests
uv run pytest -m safety

# Run slow tests
uv run pytest -m slow
```

### Run with Coverage
```bash
# Basic coverage report
uv run pytest --cov=ace_network_manager

# Detailed coverage report
uv run pytest --cov=ace_network_manager --cov-report=html --cov-report=term-missing

# Coverage with branch coverage
uv run pytest --cov=ace_network_manager --cov-branch
```

### Run Specific Test Files
```bash
# Single test file
uv run pytest tests/unit/test_config_manager.py -v

# Multiple test files
uv run pytest tests/unit/test_config_manager.py tests/unit/test_backup_manager.py -v
```

### Run Specific Test Functions
```bash
# Single test function
uv run pytest tests/unit/test_config_manager.py::test_parse_valid_config -v

# Test class
uv run pytest tests/unit/test_config_manager.py::TestConfigurationParser -v
```

### Run in Parallel
```bash
# Run tests in parallel (requires pytest-xdist)
uv run pytest -n auto

# Run with specific number of workers
uv run pytest -n 4
```

### Run with Timeout
```bash
# Set timeout for all tests
uv run pytest --timeout=60

# Disable timeout
uv run pytest --timeout=0
```

### Run Failed Tests Only
```bash
# Rerun only failed tests from last run
uv run pytest --lf

# Run failed tests first, then others
uv run pytest --ff
```

### Debug Mode
```bash
# Run with pdb on failure
uv run pytest --pdb

# Run with verbose output and show local variables
uv run pytest -vv --showlocals

# Run with print statements visible
uv run pytest -s
```

### Benchmark Tests
```bash
# Run performance benchmarks
uv run pytest tests/performance --benchmark-only

# Save benchmark results
uv run pytest tests/performance --benchmark-save=results

# Compare with previous benchmark
uv run pytest tests/performance --benchmark-compare=results
```

---

## Summary

This comprehensive testing strategy provides:

1. **Multi-layered Testing**: Unit, integration, E2E, chaos, and performance testing
2. **Safety-First Approach**: Extensive safety testing for critical failure modes
3. **Platform Coverage**: Testing on both Ubuntu 20.04 and 24.04
4. **Isolation Mechanisms**: Network namespaces and containers for safe testing
5. **Comprehensive Fixtures**: Ready-to-use test data and mock configurations
6. **CI/CD Integration**: Complete GitHub Actions workflow
7. **Risk Mitigation**: Identified high-risk areas with specific mitigation tests
8. **Clear Documentation**: Detailed test scenarios and implementation guidance

The strategy ensures that the safe network configuration manager can be thoroughly tested without risk to production systems, while providing confidence that all failure modes are handled correctly.

**Next Steps**:
1. Implement test infrastructure (fixtures, mocks, network namespaces)
2. Write unit tests for each component (starting with safety-critical functions)
3. Implement integration tests for state transitions
4. Create E2E test scenarios in Docker containers
5. Set up CI/CD pipeline
6. Establish coverage monitoring and enforcement
7. Document test results and maintain test suite
