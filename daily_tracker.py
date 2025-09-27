#!/usr/bin/env python3
"""
Daily PnL Tracker - Simple & Robust
Tracks realized profit/loss and stops trading at daily target (3%)
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

# Configuration
DAILY_TARGET_PCT = float(os.getenv("DAILY_TARGET_PCT", "3"))  # 3%
EQUITY_USDT = float(os.getenv("EQUITY_USDT", "120"))
STATE_PATH = Path("state/daily_pnl.json")

def _today_key():
    """Get today's key in UTC"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def load_state():
    """Load daily state from JSON file"""
    if not STATE_PATH.exists():
        return {}
    try:
        with open(STATE_PATH, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_state(state):
    """Save state to JSON file"""
    STATE_PATH.parent.mkdir(exist_ok=True)
    with open(STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)

def add_realized_pnl(delta_usdt: float):
    """Add realized PnL (positive = profit, negative = loss)"""
    state = load_state()
    key = _today_key()

    # Initialize today's data if not exists
    day_data = state.get(key, {
        "realized": 0.0,
        "stopped": False,
        "loss_streak": 0,
        "trades": 0
    })

    # Update realized PnL
    day_data["realized"] = round(day_data["realized"] + delta_usdt, 6)
    day_data["trades"] += 1

    # Update loss streak
    if delta_usdt < 0:
        day_data["loss_streak"] = day_data.get("loss_streak", 0) + 1
    else:
        day_data["loss_streak"] = 0

    state[key] = day_data
    save_state(state)

    print(f"[DAILY-PNL] Trade #{day_data['trades']}: {delta_usdt:+.2f} USDT | Total: {day_data['realized']:+.2f} USDT | Loss streak: {day_data['loss_streak']}")

    return day_data

def reached_daily_target():
    """Check if daily target reached"""
    state = load_state()
    key = _today_key()
    day_data = state.get(key, {"realized": 0.0, "stopped": False})

    target_usdt = EQUITY_USDT * DAILY_TARGET_PCT / 100.0

    # Check if target reached
    if day_data["realized"] >= target_usdt and not day_data["stopped"]:
        day_data["stopped"] = True
        state[key] = day_data
        save_state(state)
        print(f"[DAILY-TARGET] ✅ TARGET REACHED! Realized: {day_data['realized']:.2f} USDT >= Target: {target_usdt:.2f} USDT")
        print(f"[DAILY-TARGET] 🛑 STOPPING TRADING FOR TODAY")

    return day_data.get("stopped", False), day_data["realized"], target_usdt

def get_loss_streak():
    """Get current loss streak"""
    state = load_state()
    key = _today_key()
    return state.get(key, {}).get("loss_streak", 0)

def reset_if_new_day():
    """Initialize today's data if needed"""
    state = load_state()
    key = _today_key()

    if key not in state:
        state[key] = {
            "realized": 0.0,
            "stopped": False,
            "loss_streak": 0,
            "trades": 0
        }
        save_state(state)
        print(f"[DAILY-PNL] 🌅 New trading day started: {key}")

def get_daily_stats():
    """Get today's trading statistics"""
    state = load_state()
    key = _today_key()
    day_data = state.get(key, {"realized": 0.0, "stopped": False, "trades": 0, "loss_streak": 0})
    target_usdt = EQUITY_USDT * DAILY_TARGET_PCT / 100.0

    return {
        "date": key,
        "realized_pnl": day_data["realized"],
        "target_pnl": target_usdt,
        "progress_pct": (day_data["realized"] / target_usdt * 100) if target_usdt > 0 else 0,
        "trades": day_data["trades"],
        "loss_streak": day_data["loss_streak"],
        "stopped": day_data["stopped"]
    }

if __name__ == "__main__":
    # Test the tracker
    print("Daily PnL Tracker Test")
    reset_if_new_day()

    stats = get_daily_stats()
    print(f"Today's stats: {stats}")

    stopped, realized, target = reached_daily_target()
    print(f"Trading stopped: {stopped}, Realized: {realized:.2f}, Target: {target:.2f}")