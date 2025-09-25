#!/usr/bin/env python3
"""
Local State Management for Panic Button
Handles lock files and trading state persistence.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict

@dataclass
class PanicReport:
    """Data structure for panic execution report."""
    started_at: str
    ended_at: Optional[str] = None
    phase_timings: Dict[str, float] = None
    symbols_touched: list = None
    orders_canceled: int = 0
    positions_closed: int = 0
    warnings: list = None
    locked: bool = False
    total_duration_sec: float = 0.0
    success: bool = False
    error_message: Optional[str] = None

    def __post_init__(self):
        if self.phase_timings is None:
            self.phase_timings = {}
        if self.symbols_touched is None:
            self.symbols_touched = []
        if self.warnings is None:
            self.warnings = []

class StateManager:
    """Manages panic button state and lock files."""

    def __init__(self, lock_file_path: str = "state/panic.lock"):
        self.lock_file_path = Path(lock_file_path)
        self.trading_enabled = True
        self.panic_tripped = False

        # Ensure state directory exists
        self.lock_file_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing state
        self._load_state()

    def _load_state(self):
        """Load existing state from lock file if it exists."""
        if self.lock_file_path.exists():
            try:
                with open(self.lock_file_path, 'r') as f:
                    data = json.load(f)
                    self.panic_tripped = True
                    self.trading_enabled = False
                    print(f"[STATE] Loaded existing panic lock from {self.lock_file_path}")
            except Exception as e:
                print(f"[STATE] Warning: Could not load lock file: {e}")
                # Remove corrupted lock file
                self.lock_file_path.unlink(missing_ok=True)

    def is_panic_active(self) -> bool:
        """Check if panic mode is currently active."""
        return self.panic_tripped

    def is_trading_enabled(self) -> bool:
        """Check if trading is currently enabled."""
        return self.trading_enabled and not self.panic_tripped

    def disable_trading(self):
        """Disable trading (Phase 1 of panic)."""
        self.trading_enabled = False
        print("[STATE] Trading disabled")

    def enable_trading(self):
        """Enable trading (only after successful reset)."""
        self.trading_enabled = True
        print("[STATE] Trading enabled")

    def create_panic_lock(self, report: PanicReport):
        """Create panic lock file with report data (Phase 5)."""
        try:
            lock_data = {
                "timestamp": datetime.now().isoformat(),
                "panic_tripped": True,
                "trading_enabled": False,
                "last_report": asdict(report)
            }

            # Write to temporary file first, then atomic rename
            temp_file = self.lock_file_path.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(lock_data, f, indent=2)

            # Atomic rename
            temp_file.rename(self.lock_file_path)

            self.panic_tripped = True
            self.trading_enabled = False

            print(f"[STATE] Panic lock created: {self.lock_file_path}")

        except Exception as e:
            print(f"[STATE] Error creating panic lock: {e}")
            raise

    def remove_panic_lock(self):
        """Remove panic lock file (reset operation)."""
        try:
            if self.lock_file_path.exists():
                self.lock_file_path.unlink()
                print(f"[STATE] Panic lock removed: {self.lock_file_path}")

            self.panic_tripped = False
            self.trading_enabled = True

        except Exception as e:
            print(f"[STATE] Error removing panic lock: {e}")
            raise

    def get_last_report(self) -> Optional[PanicReport]:
        """Get the last panic report from lock file."""
        if not self.lock_file_path.exists():
            return None

        try:
            with open(self.lock_file_path, 'r') as f:
                data = json.load(f)
                report_data = data.get('last_report', {})

                # Convert back to PanicReport object
                return PanicReport(**report_data)

        except Exception as e:
            print(f"[STATE] Error reading last report: {e}")
            return None

    def get_status(self) -> Dict[str, Any]:
        """Get current system status."""
        last_report = self.get_last_report()

        status = {
            "trading_enabled": self.trading_enabled,
            "panic_tripped": self.panic_tripped,
            "lock_file_exists": self.lock_file_path.exists(),
            "uptime_sec": time.time() - os.path.getctime(__file__) if os.path.exists(__file__) else 0
        }

        if last_report:
            status["last_panic"] = {
                "timestamp": last_report.started_at,
                "success": last_report.success,
                "duration_sec": last_report.total_duration_sec,
                "symbols_touched": len(last_report.symbols_touched),
                "orders_canceled": last_report.orders_canceled,
                "positions_closed": last_report.positions_closed
            }

        return status

    def create_report(self) -> PanicReport:
        """Create a new panic report."""
        return PanicReport(
            started_at=datetime.now().isoformat()
        )

    def finalize_report(self, report: PanicReport, success: bool = True, error_message: str = None):
        """Finalize panic report with end time and success status."""
        end_time = datetime.now()
        report.ended_at = end_time.isoformat()
        report.success = success
        report.locked = success  # Only lock if successful
        report.error_message = error_message

        # Calculate total duration
        if report.started_at:
            start_time = datetime.fromisoformat(report.started_at.replace('Z', '+00:00'))
            report.total_duration_sec = (end_time - start_time).total_seconds()

        return report

# Global state manager instance
_state_manager = None

def get_state_manager(lock_file_path: str = "state/panic.lock") -> StateManager:
    """Get global state manager instance."""
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager(lock_file_path)
    return _state_manager