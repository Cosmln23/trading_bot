#!/usr/bin/env python3
"""
Breakeven Manager - Move SL to breakeven at 0.5R
Protects profits by moving stop loss to entry + fees at 50% of target
"""
import os
from typing import Dict, Optional

# Configuration
TAKER_FEE = float(os.getenv("TAKER_FEE", "0.0006"))  # 0.06% Bybit taker fee
SLIP_PCT = float(os.getenv("SLIP_PCT", "0.0005"))    # 0.05% slippage buffer

def r_multiple(entry: float, stop: float, current: float, side: str) -> float:
    """
    Calculate R multiple (how many R's we're in profit/loss)

    Args:
        entry: Entry price
        stop: Stop loss price
        current: Current market price
        side: 'Buy' or 'Sell'

    Returns:
        R multiple (positive = profitable move, negative = losing move)
    """
    if entry == 0 or stop == 0:
        return 0.0

    # Calculate R (risk per share)
    r_value = abs(entry - stop)
    if r_value == 0:
        return 0.0

    # Calculate unrealized move
    if side.lower() in ['buy', 'long']:
        move = current - entry  # Long: profit when price goes up
    else:
        move = entry - current  # Short: profit when price goes down

    return move / r_value

def calculate_breakeven_price(entry: float, side: str) -> float:
    """
    Calculate breakeven price including fees and slippage

    Args:
        entry: Entry price
        side: 'Buy' or 'Sell'

    Returns:
        Breakeven price (entry + fees + slippage buffer)
    """
    fee_offset = entry * (TAKER_FEE * 2 + SLIP_PCT)  # Entry + Exit fees + slippage

    if side.lower() in ['buy', 'long']:
        return entry + fee_offset  # Long: breakeven above entry
    else:
        return entry - fee_offset  # Short: breakeven below entry

def should_move_to_breakeven(entry: float, stop: float, current: float, side: str, already_moved: bool = False) -> tuple[bool, float]:
    """
    Check if we should move SL to breakeven

    Args:
        entry: Entry price
        stop: Current stop loss price
        current: Current market price
        side: 'Buy' or 'Sell'
        already_moved: Whether SL was already moved to breakeven

    Returns:
        (should_move: bool, new_stop_price: float)
    """
    if already_moved:
        return False, stop

    # Calculate current R multiple
    r_mult = r_multiple(entry, stop, current, side)

    # Move to breakeven at 0.5R
    if r_mult >= 0.5:
        new_stop = calculate_breakeven_price(entry, side)
        return True, new_stop

    return False, stop

def format_breakeven_log(symbol: str, side: str, entry: float, old_stop: float, new_stop: float, r_mult: float) -> str:
    """Format log message for breakeven move"""
    return (f"[BREAKEVEN] {symbol} {side.upper()}: "
            f"Entry={entry:.4f} | SL: {old_stop:.4f} → {new_stop:.4f} | "
            f"R={r_mult:.2f} (≥0.5R)")

class BreakevenTracker:
    """Track breakeven status for multiple positions"""

    def __init__(self):
        self.moved_positions: Dict[str, bool] = {}

    def is_moved(self, position_id: str) -> bool:
        """Check if position already moved to breakeven"""
        return self.moved_positions.get(position_id, False)

    def mark_moved(self, position_id: str):
        """Mark position as moved to breakeven"""
        self.moved_positions[position_id] = True
        print(f"[BREAKEVEN-TRACKER] {position_id} marked as moved to breakeven")

    def reset_position(self, position_id: str):
        """Reset position (when closed)"""
        if position_id in self.moved_positions:
            del self.moved_positions[position_id]

    def check_and_move(self, position_id: str, entry: float, stop: float, current: float, side: str) -> tuple[bool, float]:
        """
        Check if position should move to breakeven and track it

        Returns:
            (should_move: bool, new_stop_price: float)
        """
        already_moved = self.is_moved(position_id)
        should_move, new_stop = should_move_to_breakeven(entry, stop, current, side, already_moved)

        if should_move:
            self.mark_moved(position_id)

        return should_move, new_stop

# Global tracker instance
breakeven_tracker = BreakevenTracker()

if __name__ == "__main__":
    # Test breakeven logic
    print("Breakeven Manager Test")

    # Test long position
    entry = 100.0
    stop = 97.0  # 3% stop loss

    prices = [100.5, 101.0, 101.5, 102.0, 102.5]  # Price movement up

    print(f"\nLong position test: Entry={entry}, SL={stop}")

    for current in prices:
        r_mult = r_multiple(entry, stop, current, 'Buy')
        should_move, new_stop = should_move_to_breakeven(entry, stop, current, 'Buy')

        print(f"Price: {current:6.2f} | R: {r_mult:5.2f} | Move: {should_move} | New SL: {new_stop:6.2f}")

        if should_move:
            print(format_breakeven_log("TESTUSDT", "Buy", entry, stop, new_stop, r_mult))
            break