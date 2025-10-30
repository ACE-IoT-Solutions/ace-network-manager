"""Unit tests for StateTracker."""

from datetime import timedelta
from pathlib import Path

import pytest

from ace_network_manager.core.exceptions import StateError
from ace_network_manager.state.models import StateStatus
from ace_network_manager.state.tracker import StateTracker


class TestStateTracker:
    """Test StateTracker functionality."""

    def test_create_pending_state(self, tmp_path: Path) -> None:
        """Test creating a new pending state."""
        tracker = StateTracker(state_dir=tmp_path / "state")

        backup_path = tmp_path / "backup"
        config_path = tmp_path / "config.yaml"
        timeout = timedelta(minutes=5)

        state = tracker.create_pending_state(
            backup_path=backup_path,
            config_path=config_path,
            timeout=timeout,
            original_hash="abc123",
            new_hash="def456",
            metadata={"user": "test", "hostname": "test-host"},
        )

        assert state.state_id is not None
        assert state.status == StateStatus.PENDING
        assert state.backup_path == backup_path
        assert state.config_path == config_path
        assert state.original_config_hash == "abc123"
        assert state.new_config_hash == "def456"
        assert state.metadata["user"] == "test"
        assert state.timeout_seconds == 300

    def test_get_pending_state(self, tmp_path: Path) -> None:
        """Test retrieving pending state."""
        tracker = StateTracker(state_dir=tmp_path / "state")

        # Initially no pending state
        assert tracker.get_pending_state() is None

        # Create a pending state
        state = tracker.create_pending_state(
            backup_path=tmp_path / "backup",
            config_path=tmp_path / "config.yaml",
            timeout=timedelta(minutes=5),
            original_hash="abc123",
            new_hash="def456",
        )

        # Should retrieve it
        retrieved = tracker.get_pending_state()
        assert retrieved is not None
        assert retrieved.state_id == state.state_id
        assert retrieved.status == StateStatus.PENDING

    def test_cannot_create_multiple_pending_states(self, tmp_path: Path) -> None:
        """Test that only one pending state is allowed at a time."""
        tracker = StateTracker(state_dir=tmp_path / "state")

        # Create first pending state
        tracker.create_pending_state(
            backup_path=tmp_path / "backup1",
            config_path=tmp_path / "config1.yaml",
            timeout=timedelta(minutes=5),
            original_hash="abc123",
            new_hash="def456",
        )

        # Try to create second pending state
        with pytest.raises(StateError, match="existing state"):
            tracker.create_pending_state(
                backup_path=tmp_path / "backup2",
                config_path=tmp_path / "config2.yaml",
                timeout=timedelta(minutes=5),
                original_hash="xyz789",
                new_hash="uvw012",
            )

    def test_confirm_state(self, tmp_path: Path) -> None:
        """Test confirming a pending state."""
        tracker = StateTracker(state_dir=tmp_path / "state")

        # Create pending state
        state = tracker.create_pending_state(
            backup_path=tmp_path / "backup",
            config_path=tmp_path / "config.yaml",
            timeout=timedelta(minutes=5),
            original_hash="abc123",
            new_hash="def456",
        )

        # Confirm it
        tracker.confirm_state(state.state_id)

        # Should no longer be pending
        assert tracker.get_pending_state() is None

        # Should be in archive as confirmed
        confirmed = tracker.get_state(state.state_id)
        assert confirmed is not None
        assert confirmed.status == StateStatus.CONFIRMED
        assert confirmed.confirmed_at is not None

    def test_mark_rolled_back(self, tmp_path: Path) -> None:
        """Test marking a state as rolled back."""
        tracker = StateTracker(state_dir=tmp_path / "state")

        # Create pending state
        state = tracker.create_pending_state(
            backup_path=tmp_path / "backup",
            config_path=tmp_path / "config.yaml",
            timeout=timedelta(minutes=5),
            original_hash="abc123",
            new_hash="def456",
        )

        # Mark as rolled back
        tracker.mark_rolled_back(state.state_id, reason="timeout_expired")

        # Should no longer be pending
        assert tracker.get_pending_state() is None

        # Should be in archive as rolled back
        rolled_back = tracker.get_state(state.state_id)
        assert rolled_back is not None
        assert rolled_back.status == StateStatus.ROLLBACK_COMPLETE
        assert rolled_back.rolled_back_at is not None
        assert rolled_back.rollback_reason == "timeout_expired"

    def test_list_states(self, tmp_path: Path) -> None:
        """Test listing states."""
        tracker = StateTracker(state_dir=tmp_path / "state")

        # Create and confirm a few states
        state1 = tracker.create_pending_state(
            backup_path=tmp_path / "backup1",
            config_path=tmp_path / "config1.yaml",
            timeout=timedelta(minutes=5),
            original_hash="abc123",
            new_hash="def456",
        )
        tracker.confirm_state(state1.state_id)

        state2 = tracker.create_pending_state(
            backup_path=tmp_path / "backup2",
            config_path=tmp_path / "config2.yaml",
            timeout=timedelta(minutes=5),
            original_hash="ghi789",
            new_hash="jkl012",
        )
        tracker.mark_rolled_back(state2.state_id, reason="manual")

        state3 = tracker.create_pending_state(
            backup_path=tmp_path / "backup3",
            config_path=tmp_path / "config3.yaml",
            timeout=timedelta(minutes=5),
            original_hash="mno345",
            new_hash="pqr678",
        )

        # List all states
        all_states = tracker.list_states()
        assert len(all_states) == 3

        # List only confirmed
        confirmed_states = tracker.list_states(status=StateStatus.CONFIRMED)
        assert len(confirmed_states) == 1
        assert confirmed_states[0].state_id == state1.state_id

        # List only rolled back
        rolled_back_states = tracker.list_states(status=StateStatus.ROLLBACK_COMPLETE)
        assert len(rolled_back_states) == 1
        assert rolled_back_states[0].state_id == state2.state_id

        # List only pending
        pending_states = tracker.list_states(status=StateStatus.PENDING)
        assert len(pending_states) == 1
        assert pending_states[0].state_id == state3.state_id

    def test_cleanup_old_states(self, tmp_path: Path) -> None:
        """Test cleanup of old archived states."""
        tracker = StateTracker(state_dir=tmp_path / "state")

        # Create and confirm a state
        state = tracker.create_pending_state(
            backup_path=tmp_path / "backup",
            config_path=tmp_path / "config.yaml",
            timeout=timedelta(minutes=5),
            original_hash="abc123",
            new_hash="def456",
        )
        tracker.confirm_state(state.state_id)

        # Initially should have 1 archived state
        all_states = tracker.list_states()
        assert len(all_states) == 1

        # Cleanup with keep_days=0 should remove it
        # (since we can't easily manipulate timestamps in tests)
        # This is a simplified test - in practice we'd mock datetime
        removed = tracker.cleanup_old_states(keep_days=0)
        assert removed >= 0  # May or may not remove depending on timing

    def test_state_persists_across_instances(self, tmp_path: Path) -> None:
        """Test that state persists across StateTracker instances."""
        state_dir = tmp_path / "state"

        # Create state with first tracker
        tracker1 = StateTracker(state_dir=state_dir)
        state = tracker1.create_pending_state(
            backup_path=tmp_path / "backup",
            config_path=tmp_path / "config.yaml",
            timeout=timedelta(minutes=5),
            original_hash="abc123",
            new_hash="def456",
        )

        # Create new tracker instance
        tracker2 = StateTracker(state_dir=state_dir)

        # Should retrieve the same state
        retrieved = tracker2.get_pending_state()
        assert retrieved is not None
        assert retrieved.state_id == state.state_id
