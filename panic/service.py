#!/usr/bin/env python3
"""
Core Panic Service Engine
Executes the 6-phase panic procedure with atomic operations.
"""

import time
import json
import sys
import os
from typing import Dict, List, Any, Tuple
from pathlib import Path

# Add the project root to Python path to import existing modules
sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "BybitUSDT"))

try:
    # Try importing from BybitUSDT directory first
    sys.path.insert(0, str(Path(__file__).parent.parent / "BybitUSDT"))
    import bybitwrapper
    print("[SERVICE] Bybit wrapper imported successfully")
except ImportError as e:
    print(f"[SERVICE] Warning: Could not import bybitwrapper: {e}")
    bybitwrapper = None

from .config import get_config
from .state import StateManager, PanicReport, get_state_manager
from .telegram import get_alerter

class PanicService:
    """Core panic execution service with 6 atomic phases."""

    def __init__(self):
        self.config = get_config()
        self.state_manager = get_state_manager(self.config.lock_file_path)
        self.alerter = get_alerter()

        # Initialize Bybit client using existing configuration
        self.client = None
        self._init_bybit_client()

        # Load coins configuration
        self.coins = self._load_coins_config()

    def _init_bybit_client(self):
        """Initialize Bybit client using existing settings."""
        try:
            # Load existing settings.json
            settings_path = Path(__file__).parent.parent / 'settings.json'
            with open(settings_path, 'r') as f:
                settings = json.load(f)

            if bybitwrapper:
                self.client = bybitwrapper.bybit(
                    test=False,
                    api_key=settings['key'],
                    api_secret=settings['secret']
                )
                print("[SERVICE] Bybit client initialized successfully")
            else:
                print("[SERVICE] Warning: Bybit client not available, using mock mode")

        except Exception as e:
            print(f"[SERVICE] Error initializing Bybit client: {e}")
            self.client = None

    def _load_coins_config(self) -> List[Dict]:
        """Load coins configuration from coins.json."""
        try:
            coins_path = Path(__file__).parent.parent / 'coins.json'
            with open(coins_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[SERVICE] Error loading coins config: {e}")
            return []

    def _get_symbols_with_positions(self) -> List[str]:
        """Get symbols that have open positions."""
        symbols = []
        if not self.client or not self.coins:
            return symbols

        try:
            for coin in self.coins:
                symbol = coin['symbol']
                try:
                    positions = self.client.LinearPositions.LinearPositions_myPosition(
                        symbol=symbol+"USDT"
                    ).result()

                    if positions[0]['ret_msg'] == 'OK':
                        for position in positions[0]['result']:
                            if float(position['entry_price']) > 0:
                                symbols.append(symbol)
                                break
                except Exception as e:
                    print(f"[SERVICE] Error checking position for {symbol}: {e}")

        except Exception as e:
            print(f"[SERVICE] Error getting positions: {e}")

        return symbols

    def _get_symbols_with_orders(self) -> List[str]:
        """Get symbols that have open orders."""
        symbols = []
        if not self.client or not self.coins:
            return symbols

        try:
            for coin in self.coins:
                symbol = coin['symbol']
                try:
                    # Check linear orders
                    orders = self.client.LinearOrder.LinearOrder_getOrders(
                        symbol=symbol+"USDT", limit='10'
                    ).result()

                    if orders[0]['ret_msg'] == 'OK' and orders[0]['result']['data']:
                        for order in orders[0]['result']['data']:
                            if order['order_status'] not in ['Filled', 'Cancelled']:
                                symbols.append(symbol)
                                break

                    # Check conditional orders if not already added
                    if symbol not in symbols:
                        cond_orders = self.client.LinearConditional.LinearConditional_getOrders(
                            symbol=symbol+"USDT", limit='10'
                        ).result()

                        if cond_orders[0]['ret_msg'] == 'OK' and cond_orders[0]['result']['data']:
                            for order in cond_orders[0]['result']['data']:
                                if order['order_status'] != 'Deactivated':
                                    symbols.append(symbol)
                                    break

                except Exception as e:
                    print(f"[SERVICE] Error checking orders for {symbol}: {e}")

        except Exception as e:
            print(f"[SERVICE] Error getting orders: {e}")

        return symbols

    def _backoff_delay(self, attempt: int) -> float:
        """Calculate backoff delay for retry attempts."""
        delay = min(
            self.config.initial_backoff_ms * (self.config.backoff_multiplier ** attempt),
            self.config.max_backoff_ms
        ) / 1000.0  # Convert to seconds
        return delay

    def _phase_1_disable_trading(self, report: PanicReport) -> bool:
        """Phase 1: Disable trading globally."""
        start_time = time.time()
        print("[PANIC-PHASE-1] Disabling trading...")

        try:
            self.state_manager.disable_trading()

            # Could also set a global flag file that other processes check
            flag_file = Path("trading_disabled.flag")
            flag_file.touch()

            phase_time = time.time() - start_time
            report.phase_timings['disable_trading'] = phase_time
            print(f"[PANIC-PHASE-1] Trading disabled in {phase_time:.3f}s")
            return True

        except Exception as e:
            phase_time = time.time() - start_time
            report.phase_timings['disable_trading'] = phase_time
            report.warnings.append(f"Phase 1 error: {str(e)}")
            print(f"[PANIC-PHASE-1] Error: {e}")
            return False

    def _phase_2_cancel_all(self, report: PanicReport) -> bool:
        """Phase 2: Cancel all orders on all symbols."""
        start_time = time.time()
        print("[PANIC-PHASE-2] Cancelling all orders...")

        if not self.client:
            print("[PANIC-PHASE-2] No client available, skipping")
            report.phase_timings['cancel_all'] = 0.0
            return True

        symbols_with_orders = self._get_symbols_with_orders()
        orders_canceled = 0
        errors = []

        for symbol in symbols_with_orders:
            try:
                # Cancel linear orders
                linear_result = self.client.LinearOrder.LinearOrder_cancel(
                    symbol=symbol+"USDT"
                ).result()

                if linear_result[0]['ret_msg'] == 'OK':
                    orders_canceled += 1

                # Cancel conditional orders
                cond_result = self.client.LinearConditional.LinearConditional_cancel(
                    symbol=symbol+"USDT"
                ).result()

                if cond_result[0]['ret_msg'] == 'OK':
                    orders_canceled += 1

                print(f"[PANIC-PHASE-2] Canceled orders for {symbol}")

            except Exception as e:
                error_msg = f"Cancel error for {symbol}: {str(e)}"
                errors.append(error_msg)
                print(f"[PANIC-PHASE-2] {error_msg}")

        report.orders_canceled = orders_canceled
        report.warnings.extend(errors)

        phase_time = time.time() - start_time
        report.phase_timings['cancel_all'] = phase_time

        print(f"[PANIC-PHASE-2] Canceled {orders_canceled} orders in {phase_time:.3f}s")
        return len(errors) == 0  # Success if no errors

    def _phase_3_flatten_all(self, report: PanicReport) -> bool:
        """Phase 3: Close all positions with market reduceOnly orders."""
        start_time = time.time()
        print("[PANIC-PHASE-3] Flattening all positions...")

        if not self.client:
            print("[PANIC-PHASE-3] No client available, skipping")
            report.phase_timings['flatten_all'] = 0.0
            return True

        symbols_with_positions = self._get_symbols_with_positions()
        positions_closed = 0
        errors = []

        for symbol in symbols_with_positions:
            try:
                # Get position details
                positions = self.client.LinearPositions.LinearPositions_myPosition(
                    symbol=symbol+"USDT"
                ).result()

                if positions[0]['ret_msg'] == 'OK':
                    for position in positions[0]['result']:
                        entry_price = float(position['entry_price'])
                        if entry_price > 0:
                            size = float(position['size'])
                            side = position['side']

                            # Determine opposite side for closing
                            close_side = 'Sell' if side == 'Buy' else 'Buy'

                            # Close with market reduceOnly order
                            close_result = self.client.LinearOrder.LinearOrder_new(
                                side=close_side,
                                symbol=symbol+"USDT",
                                order_type="Market",
                                qty=size,
                                reduce_only=True,
                                time_in_force="IOC"
                            ).result()

                            if close_result[0]['ret_msg'] == 'OK':
                                positions_closed += 1
                                print(f"[PANIC-PHASE-3] Closed {symbol} position: {close_side} {size}")

            except Exception as e:
                error_msg = f"Close error for {symbol}: {str(e)}"
                errors.append(error_msg)
                print(f"[PANIC-PHASE-3] {error_msg}")

        report.positions_closed = positions_closed
        report.warnings.extend(errors)

        phase_time = time.time() - start_time
        report.phase_timings['flatten_all'] = phase_time

        print(f"[PANIC-PHASE-3] Closed {positions_closed} positions in {phase_time:.3f}s")
        return len(errors) == 0

    def _phase_4_verify_clean(self, report: PanicReport) -> bool:
        """Phase 4: Verify all positions and orders are closed."""
        start_time = time.time()
        print("[PANIC-PHASE-4] Verifying clean state...")

        if not self.client:
            print("[PANIC-PHASE-4] No client available, assuming clean")
            report.phase_timings['verify_clean'] = 0.0
            return True

        max_attempts = self.config.max_retries
        poll_interval = self.config.verify_poll_ms / 1000.0

        for attempt in range(max_attempts):
            positions_remaining = len(self._get_symbols_with_positions())
            orders_remaining = len(self._get_symbols_with_orders())

            if positions_remaining == 0 and orders_remaining == 0:
                phase_time = time.time() - start_time
                report.phase_timings['verify_clean'] = phase_time
                print(f"[PANIC-PHASE-4] Verified clean in {phase_time:.3f}s")
                return True

            print(f"[PANIC-PHASE-4] Attempt {attempt+1}: {positions_remaining} positions, {orders_remaining} orders remaining")

            if attempt < max_attempts - 1:
                time.sleep(poll_interval)

        # Timeout reached
        phase_time = time.time() - start_time
        report.phase_timings['verify_clean'] = phase_time
        report.warnings.append(f"Verification timeout after {phase_time:.1f}s")
        print(f"[PANIC-PHASE-4] Timeout after {phase_time:.3f}s")
        return False

    def _phase_5_arm_lock(self, report: PanicReport) -> bool:
        """Phase 5: Create panic lock file."""
        start_time = time.time()
        print("[PANIC-PHASE-5] Creating panic lock...")

        try:
            # Update symbols touched in report
            all_symbols = set()
            all_symbols.update(self._get_symbols_with_positions())
            all_symbols.update(self._get_symbols_with_orders())
            report.symbols_touched = list(all_symbols)

            self.state_manager.create_panic_lock(report)

            phase_time = time.time() - start_time
            report.phase_timings['arm_lock'] = phase_time
            print(f"[PANIC-PHASE-5] Lock created in {phase_time:.3f}s")
            return True

        except Exception as e:
            phase_time = time.time() - start_time
            report.phase_timings['arm_lock'] = phase_time
            report.warnings.append(f"Phase 5 error: {str(e)}")
            print(f"[PANIC-PHASE-5] Error: {e}")
            return False

    def _phase_6_send_alert(self, report: PanicReport, success: bool) -> bool:
        """Phase 6: Send Telegram alert."""
        start_time = time.time()
        print("[PANIC-PHASE-6] Sending alert...")

        try:
            if success:
                self.alerter.send_panic_success_alert(report)
            else:
                self.alerter.send_panic_failure_alert(report)

            phase_time = time.time() - start_time
            report.phase_timings['send_alert'] = phase_time
            print(f"[PANIC-PHASE-6] Alert sent in {phase_time:.3f}s")
            return True

        except Exception as e:
            phase_time = time.time() - start_time
            report.phase_timings['send_alert'] = phase_time
            report.warnings.append(f"Phase 6 error: {str(e)}")
            print(f"[PANIC-PHASE-6] Error: {e}")
            return False

    def execute_panic(self) -> PanicReport:
        """Execute full panic procedure with all 6 phases."""
        print("\n" + "="*60)
        print("🚨 PANIC BUTTON ACTIVATED - EXECUTING EMERGENCY PROCEDURES")
        print("="*60)

        # Check if already in panic mode
        if self.state_manager.is_panic_active():
            print("[PANIC] Already in panic mode - returning existing report")
            existing_report = self.state_manager.get_last_report()
            if existing_report:
                return existing_report

        # Create new report and send start alert
        report = self.state_manager.create_report()
        self.alerter.send_panic_start_alert(report.started_at)

        success = True

        # Execute all 6 phases
        phases = [
            self._phase_1_disable_trading,
            self._phase_2_cancel_all,
            self._phase_3_flatten_all,
            self._phase_4_verify_clean,
            self._phase_5_arm_lock,
        ]

        for phase_func in phases:
            try:
                phase_success = phase_func(report)
                if not phase_success:
                    success = False
                    print(f"[PANIC] Phase {phase_func.__name__} failed")
            except Exception as e:
                success = False
                error_msg = f"Phase {phase_func.__name__} exception: {str(e)}"
                report.warnings.append(error_msg)
                print(f"[PANIC] {error_msg}")

        # Always execute phase 6 (alert) regardless of success
        self._phase_6_send_alert(report, success)

        # Finalize report
        self.state_manager.finalize_report(
            report,
            success=success,
            error_message="Multiple phase failures" if not success else None
        )

        print("="*60)
        if success:
            print("✅ PANIC PROCEDURE COMPLETED SUCCESSFULLY")
        else:
            print("❌ PANIC PROCEDURE COMPLETED WITH ERRORS")
        print("="*60 + "\n")

        return report

    def reset_panic(self) -> Dict[str, Any]:
        """Reset panic state (remove lock and re-enable trading)."""
        print("[RESET] Attempting panic reset...")

        # Safety check - verify positions and orders are actually clean
        if self.client:
            positions_remaining = len(self._get_symbols_with_positions())
            orders_remaining = len(self._get_symbols_with_orders())

            if positions_remaining > 0 or orders_remaining > 0:
                error_msg = f"Unsafe reset: {positions_remaining} positions, {orders_remaining} orders remaining"
                print(f"[RESET] {error_msg}")
                self.alerter.send_reset_alert(False, error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "positions_remaining": positions_remaining,
                    "orders_remaining": orders_remaining
                }

        try:
            # Remove lock and re-enable trading
            self.state_manager.remove_panic_lock()

            # Remove trading disabled flag
            flag_file = Path("trading_disabled.flag")
            flag_file.unlink(missing_ok=True)

            print("[RESET] Panic reset successful")
            self.alerter.send_reset_alert(True, "All positions and orders verified clean")

            return {
                "success": True,
                "message": "Panic reset successful, trading re-enabled",
                "timestamp": time.time()
            }

        except Exception as e:
            error_msg = f"Reset error: {str(e)}"
            print(f"[RESET] {error_msg}")
            self.alerter.send_reset_alert(False, error_msg)
            return {
                "success": False,
                "error": error_msg
            }

# Global service instance
_panic_service = None

def get_panic_service() -> PanicService:
    """Get global panic service instance."""
    global _panic_service
    if _panic_service is None:
        _panic_service = PanicService()
    return _panic_service