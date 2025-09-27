#!/usr/bin/env python3
"""
Portfolio Momentum Manager - Trend Following System
Buys assets with strong daily momentum and holds with trailing stops
"""
import json
import time
import os
import aiohttp
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Set
import bybitwrapper

# Configuration
SETTINGS_PATH = Path("../settings.json")
STATE_PATH = Path("portfolio_state.json")
TELEGRAM_CONFIG_PATH = Path("../config/panic.yaml")

# Telegram configuration
TELEGRAM_BOT_TOKEN = None
TELEGRAM_CHAT_ID = None

def load_telegram_config():
    """Load Telegram configuration from panic.yaml"""
    global TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    try:
        import yaml
        with open(TELEGRAM_CONFIG_PATH, 'r') as f:
            config = yaml.safe_load(f)

        TELEGRAM_BOT_TOKEN = config['alert']['telegram']['bot_token']
        TELEGRAM_CHAT_ID = config['alert']['telegram']['chat_id']
        print(f"[TELEGRAM] Config loaded successfully")
        return True
    except Exception as e:
        print(f"[TELEGRAM] Config load error: {e}")
        return False

async def send_telegram(message: str):
    """Send message to Telegram asynchronously"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[TELEGRAM] Not configured, skipping: {message}")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    print(f"[TELEGRAM] ✅ Sent: {message[:50]}...")
                else:
                    print(f"[TELEGRAM] ❌ Error {response.status}")
    except Exception as e:
        print(f"[TELEGRAM] Exception: {e}")

def send_telegram_sync(message: str):
    """Synchronous wrapper for send_telegram"""
    try:
        # Create new event loop if none exists
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Run the async function
        loop.run_until_complete(send_telegram(message))
    except Exception as e:
        print(f"[TELEGRAM] Sync wrapper error: {e}")

def load_config():
    """Load configuration from settings.json"""
    with open(SETTINGS_PATH, 'r') as f:
        settings = json.load(f)
    return settings["portfolio"], settings

def load_allowlist() -> Set[str]:
    """Load allowed symbols from allowlist file"""
    cfg, _ = load_config()
    allowlist_path = Path("..") / cfg["entry"]["allowlist_file"]
    try:
        with open(allowlist_path, 'r') as f:
            data = json.load(f)
            # Extract symbols from allowlist
            if isinstance(data, list):
                return set(data)
            elif isinstance(data, dict) and "symbols" in data:
                return set(data["symbols"])
            else:
                print(f"[ALLOWLIST] Unknown format in {allowlist_path}")
                return set()
    except Exception as e:
        print(f"[ALLOWLIST] Error loading {allowlist_path}: {e}")
        return set()

def load_state() -> Dict:
    """Load portfolio state from JSON file"""
    if not STATE_PATH.exists():
        return {}
    try:
        with open(STATE_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[STATE] Error loading state: {e}")
        return {}

def save_state(state: Dict):
    """Save state to JSON file"""
    try:
        with open(STATE_PATH, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[STATE] Error saving state: {e}")

def daily_change_pct(client, symbol: str) -> float:
    """Calculate daily change percentage for symbol"""
    try:
        # Get 2 daily candles to compare
        kline = client._session.get_kline(
            category="linear",
            symbol=f"{symbol}USDT",
            interval="D",
            limit=2
        )

        if kline.get('retCode') == 0:
            candles = kline.get('result', {}).get('list', [])
            if len(candles) >= 2:
                # candles[0] = today, candles[1] = yesterday
                current_close = float(candles[0][4])  # close price today
                previous_close = float(candles[1][4])  # close price yesterday

                if previous_close > 0:
                    change_pct = ((current_close - previous_close) / previous_close) * 100
                    return change_pct

        print(f"[DAILY%] {symbol}: Unable to get daily change")
        return 0.0

    except Exception as e:
        print(f"[DAILY%] {symbol}: Error calculating daily change: {e}")
        return 0.0

def last_price(client, symbol: str) -> float:
    """Get current market price for symbol"""
    try:
        ticker = client._session.get_tickers(
            category="linear",
            symbol=f"{symbol}USDT"
        )

        if ticker.get('retCode') == 0:
            result = ticker.get('result', {}).get('list', [])
            if result:
                return float(result[0]['lastPrice'])

        print(f"[PRICE] {symbol}: Unable to get price")
        return 0.0

    except Exception as e:
        print(f"[PRICE] {symbol}: Error getting price: {e}")
        return 0.0

def liq_notional_recent(symbol: str) -> float:
    """
    Estimate recent liquidation notional value
    For now, returns a placeholder - would need liquidation feed integration
    """
    # TODO: Integrate with liquidation feed to get real data
    return 150.0  # Placeholder value above threshold

def can_buy(client, cfg: Dict, symbol: str, current_positions: int, allowlist: Set[str]) -> tuple[bool, str]:
    """Check if we can buy a symbol based on entry criteria"""

    if symbol not in allowlist:
        return False, "not in allowlist"

    # Check position limits
    if current_positions >= cfg["max_open_positions"]:
        return False, "max positions reached"

    # Check daily change percentage
    daily_change = daily_change_pct(client, symbol)
    if daily_change < cfg["entry"]["daily_change_min_pct"]:
        return False, f"daily change {daily_change:.1f}% < {cfg['entry']['daily_change_min_pct']}%"

    # Check liquidation notional
    liq_notional = liq_notional_recent(symbol)
    if liq_notional < cfg["entry"]["liq_notional_min_usd"]:
        return False, f"liq notional ${liq_notional:.0f} < ${cfg['entry']['liq_notional_min_usd']}"

    return True, f"daily:{daily_change:.1f}% liq:${liq_notional:.0f}"

def set_leverage_1x(client, symbol: str):
    """Set leverage to 1x for symbol"""
    try:
        result = client._session.set_leverage(
            category="linear",
            symbol=f"{symbol}USDT",
            buyLeverage="1",
            sellLeverage="1"
        )

        if result.get('retCode') == 0:
            print(f"[LEVERAGE] {symbol}: Set to 1x")
            return True
        else:
            print(f"[LEVERAGE] {symbol}: Error setting leverage: {result.get('retMsg')}")
            return False

    except Exception as e:
        print(f"[LEVERAGE] {symbol}: Exception setting leverage: {e}")
        return False

def place_buy_order(client, cfg: Dict, symbol: str, price: float) -> bool:
    """Place market buy order"""
    try:
        # Calculate quantity
        qty = cfg["buy_amount_usdt"] / price

        # Apply quantity precision fix
        qty_step_01_symbols = ['XRP', 'DOT', 'UNI', 'SOL', 'LINK', 'FIL', 'EOS', 'APEX', 'BARD', 'ALPINE', 'WLD', 'SNX', 'BAND']
        qty_step_1_symbols = ['ADA', 'DOGE', 'MATIC', 'XLM', 'XPL', 'SQD', 'FARTCOIN', 'MYX', 'ORDER', 'SOLV', 'AIA']
        qty_step_10_symbols = ['PENGU', 'LINEA', 'BLESS']
        qty_step_100_symbols = ['1000BONK']

        if symbol in qty_step_01_symbols:
            qty = round(qty, 1)
        elif symbol in qty_step_1_symbols:
            qty = int(round(qty))
        elif symbol in qty_step_10_symbols:
            qty = int(round(qty / 10) * 10)
        elif symbol in qty_step_100_symbols:
            qty = int(round(qty / 100) * 100)
        else:
            qty = round(qty, 3)  # Default precision

        # Set leverage first
        set_leverage_1x(client, symbol)

        # Place order with PM prefix
        order_link_id = f"PM-{symbol}-{int(time.time())}"

        result = client._session.place_order(
            category="linear",
            symbol=f"{symbol}USDT",
            side="Buy",
            orderType="Market",
            qty=str(qty),
            timeInForce="IOC",
            orderLinkId=order_link_id
        )

        if result.get('retCode') == 0:
            print(f"[BUY] {symbol}: ${cfg['buy_amount_usdt']} qty={qty} @ ${price:.4f}")
            return True
        else:
            print(f"[BUY_FAIL] {symbol}: {result.get('retMsg')}")
            return False

    except Exception as e:
        print(f"[BUY_FAIL] {symbol}: Exception: {e}")
        return False

def place_sell_order(client, symbol: str, qty: float, reason: str) -> bool:
    """Place market sell order"""
    try:
        # Apply same quantity precision fix
        qty_step_01_symbols = ['XRP', 'DOT', 'UNI', 'SOL', 'LINK', 'FIL', 'EOS', 'APEX', 'BARD', 'ALPINE', 'WLD', 'SNX', 'BAND']
        qty_step_1_symbols = ['ADA', 'DOGE', 'MATIC', 'XLM', 'XPL', 'SQD', 'FARTCOIN', 'MYX', 'ORDER', 'SOLV', 'AIA']
        qty_step_10_symbols = ['PENGU', 'LINEA', 'BLESS']
        qty_step_100_symbols = ['1000BONK']

        if symbol in qty_step_01_symbols:
            qty = round(qty, 1)
        elif symbol in qty_step_1_symbols:
            qty = int(round(qty))
        elif symbol in qty_step_10_symbols:
            qty = int(round(qty / 10) * 10)
        elif symbol in qty_step_100_symbols:
            qty = int(round(qty / 100) * 100)
        else:
            qty = round(qty, 3)

        order_link_id = f"PM-{symbol}-{int(time.time())}"

        result = client._session.place_order(
            category="linear",
            symbol=f"{symbol}USDT",
            side="Sell",
            orderType="Market",
            qty=str(qty),
            timeInForce="IOC",
            reduceOnly=True,
            orderLinkId=order_link_id
        )

        if result.get('retCode') == 0:
            print(f"[SELL] {symbol}: qty={qty} reason={reason}")
            return True
        else:
            print(f"[SELL_FAIL] {symbol}: {result.get('retMsg')}")
            return False

    except Exception as e:
        print(f"[SELL_FAIL] {symbol}: Exception: {e}")
        return False

def calculate_breakeven_price(entry: float) -> float:
    """Calculate breakeven price including fees"""
    # Bybit taker fee 0.055% + small buffer
    fee_offset = entry * 0.0012  # 0.12% total
    return entry + fee_offset

def should_move_to_breakeven(entry: float, stop: float, current: float, already_moved: bool = False) -> tuple[bool, float]:
    """Check if we should move SL to breakeven at 0.5R"""
    if already_moved:
        return False, stop

    # Calculate R multiple
    r_value = abs(entry - stop)
    if r_value == 0:
        return False, stop

    r_mult = (current - entry) / r_value

    # Move to breakeven at 0.5R
    if r_mult >= 0.5:
        new_stop = calculate_breakeven_price(entry)
        return True, new_stop

    return False, stop

def main():
    """Main portfolio momentum loop"""
    print("🚀 Portfolio Momentum Manager Starting...")

    # Load Telegram configuration
    load_telegram_config()

    # Load configuration
    cfg, settings = load_config()
    if not cfg["enable"]:
        print("❌ Portfolio system disabled in config")
        return

    # Initialize client
    client = bybitwrapper.bybit(
        test=False,
        api_key=settings['key'],
        api_secret=settings['secret']
    )

    # Load initial state and allowlist
    STATE = load_state()
    allowlist = load_allowlist()

    print(f"📊 Config: ${cfg['buy_amount_usdt']}/trade, max {cfg['max_open_positions']} positions")
    print(f"📋 Allowlist: {len(allowlist)} symbols loaded")
    print(f"💾 State: {len(STATE)} positions loaded")
    print()

    # Scheduler mode: run comprehensive scan every 5 minutes
    scan_interval = 300  # 5 minutes
    last_scan_time = 0

    while True:
        try:
            current_time = time.time()

            # Full scan every 5 minutes (scheduler mode for live trading)
            if current_time - last_scan_time >= scan_interval:
                print(f"🔍 [SCHEDULER] [{datetime.now().strftime('%H:%M:%S')}] Full portfolio scan starting...")

                # Entry scanning
                entries_found = 0
                for symbol in allowlist:
                    if symbol not in STATE:
                        can_enter, reason = can_buy(client, cfg, symbol, len(STATE), allowlist)
                        if can_enter:
                            price = last_price(client, symbol)
                            if price > 0:
                                if place_buy_order(client, cfg, symbol, price):
                                    # Add to state
                                    qty = cfg["buy_amount_usdt"] / price
                                    STATE[symbol] = {
                                        "entry": price,
                                        "peak": price,
                                        "size": qty,
                                        "adds_done": 0,
                                        "breakeven_moved": False,
                                        "timestamp": current_time
                                    }
                                    save_state(STATE)
                                    print(f"✅ {symbol}: Added to portfolio @ ${price:.4f}")

                                    # Send Telegram notification
                                    telegram_msg = f"🟢 <b>[PORTFOLIO BUY]</b> {symbol}\n💰 Size: {qty:.3f}\n💵 Price: ${price:.4f}\n📊 Investment: ${cfg['buy_amount_usdt']}"
                                    send_telegram_sync(telegram_msg)

                                    entries_found += 1

                print(f"🔍 [SCHEDULER] Entry scan complete: {entries_found} new positions added")

                # Send scheduler notification
                next_scan = datetime.fromtimestamp(current_time + scan_interval)
                scheduler_msg = f"🔍 <b>[SCHEDULER]</b> Portfolio scan complete\n📊 New positions: {entries_found}\n⏰ Next scan: {next_scan.strftime('%H:%M:%S')} (in {scan_interval//60}min)"
                send_telegram_sync(scheduler_msg)

                last_scan_time = current_time
                print(f"⏰ [SCHEDULER] Next scan in {scan_interval//60} minutes at {next_scan.strftime('%H:%M:%S')}")

            # Quick position management every 30 seconds
            elif int(current_time) % 30 == 0:
                pass  # Skip frequent management to avoid conflicts with profit.py

            # Manage existing positions (always active for portfolio positions)
            for symbol in list(STATE.keys()):
                position = STATE[symbol]
                current_price = last_price(client, symbol)

                if current_price <= 0:
                    continue

                # Update peak
                if current_price > position["peak"]:
                    position["peak"] = current_price
                    save_state(STATE)

                # Check breakeven move
                if not position["breakeven_moved"]:
                    initial_stop = position["entry"] * (1 - cfg["exit"]["initial_stop_pct"] / 100)
                    should_move, new_stop = should_move_to_breakeven(
                        position["entry"], initial_stop, current_price, position["breakeven_moved"]
                    )
                    if should_move:
                        position["breakeven_moved"] = True
                        save_state(STATE)
                        print(f"🛡️  {symbol}: Moved to breakeven @ ${new_stop:.4f}")

                # Check trailing stop
                peak_dd = (position["peak"] - current_price) / position["peak"] * 100
                profit_pct = (current_price - position["entry"]) / position["entry"] * 100

                # Exit conditions
                should_exit = False
                exit_reason = ""

                if peak_dd >= cfg["exit"]["trail_from_peak_pct"]:
                    should_exit = True
                    exit_reason = f"trailing stop (peak DD {peak_dd:.1f}%)"
                elif profit_pct >= cfg["exit"]["hard_take_profit_pct"]:
                    should_exit = True
                    exit_reason = f"hard TP {profit_pct:.1f}%"
                elif not position["breakeven_moved"] and current_price <= position["entry"] * (1 - cfg["exit"]["initial_stop_pct"] / 100):
                    should_exit = True
                    exit_reason = f"initial SL {profit_pct:.1f}%"

                if should_exit:
                    if place_sell_order(client, symbol, position["size"], exit_reason):
                        print(f"🎯 {symbol}: Exit @ ${current_price:.4f} ({exit_reason}) PnL: {profit_pct:+.1f}%")

                        # Send exit notification
                        profit_emoji = "🟢" if profit_pct > 0 else "🔴"
                        telegram_msg = f"{profit_emoji} <b>[PORTFOLIO SELL]</b> {symbol}\n💰 Size: {position['size']:.3f}\n💵 Exit: ${current_price:.4f}\n📊 PnL: {profit_pct:+.1f}%\n🎯 Reason: {exit_reason}"
                        send_telegram_sync(telegram_msg)

                        del STATE[symbol]
                        save_state(STATE)

                # Check pyramiding
                elif cfg["pyramiding"]["enable"] and position["adds_done"] < cfg["pyramiding"]["max_adds"]:
                    add_threshold = position["peak"] * (1 + cfg["pyramiding"]["add_on_move_pct"] / 100)
                    if current_price >= add_threshold:
                        if place_buy_order(client, cfg, symbol, current_price):
                            position["adds_done"] += 1
                            position["size"] += cfg["buy_amount_usdt"] / current_price
                            save_state(STATE)
                            print(f"📈 {symbol}: Pyramid add #{position['adds_done']} @ ${current_price:.4f}")

            # Status update during scheduler scans
            if len(STATE) > 0 and (current_time - last_scan_time < 60):  # Show status after scan
                total_invested = len(STATE) * cfg["buy_amount_usdt"]
                print(f"📊 [PORTFOLIO] {len(STATE)}/{cfg['max_open_positions']} positions, ${total_invested} invested")
                for symbol, pos in STATE.items():
                    price = last_price(client, symbol)
                    if price > 0:
                        pnl_pct = (price - pos["entry"]) / pos["entry"] * 100
                        peak_dd = (pos["peak"] - price) / pos["peak"] * 100
                        print(f"  📈 {symbol}: PnL {pnl_pct:+.1f}% | Peak DD {peak_dd:.1f}% | Adds {pos['adds_done']}")

            # Sleep longer in scheduler mode to avoid conflicts
            time.sleep(60)  # Check every minute instead of every 3 seconds

        except KeyboardInterrupt:
            print("\n🛑 Portfolio Manager stopping...")
            break
        except Exception as e:
            print(f"❌ Error in main loop: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()