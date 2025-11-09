"""User confirmation handling."""

import sys
from datetime import timedelta


class ConfirmationHandler:
    """Handles user confirmation prompts."""

    @staticmethod
    def prompt_for_confirmation(
        state_id: str,
        timeout: timedelta,
        config_path: str,
    ) -> None:
        """Display confirmation prompt with instructions.

        Args:
            state_id: State ID to confirm
            timeout: Time remaining until auto-rollback
            config_path: Path to config that was applied
        """
        minutes = int(timeout.total_seconds() / 60)
        seconds = int(timeout.total_seconds() % 60)

        print("\n" + "=" * 70)
        print("  NETWORK CONFIGURATION APPLIED - CONFIRMATION REQUIRED")
        print("=" * 70)
        print(f"\nConfiguration: {config_path}")
        print(f"State ID: {state_id}")
        print(f"\nYou have {minutes}m {seconds}s to confirm the configuration.")
        print("\nIf you can still access this system, the configuration is working.")
        print("\nTo CONFIRM the changes (make them permanent):")
        print("  ace-network-manager confirm")
        print("\nTo ROLLBACK the changes:")
        print("  ace-network-manager rollback")
        print("\nIf you do nothing, the configuration will AUTOMATICALLY ROLLBACK")
        print(f"in {minutes}m {seconds}s to prevent network lockout.")
        print("\n" + "=" * 70 + "\n")
        sys.stdout.flush()

    @staticmethod
    def show_countdown(time_remaining: timedelta) -> None:
        """Show countdown to auto-rollback.

        Args:
            time_remaining: Time until rollback
        """
        minutes = int(time_remaining.total_seconds() / 60)
        seconds = int(time_remaining.total_seconds() % 60)

        msg = f"\rTime until auto-rollback: {minutes:02d}:{seconds:02d}"
        print(msg, end="", flush=True)

    @staticmethod
    def show_confirmed() -> None:
        """Show confirmation success message."""
        print("\n" + "=" * 70)
        print("  ✓ CONFIGURATION CONFIRMED")
        print("=" * 70)
        print("\nThe network configuration has been permanently applied.")
        print("The automatic rollback timer has been cancelled.")
        print("\n" + "=" * 70 + "\n")

    @staticmethod
    def show_rolled_back(reason: str = "timeout") -> None:
        """Show rollback message.

        Args:
            reason: Reason for rollback
        """
        print("\n" + "=" * 70)
        print("  ⚠ CONFIGURATION ROLLED BACK")
        print("=" * 70)
        print(f"\nReason: {reason}")
        print("\nThe network configuration has been restored to the previous state.")
        print("Your network connectivity should be restored.")
        print("\n" + "=" * 70 + "\n")
