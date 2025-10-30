"""State tracking models with comprehensive type hints."""

from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StateStatus(str, Enum):
    """Possible states for a configuration change."""

    IDLE = "idle"
    BACKUP_IN_PROGRESS = "backup_in_progress"
    PENDING = "pending"
    APPLYING = "applying"
    APPLIED = "applied"
    CONFIRMING = "confirming"
    CONFIRMED = "confirmed"
    ROLLING_BACK = "rolling_back"
    ROLLBACK_COMPLETE = "rollback_complete"
    FAILED = "failed"


class ConfigurationState(BaseModel):
    """Complete state information for a configuration change.

    Persisted as JSON in semaphore files for cross-reboot durability.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "state_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "pending",
                "created_at": "2024-10-30T14:30:22.123456",
                "timeout_at": "2024-10-30T14:35:22.123456",
                "backup_path": "/var/lib/ace-network-manager/backups/2024-10-30-143022",
                "config_path": "/etc/netplan/00-installer-config.yaml",
                "original_config_hash": "abc123",
                "new_config_hash": "def456",
            }
        }
    )

    state_id: str = Field(..., description="UUID4 identifier for this state")
    status: StateStatus = Field(..., description="Current status of the change")
    created_at: datetime = Field(
        default_factory=datetime.now, description="When the state was created"
    )
    timeout_at: datetime = Field(..., description="When automatic rollback will trigger")
    timeout_seconds: int = Field(..., ge=0, description="Timeout duration in seconds")

    backup_path: Path = Field(..., description="Path to backup directory")
    config_path: Path = Field(..., description="Path to config file that was applied")

    original_config_hash: str = Field(..., description="SHA256 hash of original config")
    new_config_hash: str = Field(..., description="SHA256 hash of new config")

    confirmed_at: datetime | None = Field(None, description="When the config was confirmed")
    rolled_back_at: datetime | None = Field(None, description="When rollback occurred")
    rollback_reason: str | None = Field(
        None, description="Reason for rollback (timeout, manual, error, etc.)"
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata (user, hostname, etc.)"
    )

    @field_validator("timeout_at", mode="before")
    @classmethod
    def parse_timeout(cls, v: Any) -> datetime:
        """Parse timeout from various formats."""
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            return datetime.fromisoformat(v)
        msg = f"Invalid timeout format: {type(v)}"
        raise ValueError(msg)

    @field_validator("backup_path", "config_path", mode="before")
    @classmethod
    def parse_path(cls, v: Any) -> Path:
        """Parse paths from strings."""
        if isinstance(v, Path):
            return v
        return Path(v)

    def is_expired(self) -> bool:
        """Check if this state has passed its timeout."""
        return datetime.now() > self.timeout_at

    def time_remaining(self) -> timedelta:
        """Get time remaining until timeout."""
        remaining = self.timeout_at - datetime.now()
        return remaining if remaining.total_seconds() > 0 else timedelta(0)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConfigurationState":
        """Create from dictionary (for loading from JSON)."""
        # Convert status string to enum
        if "status" in data and isinstance(data["status"], str):
            data["status"] = StateStatus(data["status"])
        return cls.model_validate(data)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (for saving to JSON)."""
        data = self.model_dump(mode="json")
        # Convert datetime objects to ISO format strings
        data["created_at"] = self.created_at.isoformat()
        data["timeout_at"] = self.timeout_at.isoformat()
        if self.confirmed_at:
            data["confirmed_at"] = self.confirmed_at.isoformat()
        if self.rolled_back_at:
            data["rolled_back_at"] = self.rolled_back_at.isoformat()
        # Convert Paths to strings
        data["backup_path"] = str(self.backup_path)
        data["config_path"] = str(self.config_path)
        # Convert enum to value
        data["status"] = self.status.value
        return data


class BackupMetadata(BaseModel):
    """Metadata for a backup directory."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "backup_id": "550e8400-e29b-41d4-a716-446655440000",
                "created_at": "2024-10-30T14:30:22.123456",
                "description": "Before changing enp1s0 to static IP",
                "source_configs": ["00-installer-config.yaml"],
                "checksums": {"00-installer-config.yaml": "abc123..."},
            }
        }
    )

    backup_id: str = Field(..., description="UUID for this backup")
    created_at: datetime = Field(default_factory=datetime.now, description="Backup creation time")
    description: str | None = Field(None, description="Human-readable description")

    source_configs: list[str] = Field(
        default_factory=list, description="List of config filenames backed up"
    )
    checksums: dict[str, str] = Field(
        default_factory=dict, description="SHA256 checksums for each file"
    )

    system_info: dict[str, str] = Field(
        default_factory=dict,
        description="System information (hostname, OS version, netplan version)",
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BackupMetadata":
        """Create from dictionary."""
        return cls.model_validate(data)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = self.model_dump(mode="json")
        data["created_at"] = self.created_at.isoformat()
        return data


class ApplyResult(BaseModel):
    """Result of applying a configuration."""

    model_config = ConfigDict(frozen=True)  # Immutable result

    success: bool = Field(..., description="Whether the apply succeeded")
    backup_path: Path = Field(..., description="Path to backup directory")
    state_id: str = Field(..., description="State ID for tracking")
    message: str = Field(..., description="Human-readable message")
    timeout_seconds: int = Field(..., ge=0, description="Timeout in seconds")
    errors: list[str] = Field(default_factory=list, description="Any validation errors")

    @field_validator("backup_path", mode="before")
    @classmethod
    def parse_path(cls, v: Any) -> Path:
        """Parse path from string."""
        if isinstance(v, Path):
            return v
        return Path(v)
