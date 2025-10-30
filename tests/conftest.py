"""Pytest configuration and shared fixtures."""

import pytest


@pytest.fixture
def temp_state_dir(tmp_path):
    """Provide a temporary directory for state files."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
def temp_backup_dir(tmp_path):
    """Provide a temporary directory for backups."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    return backup_dir


@pytest.fixture
def temp_config_dir(tmp_path):
    """Provide a temporary directory for netplan configs."""
    config_dir = tmp_path / "netplan"
    config_dir.mkdir()
    return config_dir
