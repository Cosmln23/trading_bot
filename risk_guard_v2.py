#!/usr/bin/env python3
"""
Risk Guard v2 - Command Center for Coordinated Risk Management
Monitors wallet balance every 60 seconds and writes commands for other processes.
No direct API order execution to avoid race conditions.
"""

import os
import time
import math
import json
from typing import Dict, Any
from datetime import datetime

try:
    from pybit.unified_trading import HTTP
except ImportError:
    print("ERROR: pybit not installed. Run: pip install pybit")
    exit(1)


def _safe_float(x) -> float:
    """Convert to float safely, return NaN if invalid."""
    try:
        return float(x)
    except Exception:
        return float('nan')


class RiskCommandCenter:
    """
    Centralized risk monitoring and command coordination.
    Monitors IM utilization and writes commands for other processes to execute.
    """

    def __init__(
        self,
        client: HTTP,
        warn_at: float = 0.60,        # 60%
        derisk_at: float = 0.70,      # 70%
        cap_at: float = 0.80,         # 80%
        halt_at: float = 0.90,        # 90%
        target_after_derisk: float = 0.60,
        target_after_emergency: float = 0.58,
        poll_seconds: int = 60,       # Check every 60 seconds (efficiency)
        command_file: str = "risk_commands.json",
        log_func=print,
        dry_run: bool = False
    ):
        self.client = client
        self.warn_at = warn_at
        self.derisk_at = derisk_at
        self.cap_at = cap_at
        self.halt_at = halt_at
        self.target_after_derisk = target_after_derisk
        self.target_after_emergency = target_after_emergency
        self.poll_seconds = poll_seconds
        self.command_file = command_file
        self.log = log_func
        self.dry_run = dry_run

        # State tracking
        self.last_utilization = 0.0
        self.last_mode = "NORMAL"
        self.consecutive_errors = 0

        self.log(f"[RISK-CENTER] Initialized - Command Center Mode")
        self.log(f"[RISK-CENTER] Polling every {poll_seconds} seconds")
        self.log(f"[RISK-CENTER] Thresholds: {warn_at:.0%}/{derisk_at:.0%}/{cap_at:.0%}/{halt_at:.0%}")
        self.log(f"[RISK-CENTER] Commands file: {command_file}")

    def get_wallet_utilization(self) -> tuple:
        """
        Fetch ONLY wallet balance for IM utilization - no positions API call.
        Returns: (utilization, total_equity, used_im, free_equity)
        """
        try:
            response = self.client.get_wallet_balance(accountType="UNIFIED")

            if response.get("retCode") != 0:
                raise RuntimeError(f"Bybit API error: {response.get('retMsg')}")

            wallet_list = response.get("result", {}).get("list", [])
            if not wallet_list:
                raise RuntimeError("No wallet data found in UNIFIED account")

            wallet = wallet_list[0]

            total_equity = _safe_float(wallet.get("totalEquity", 0))
            used_im = _safe_float(wallet.get("totalInitialMargin", 0))
            free_equity = _safe_float(wallet.get("totalAvailableBalance", 0))

            if not (math.isfinite(total_equity) and total_equity > 0):
                raise RuntimeError(f"Invalid totalEquity: {total_equity}")

            utilization = max(0.0, min(1.0, used_im / total_equity if math.isfinite(used_im) else 0.0))

            self.consecutive_errors = 0  # Reset error counter on success
            return utilization, total_equity, used_im, free_equity

        except Exception as e:
            self.consecutive_errors += 1
            self.log(f"[ERROR] Wallet balance failed (attempt {self.consecutive_errors}): {e}")
            raise

    def determine_risk_mode(self, utilization: float) -> str:
        """Determine current risk mode based on utilization."""
        if utilization >= self.halt_at:
            return "HALT"
        elif utilization >= self.cap_at:
            return "EMERGENCY"
        elif utilization >= self.derisk_at:
            return "DERISK"
        elif utilization >= self.warn_at:
            return "ALERT"
        else:
            return "NORMAL"

    def create_command(self, mode: str, utilization: float, total_equity: float, used_im: float) -> Dict[str, Any]:
        """Create command object based on risk mode."""
        base_command = {
            "timestamp": datetime.now().isoformat(),
            "mode": mode,
            "utilization": utilization,
            "total_equity": total_equity,
            "used_im": used_im,
            "dry_run": self.dry_run
        }

        if mode == "HALT":
            # Hard stop: close everything
            base_command.update({
                "allow_new_entries": False,
                "cancel_all_orders": True,
                "close_all_positions": True,
                "close_fraction": 1.0,
                "priority": "IMMEDIATE",
                "message": "≥90% IM - EMERGENCY SHUTDOWN"
            })

        elif mode == "EMERGENCY":
            # 80-90%: Aggressive deleverage
            target_im = self.target_after_emergency * total_equity
            excess_im = used_im - target_im
            base_command.update({
                "allow_new_entries": False,
                "cancel_all_orders": True,
                "close_positions": True,
                "close_fraction": 0.33,  # Aggressive chunks
                "target_utilization": self.target_after_emergency,
                "excess_im_to_reduce": excess_im,
                "priority": "HIGH",
                "message": f"80-90% IM - Emergency deleverage to {self.target_after_emergency:.0%}"
            })

        elif mode == "DERISK":
            # 70-80%: Active deleverage
            target_im = self.target_after_derisk * total_equity
            excess_im = used_im - target_im
            base_command.update({
                "allow_new_entries": False,
                "cancel_all_orders": True,
                "close_positions": True,
                "close_fraction": 0.25,  # Moderate chunks
                "target_utilization": self.target_after_derisk,
                "excess_im_to_reduce": excess_im,
                "priority": "MEDIUM",
                "message": f"70-80% IM - Active deleverage to {self.target_after_derisk:.0%}"
            })

        elif mode == "ALERT":
            # 60-70%: Warning only
            base_command.update({
                "allow_new_entries": True,  # Still allow but warn
                "cancel_all_orders": False,
                "close_positions": False,
                "priority": "LOW",
                "message": "60-70% IM - Recommend reducing order sizes"
            })

        else:  # NORMAL
            # <60%: All clear
            base_command.update({
                "allow_new_entries": True,
                "cancel_all_orders": False,
                "close_positions": False,
                "priority": "NONE",
                "message": "Normal trading - All systems operational"
            })

        return base_command

    def write_command_file(self, command: Dict[str, Any]):
        """Write command to file for other processes to read."""
        try:
            # Write to temporary file first, then atomic rename
            temp_file = f"{self.command_file}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(command, f, indent=2)

            # Atomic rename to ensure consistency
            os.rename(temp_file, self.command_file)

            self.log(f"[COMMAND] Mode: {command['mode']} | "
                    f"Entries: {'✓' if command['allow_new_entries'] else '✗'} | "
                    f"Priority: {command['priority']}")

            if command.get('close_positions'):
                self.log(f"[COMMAND] Close positions: {command['close_fraction']:.0%} chunks | "
                        f"Target: {command.get('target_utilization', 0):.0%}")

        except Exception as e:
            self.log(f"[ERROR] Failed to write command file: {e}")

    def monitor_and_command(self):
        """Main monitoring cycle - analyze and issue commands."""
        try:
            # Get current utilization (wallet balance only)
            utilization, total_equity, used_im, free_equity = self.get_wallet_utilization()
            self.last_utilization = utilization

            # Determine risk mode
            current_mode = self.determine_risk_mode(utilization)

            # Log status
            self.log(f"[MONITOR] Total: {total_equity:.2f} | "
                    f"Used IM: {used_im:.2f} | "
                    f"Free: {free_equity:.2f} | "
                    f"Utilization: {utilization:.1%} | "
                    f"Mode: {current_mode}")

            # Create and write command
            command = self.create_command(current_mode, utilization, total_equity, used_im)
            self.write_command_file(command)

            # Log mode changes
            if current_mode != self.last_mode:
                self.log(f"[MODE-CHANGE] {self.last_mode} → {current_mode}: {command['message']}")
                self.last_mode = current_mode

            return True

        except Exception as e:
            self.log(f"[ERROR] Monitor cycle failed: {e}")

            # Emergency fallback command on repeated failures
            if self.consecutive_errors >= 3:
                self.log(f"[EMERGENCY] {self.consecutive_errors} consecutive errors - issuing HALT command")
                emergency_command = {
                    "timestamp": datetime.now().isoformat(),
                    "mode": "HALT",
                    "allow_new_entries": False,
                    "cancel_all_orders": True,
                    "close_all_positions": True,
                    "priority": "IMMEDIATE",
                    "message": f"API failures - emergency halt after {self.consecutive_errors} errors",
                    "error": str(e)
                }
                self.write_command_file(emergency_command)

            return False

    def run_forever(self):
        """Main loop - monitor and issue commands continuously."""
        self.log(f"[START] Risk Command Center online")

        # Initial command to establish baseline
        try:
            self.monitor_and_command()
        except Exception as e:
            self.log(f"[INIT] Initial command failed: {e}")

        while True:
            try:
                self.monitor_and_command()

            except KeyboardInterrupt:
                self.log("[STOP] Risk Command Center stopped by user")
                break
            except Exception as e:
                self.log(f"[ERROR] Unexpected error: {e}")

            # Sleep for polling interval
            time.sleep(self.poll_seconds)

        # Write final shutdown command
        shutdown_command = {
            "timestamp": datetime.now().isoformat(),
            "mode": "SHUTDOWN",
            "allow_new_entries": False,
            "message": "Risk Command Center offline"
        }
        self.write_command_file(shutdown_command)


def main():
    """Entry point when run as standalone script."""
    # Get API credentials from environment
    api_key = os.environ.get("BYBIT_API_KEY")
    api_secret = os.environ.get("BYBIT_API_SECRET")
    testnet = os.environ.get("BYBIT_TESTNET", "false").lower() in ("1", "true", "yes", "y")

    if not api_key or not api_secret:
        print("ERROR: Set BYBIT_API_KEY and BYBIT_API_SECRET environment variables")
        return

    # Initialize Bybit client
    client = HTTP(
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet
    )

    # Initialize and run risk command center
    command_center = RiskCommandCenter(
        client=client,
        poll_seconds=60,  # Check every minute for efficiency
        dry_run=False,    # Set to True for testing
        log_func=print
    )

    try:
        command_center.run_forever()
    except KeyboardInterrupt:
        print("\nRisk Command Center stopped")


if __name__ == "__main__":
    main()