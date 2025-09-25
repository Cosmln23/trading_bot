#!/usr/bin/env python3
"""
Risk Guard - Bybit V5 UNIFIED Account Protection
Monitors Initial Margin utilization and applies risk controls at:
- 60-70%: Alert mode
- 70-80%: Derisk active (cancel orders, close partial)
- 80-90%: Emergency mode (aggressive closing)
- ≥90%: Hard stop (close all, halt trading)
"""

import os
import time
import math
import json
from typing import List, Dict, Optional
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


class RiskGuard:
    """
    Standalone risk management for Bybit V5 UNIFIED accounts.
    Runs as separate process monitoring IM utilization.
    """

    def __init__(
        self,
        client: HTTP,
        warn_at: float = 0.60,        # 60%
        derisk_at: float = 0.70,      # 70%
        cap_at: float = 0.80,         # 80%
        halt_at: float = 0.90,        # 90%
        target_after_derisk: float = 0.60,    # Target after 70-80% derisk
        target_after_emergency: float = 0.58, # Target after 80-90% emergency
        poll_seconds: int = 5,        # Check every 5 seconds
        log_func=print,
        dry_run: bool = False,
        flag_file: str = "risk_flag.json"
    ):
        self.client = client
        self.warn_at = warn_at
        self.derisk_at = derisk_at
        self.cap_at = cap_at
        self.halt_at = halt_at
        self.target_after_derisk = target_after_derisk
        self.target_after_emergency = target_after_emergency
        self.poll_seconds = poll_seconds
        self.log = log_func
        self.dry_run = dry_run
        self.flag_file = flag_file

        # State tracking
        self.allow_new_entries = True
        self.trading_enabled = True
        self.last_utilization = 0.0
        self.last_action_time = 0

        self.log(f"[RISK-GUARD] Initialized - thresholds: {warn_at:.0%}/{derisk_at:.0%}/{cap_at:.0%}/{halt_at:.0%}")

    def get_im_utilization(self) -> tuple:
        """
        Fetch IM utilization from Bybit V5 UNIFIED account.
        Returns: (utilization, total_equity, used_im, free_equity)
        """
        try:
            response = self.client.get_wallet_balance(accountType="UNIFIED")

            if response.get("retCode") != 0:
                raise RuntimeError(f"Bybit API error: {response.get('retMsg')}")

            wallet_list = response.get("result", {}).get("list", [])
            if not wallet_list:
                raise RuntimeError("No wallet data found in UNIFIED account")

            wallet = wallet_list[0]  # First (and usually only) unified wallet

            total_equity = _safe_float(wallet.get("totalEquity", 0))
            used_im = _safe_float(wallet.get("totalInitialMargin", 0))
            free_equity = _safe_float(wallet.get("totalAvailableBalance", 0))

            if not (math.isfinite(total_equity) and total_equity > 0):
                raise RuntimeError(f"Invalid totalEquity: {total_equity}")

            utilization = max(0.0, min(1.0, used_im / total_equity if math.isfinite(used_im) else 0.0))

            return utilization, total_equity, used_im, free_equity

        except Exception as e:
            self.log(f"[ERROR] Failed to get wallet balance: {e}")
            raise

    def get_all_positions(self) -> List[Dict]:
        """
        Fetch all open positions from Bybit V5 linear (USDT futures).
        Returns normalized position data.
        """
        try:
            response = self.client.get_positions(category="linear")

            if response.get("retCode") != 0:
                raise RuntimeError(f"Positions API error: {response.get('retMsg')}")

            positions_raw = response.get("result", {}).get("list", [])
            positions = []

            for pos in positions_raw:
                size = _safe_float(pos.get("size", 0))
                if not (math.isfinite(size) and size > 0):
                    continue  # Skip empty positions

                symbol = pos.get("symbol", "")
                side = pos.get("side", "").lower()
                leverage = _safe_float(pos.get("leverage", 1))
                entry_price = _safe_float(pos.get("avgPrice", 0))
                position_im = _safe_float(pos.get("positionIM", 0))
                unrealized_pnl = _safe_float(pos.get("unrealisedPnl", 0))

                positions.append({
                    "symbol": symbol,
                    "side": "long" if side == "buy" else "short",
                    "contracts": size,
                    "leverage": leverage if math.isfinite(leverage) and leverage > 0 else 1.0,
                    "entry_price": entry_price,
                    "position_im": position_im if math.isfinite(position_im) and position_im > 0 else 0.0,
                    "unrealized_pnl": unrealized_pnl,
                    "is_losing": math.isfinite(unrealized_pnl) and unrealized_pnl < 0
                })

            return positions

        except Exception as e:
            self.log(f"[ERROR] Failed to get positions: {e}")
            raise

    def cancel_all_orders_for_symbols(self, symbols: List[str]):
        """Cancel all orders for given symbols to prevent new exposure."""
        for symbol in symbols:
            try:
                if self.dry_run:
                    self.log(f"[DRY] Would cancel all orders for {symbol}")
                    continue

                response = self.client.cancel_all_orders(category="linear", symbol=symbol)

                if response.get("retCode") != 0:
                    self.log(f"[WARN] Cancel orders {symbol} failed: {response.get('retMsg')}")
                else:
                    self.log(f"[CANCEL] All orders cancelled for {symbol}")

            except Exception as e:
                self.log(f"[WARN] Exception cancelling orders for {symbol}: {e}")

    def close_position_fraction(self, position: Dict, fraction: float) -> bool:
        """
        Close a fraction (0.0 to 1.0) of a position using reduceOnly market order.
        Returns True if successful.
        """
        if not (0 < fraction <= 1.0):
            return False

        close_qty = position["contracts"] * fraction
        if close_qty <= 0:
            return False

        # Opposite side to close
        close_side = "Sell" if position["side"] == "long" else "Buy"

        try:
            if self.dry_run:
                self.log(f"[DRY] Would close {fraction:.0%} of {position['symbol']}: "
                        f"{close_qty:g} contracts via {close_side} Market (reduceOnly)")
                return True

            response = self.client.place_order(
                category="linear",
                symbol=position["symbol"],
                side=close_side,
                orderType="Market",
                qty=str(close_qty),
                reduceOnly=True,
                timeInForce="IOC"  # Immediate or Cancel
            )

            if response.get("retCode") != 0:
                self.log(f"[WARN] Close order failed for {position['symbol']}: {response.get('retMsg')}")
                return False

            self.log(f"[CLOSE] {position['symbol']} {close_side} {close_qty:g} "
                    f"(lev:{position['leverage']:.1f}, "
                    f"{'LOSS' if position['is_losing'] else 'PROFIT'})")
            return True

        except Exception as e:
            self.log(f"[ERROR] Exception closing {position['symbol']}: {e}")
            return False

    def shed_margin_to_target(self, positions: List[Dict], total_equity: float,
                             used_im: float, target_utilization: float, chunk_fraction: float = 0.25):
        """
        Close positions to reduce IM utilization to target level.
        Prioritizes: losing positions, high leverage, high IM.
        """
        target_im = target_utilization * total_equity
        excess_im = used_im - target_im

        if excess_im <= 0:
            self.log(f"[DERISK] Already at target utilization {target_utilization:.0%}")
            return

        # Filter positions with meaningful IM and sort by priority
        valid_positions = [p for p in positions if p["position_im"] > 0]
        if not valid_positions:
            self.log("[DERISK] No positions with IM to close")
            return

        # Sort: losing first, then high leverage, then high IM
        valid_positions.sort(key=lambda p: (
            not p["is_losing"],      # Losing positions first
            -p["leverage"],          # Higher leverage first
            -p["position_im"]        # Higher IM first
        ))

        self.log(f"[DERISK] Need to reduce IM by ~{excess_im:.2f} USDT "
                f"(target: {target_utilization:.0%})")

        remaining_excess = excess_im

        for pos in valid_positions:
            if remaining_excess <= 0:
                break

            # Calculate fraction to close (limit by chunk_fraction)
            max_im_reduction = pos["position_im"]
            needed_fraction = min(chunk_fraction,
                                max(0.05, remaining_excess / max(1e-9, max_im_reduction)))

            if self.close_position_fraction(pos, needed_fraction):
                # Estimate IM freed (proportional to fraction closed)
                estimated_im_freed = max_im_reduction * needed_fraction
                remaining_excess -= estimated_im_freed

                self.log(f"[DERISK] {pos['symbol']} freed ~{estimated_im_freed:.2f} USDT IM, "
                        f"remaining excess: ~{max(0, remaining_excess):.2f}")

    def write_flag_file(self):
        """Write current state to flag file for other processes to read."""
        try:
            flag_data = {
                "allow_new_entries": self.allow_new_entries,
                "trading_enabled": self.trading_enabled,
                "last_utilization": self.last_utilization,
                "timestamp": datetime.now().isoformat(),
                "thresholds": {
                    "warn": self.warn_at,
                    "derisk": self.derisk_at,
                    "cap": self.cap_at,
                    "halt": self.halt_at
                }
            }

            with open(self.flag_file, 'w') as f:
                json.dump(flag_data, f, indent=2)

        except Exception as e:
            self.log(f"[WARN] Failed to write flag file: {e}")

    def enforce_risk_controls(self):
        """Main risk control logic - called every poll cycle."""
        try:
            # Get current utilization
            utilization, total_equity, used_im, free_equity = self.get_im_utilization()
            self.last_utilization = utilization

            self.log(f"[UTIL] Total: {total_equity:.2f} | Used IM: {used_im:.2f} | "
                    f"Free: {free_equity:.2f} | Utilization: {utilization:.1%}")

            # Get all positions
            positions = self.get_all_positions()
            symbols = sorted({pos["symbol"] for pos in positions})

            current_time = time.time()

            # Apply risk controls based on utilization thresholds
            if utilization >= self.halt_at:
                # HARD STOP: ≥90%
                self.log(f"[HARD-STOP] Utilization {utilization:.1%} ≥ {self.halt_at:.0%} - "
                        "CLOSING ALL POSITIONS AND HALTING TRADING")

                # Cancel all orders
                self.cancel_all_orders_for_symbols(symbols)

                # Close all positions 100%
                for pos in positions:
                    self.close_position_fraction(pos, 1.0)

                self.trading_enabled = False
                self.allow_new_entries = False
                self.last_action_time = current_time

            elif utilization >= self.cap_at:
                # EMERGENCY: 80-90%
                self.log(f"[EMERGENCY] Utilization {utilization:.1%} in 80-90% range - "
                        "AGGRESSIVE DELEVERAGE TO 58%")

                # Cancel all orders to prevent new exposure
                self.cancel_all_orders_for_symbols(symbols)

                # Aggressive position closing
                self.shed_margin_to_target(positions, total_equity, used_im,
                                         self.target_after_emergency, chunk_fraction=0.33)

                self.allow_new_entries = False
                self.last_action_time = current_time

            elif utilization >= self.derisk_at:
                # DERISK: 70-80%
                self.log(f"[DERISK] Utilization {utilization:.1%} in 70-80% range - "
                        "REDUCING EXPOSURE TO 60%")

                # Cancel all orders
                self.cancel_all_orders_for_symbols(symbols)

                # Moderate position closing
                self.shed_margin_to_target(positions, total_equity, used_im,
                                         self.target_after_derisk, chunk_fraction=0.25)

                self.allow_new_entries = False
                self.last_action_time = current_time

            elif utilization >= self.warn_at:
                # WARNING: 60-70%
                self.log(f"[ALERT] Utilization {utilization:.1%} in 60-70% range - "
                        "RECOMMEND REDUCING NEW ORDER SIZES")

                # Still allow entries but recommend caution
                self.allow_new_entries = True

            else:
                # NORMAL: <60%
                if not self.allow_new_entries:
                    self.log(f"[NORMAL] Utilization {utilization:.1%} < 60% - "
                            "RESUMING NORMAL TRADING")

                self.trading_enabled = True
                self.allow_new_entries = True

            # Write state to flag file
            self.write_flag_file()

        except Exception as e:
            self.log(f"[ERROR] Risk control enforcement failed: {e}")

    def run_forever(self):
        """Main loop - monitor and enforce risk controls continuously."""
        self.log(f"[START] Risk Guard monitoring every {self.poll_seconds} seconds...")
        self.log(f"[START] Dry run: {self.dry_run}")

        while True:
            try:
                self.enforce_risk_controls()
            except KeyboardInterrupt:
                self.log("[STOP] Risk Guard stopped by user")
                break
            except Exception as e:
                self.log(f"[ERROR] Unexpected error: {e}")

            time.sleep(self.poll_seconds)


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

    # Initialize and run risk guard
    guard = RiskGuard(
        client=client,
        poll_seconds=5,
        dry_run=False,  # Set to True for testing
        log_func=print
    )

    try:
        guard.run_forever()
    except KeyboardInterrupt:
        print("\nRisk Guard stopped")


if __name__ == "__main__":
    main()