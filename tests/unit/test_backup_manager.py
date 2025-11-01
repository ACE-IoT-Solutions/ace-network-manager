"""Unit tests for BackupManager."""

from pathlib import Path

import pytest

from ace_network_manager.backup.manager import BackupManager
from ace_network_manager.core.exceptions import BackupError


class TestBackupManager:
    """Test BackupManager functionality."""

    def test_create_backup(self, tmp_path: Path) -> None:
        """Test creating a backup."""
        # Setup: create a sample netplan config
        config_dir = tmp_path / "netplan"
        config_dir.mkdir()

        config_file = config_dir / "00-config.yaml"
        config_file.write_text("""
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
""")

        backup_dir = tmp_path / "backups"
        manager = BackupManager(backup_dir=backup_dir, config_dir=config_dir)

        # Create backup
        backup_path, metadata = manager.create_backup(description="Test backup")

        assert backup_path.exists()
        assert backup_path.is_dir()

        # Check files exist
        assert (backup_path / "metadata.json").exists()
        assert (backup_path / "00-config.yaml").exists()
        assert (backup_path / "checksums.sha256").exists()

        # Check metadata
        assert metadata.description == "Test backup"
        assert "00-config.yaml" in metadata.source_configs
        assert "00-config.yaml" in metadata.checksums

        # Check 'latest' symlink
        latest_link = backup_dir / "latest"
        assert latest_link.exists()
        assert latest_link.is_symlink()

    def test_create_backup_multiple_files(self, tmp_path: Path) -> None:
        """Test backup with multiple netplan files."""
        config_dir = tmp_path / "netplan"
        config_dir.mkdir()

        # Create multiple config files
        (config_dir / "00-installer.yaml").write_text("""
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
""")
        (config_dir / "01-custom.yaml").write_text("""
network:
  version: 2
  ethernets:
    eth1:
      dhcp4: true
""")

        backup_dir = tmp_path / "backups"
        manager = BackupManager(backup_dir=backup_dir, config_dir=config_dir)

        backup_path, metadata = manager.create_backup()

        # Both files should be backed up
        assert (backup_path / "00-installer.yaml").exists()
        assert (backup_path / "01-custom.yaml").exists()
        assert len(metadata.source_configs) == 2

    def test_backup_no_files_raises_error(self, tmp_path: Path) -> None:
        """Test that backup fails if no YAML files found."""
        config_dir = tmp_path / "netplan"
        config_dir.mkdir()

        backup_dir = tmp_path / "backups"
        manager = BackupManager(backup_dir=backup_dir, config_dir=config_dir)

        with pytest.raises(BackupError, match="No netplan YAML files found"):
            manager.create_backup()

    def test_restore_backup(self, tmp_path: Path) -> None:
        """Test restoring from a backup."""
        # Setup: create original config
        config_dir = tmp_path / "netplan"
        config_dir.mkdir()

        original_config = config_dir / "00-config.yaml"
        original_content = """
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
"""
        original_config.write_text(original_content)

        backup_dir = tmp_path / "backups"
        manager = BackupManager(backup_dir=backup_dir, config_dir=config_dir)

        # Create backup
        backup_path, _ = manager.create_backup()

        # Modify original config
        original_config.write_text("""
network:
  version: 2
  ethernets:
    eth0:
      addresses:
        - 192.168.1.10/24
""")

        # Restore from backup
        manager.restore_backup(backup_path, verify=True)

        # Config should be restored to original
        restored_content = original_config.read_text()
        assert "dhcp4: true" in restored_content
        assert "192.168.1.10" not in restored_content

    def test_restore_nonexistent_backup_raises_error(self, tmp_path: Path) -> None:
        """Test that restoring nonexistent backup fails."""
        manager = BackupManager(backup_dir=tmp_path / "backups", config_dir=tmp_path / "netplan")

        with pytest.raises(BackupError, match="not found"):
            manager.restore_backup(tmp_path / "nonexistent")

    def test_verify_backup(self, tmp_path: Path) -> None:
        """Test backup verification."""
        # Setup
        config_dir = tmp_path / "netplan"
        config_dir.mkdir()

        config_file = config_dir / "00-config.yaml"
        config_file.write_text("""
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
""")

        backup_dir = tmp_path / "backups"
        manager = BackupManager(backup_dir=backup_dir, config_dir=config_dir)

        # Create backup
        backup_path, _ = manager.create_backup()

        # Verify should pass
        assert manager.verify_backup(backup_path) is True

        # Corrupt the backup
        config_in_backup = backup_path / "00-config.yaml"
        config_in_backup.write_text("corrupted content")

        # Verify should fail
        assert manager.verify_backup(backup_path) is False

    def test_list_backups(self, tmp_path: Path) -> None:
        """Test listing backups."""
        # Setup
        config_dir = tmp_path / "netplan"
        config_dir.mkdir()

        config_file = config_dir / "00-config.yaml"
        config_file.write_text("""
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
""")

        backup_dir = tmp_path / "backups"
        manager = BackupManager(backup_dir=backup_dir, config_dir=config_dir)

        # Create multiple backups
        backup1_path, meta1 = manager.create_backup(description="First backup")

        # Sleep briefly to ensure different timestamps
        import time
        time.sleep(0.1)

        backup2_path, meta2 = manager.create_backup(description="Second backup")

        # List backups
        backups = manager.list_backups()

        assert len(backups) == 2

        # Find the backups by ID
        backup_dict = {meta.backup_id: meta for _, meta in backups}
        assert meta1.backup_id in backup_dict
        assert meta2.backup_id in backup_dict

    def test_cleanup_old_backups(self, tmp_path: Path) -> None:
        """Test cleanup of old backups."""
        # Setup
        config_dir = tmp_path / "netplan"
        config_dir.mkdir()

        config_file = config_dir / "00-config.yaml"
        config_file.write_text("""
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
""")

        backup_dir = tmp_path / "backups"
        manager = BackupManager(backup_dir=backup_dir, config_dir=config_dir)

        # Create many backups
        for i in range(25):
            manager.create_backup(description=f"Backup {i}")

        # Should have 25 backups
        assert len(manager.list_backups()) == 25

        # Cleanup keeping only 20
        removed = manager.cleanup_old_backups(keep_count=20, keep_days=0)

        # Should remove 5
        assert removed == 5
        assert len(manager.list_backups()) == 20

    def test_backup_preserves_file_content(self, tmp_path: Path) -> None:
        """Test that backup preserves exact file content."""
        config_dir = tmp_path / "netplan"
        config_dir.mkdir()

        original_content = """# Comment at top
network:
  version: 2
  renderer: networkd
  ethernets:
    enp1s0:
      addresses:
        - 192.168.1.10/24
      gateway4: 192.168.1.1
      nameservers:
        addresses:
          - 8.8.8.8
          - 1.1.1.1
"""
        config_file = config_dir / "00-config.yaml"
        config_file.write_text(original_content)

        backup_dir = tmp_path / "backups"
        manager = BackupManager(backup_dir=backup_dir, config_dir=config_dir)

        # Create backup
        backup_path, _ = manager.create_backup()

        # Read backed up content
        backed_up_content = (backup_path / "00-config.yaml").read_text()

        # Should be identical
        assert backed_up_content == original_content

    def test_restore_removes_extra_files(self, tmp_path: Path) -> None:
        """Test that restore removes YAML files not in the backup."""
        # Setup: create original config with one file
        config_dir = tmp_path / "netplan"
        config_dir.mkdir()

        original_config = config_dir / "00-installer.yaml"
        original_config.write_text("""
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
""")

        backup_dir = tmp_path / "backups"
        manager = BackupManager(backup_dir=backup_dir, config_dir=config_dir)

        # Create backup (has only 00-installer.yaml)
        backup_path, _ = manager.create_backup(description="Original config")

        # Add a new file that wasn't in the backup
        new_config = config_dir / "01-new-config.yaml"
        new_config.write_text("""
network:
  version: 2
  ethernets:
    eth1:
      addresses:
        - 192.168.1.10/24
""")

        # Verify both files exist
        assert original_config.exists()
        assert new_config.exists()
        assert len(list(config_dir.glob("*.yaml"))) == 2

        # Restore from backup
        manager.restore_backup(backup_path, verify=True)

        # Only the original file should exist
        assert original_config.exists()
        assert not new_config.exists()
        assert len(list(config_dir.glob("*.yaml"))) == 1

        # Content should match original
        assert "dhcp4: true" in original_config.read_text()
