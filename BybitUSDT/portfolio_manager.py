#!/usr/bin/env python3
"""
Portfolio Momentum Manager - Trend Following System
Buys assets with strong daily momentum and holds with trailing stops
"""
import json
import time
import os
import statistics
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

def get_current_equity(client) -> float:
    """Get current account equity from Bybit"""
    try:
        # Prefer unified account equity if available
        session = getattr(client, "_session", None)
        if session:
            response = session.get_wallet_balance(accountType="UNIFIED")
            wallet_list = (response.get("result", {}) or {}).get("list", [])
            if wallet_list:
                total_equity = float(wallet_list[0].get("totalEquity", 0.0))
                if total_equity:
                    return total_equity

        # Fallback to legacy wallet balance (approximation)
        balance_body, _ = client.Wallet.Wallet_getBalance(coin="USDT").result()
        return float(balance_body.get("result", {}).get("USDT", {}).get("wallet_balance", 0.0))
    except Exception as e:
        print(f"[ERROR] Could not get equity: {e}")
        return 1000.0  # Conservative fallback to keep trading logic alive


def get_effective_budget(client, cfg: Dict) -> float:
    """Calculate the portfolio budget after reserving funds for Win/Loss"""
    current_equity = get_current_equity(client)
    reserved_for_winloss = current_equity * (cfg['reserve_for_winloss_pct'] / 100)
    portfolio_budget_cap = current_equity * (cfg['max_budget_pct'] / 100)
    available_equity = max(0.0, current_equity - reserved_for_winloss)
    return max(0.0, min(portfolio_budget_cap, available_equity))


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

def load_state() -> Dict[str, Dict]:
    """Load portfolio state from JSON file (positions + cooldowns)"""
    default_state = {"positions": {}, "cooldowns": {}}
    if not STATE_PATH.exists():
        return default_state

    try:
        with open(STATE_PATH, 'r') as f:
            data = json.load(f)

        if isinstance(data, dict) and "positions" in data:
            positions = data.get("positions", {}) or {}
            cooldowns = data.get("cooldowns", {}) or {}
        elif isinstance(data, dict):
            positions = {k: v for k, v in data.items() if isinstance(v, dict)}
            cooldowns = {}
        else:
            positions, cooldowns = {}, {}

        return {"positions": positions, "cooldowns": cooldowns}

    except Exception as e:
        print(f"[STATE] Error loading state: {e}")
        return default_state


def save_state(state: Dict[str, Dict]):
    """Persist portfolio state (positions + cooldowns)"""
    try:
        with open(STATE_PATH, 'w') as f:
            json.dump({
                "positions": state.get("positions", {}),
                "cooldowns": state.get("cooldowns", {})
            }, f, indent=2)
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

def can_buy_limited(
    client,
    cfg: Dict,
    symbol: str,
    positions: Dict[str, Dict],
    cooldowns: Dict[str, float],
    allowlist: Set[str],
    used_budget: float,
    effective_budget: float,
    current_time: float,
) -> tuple[bool, str, Dict]:
    """Check entry conditions with budget + cooldown limits and return candidate data."""

    if symbol not in allowlist:
        return False, "not in allowlist", {}

    if symbol in positions:
        return False, "already in portfolio", {}

    if len(positions) >= cfg["max_open_positions"]:
        return False, "max positions reached", {}

    cooldown_seconds = cfg['per_symbol_cooldown_min'] * 60
    last_buy_ts = cooldowns.get(symbol, 0)
    if last_buy_ts and (current_time - last_buy_ts) < cooldown_seconds:
        minutes_passed = int((current_time - last_buy_ts) // 60)
        return False, f"cooldown {minutes_passed}m < {cfg['per_symbol_cooldown_min']}m", {}

    if used_budget + cfg['buy_amount_usdt'] > effective_budget:
        return False, "insufficient budget", {}

    daily_change = daily_change_pct(client, symbol)
    if daily_change < cfg['entry']['daily_change_min_pct']:
        return False, f"daily change {daily_change:.1f}% < {cfg['entry']['daily_change_min_pct']}%", {}

    liq_notional = liq_notional_recent(symbol)
    if liq_notional < cfg['entry']['liq_notional_min_usd']:
        return False, f"liq notional ${liq_notional:.0f} < ${cfg['entry']['liq_notional_min_usd']}", {}

    candidate = {
        'symbol': symbol,
        'daily_change': daily_change,
        'liq_usd': liq_notional,
    }
    return True, f"daily:{daily_change:.1f}% liq:${liq_notional:.0f}", candidate


def calculate_breakeven_price(entry: float) -> float:
    """Calculate breakeven price including fees and small buffer."""
    # Bybit taker fee ~0.055% each side; include a small buffer
    fee_offset = entry * 0.0012  # ~0.12%
    return entry + fee_offset


def should_move_to_breakeven(entry: float, stop: float, current: float, already_moved: bool = False) -> tuple[bool, float]:
    """Move SL to breakeven at 0.5R. Returns (should_move, new_stop)."""
    if already_moved:
        return False, stop

    if not entry or not stop:
        return False, stop

    r_value = abs(entry - stop)
    if r_value == 0:
        return False, stop

    r_mult = (current - entry) / r_value
    if r_mult >= 0.5:
        return True, calculate_breakeven_price(entry)

    return False, stop


def set_leverage_1x(client, symbol: str):
    """Set leverage to 1x for symbol (best-effort)."""
    try:
        result = client._session.set_leverage(
            category="linear",
            symbol=f"{symbol}USDT",
            buyLeverage="1",
            sellLeverage="1",
        )
        if result.get('retCode') == 0:
            print(f"[LEVERAGE] {symbol}: Set to 1x")
            return True
        print(f"[LEVERAGE] {symbol}: set_leverage ret={result.get('retMsg')}")
        return False
    except Exception as e:
        print(f"[LEVERAGE] {symbol}: Exception setting leverage: {e}")
        return False


def place_buy_order(client, cfg: Dict, symbol: str, price: float) -> bool:
    """Place market buy order with qty precision fixes and 1x leverage."""
    try:
        qty = cfg["buy_amount_usdt"] / price

        # Quantity precision per symbol groups
        qty_step_01_symbols = ['XRP', 'DOT', 'UNI', 'SOL', 'LINK', 'FIL', 'EOS', 'APEX', 'BARD', 'ALPINE', 'WLD', 'SNX', 'BAND', 'MIRA', 'QTUM', 'W', '0G']
        qty_step_1_symbols = ['ADA', 'DOGE', 'MATIC', 'XLM', 'XPL', 'SQD', 'FARTCOIN', 'MYX', 'ORDER', 'SOLV', 'AIA', 'ASTER', 'HEMI', 'TA', 'AVNT', 'DOLO', 'MAV', 'PLUME', 'OPEN', 'STBL']
        qty_step_10_symbols = ['PENGU', 'LINEA', 'BLESS', 'MEME', 'H', 'SUN', 'AIO']
        qty_step_100_symbols = ['1000BONK', 'AKE', '1000PEPE']

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

        # Best-effort ensure leverage 1x (ignore failures)
        set_leverage_1x(client, symbol)

        order_link_id = f"PM-{symbol}-{int(time.time())}"
        result = client._session.place_order(
            category="linear",
            symbol=f"{symbol}USDT",
            side="Buy",
            orderType="Market",
            qty=str(qty),
            timeInForce="IOC",
            orderLinkId=order_link_id,
        )
        if result.get('retCode') == 0:
            print(f"[BUY] {symbol}: ${cfg['buy_amount_usdt']} qty={qty} @ ${price:.4f}")
            return True
        print(f"[BUY_FAIL] {symbol}: {result.get('retMsg')}")
        return False
    except Exception as e:
        print(f"[BUY_FAIL] {symbol}: Exception: {e}")
        return False


def place_sell_order(client, symbol: str, qty: float, reason: str) -> bool:
    """Place market sell order (reduceOnly) with qty precision fixes."""
    try:
        qty_step_01_symbols = ['XRP', 'DOT', 'UNI', 'SOL', 'LINK', 'FIL', 'EOS', 'APEX', 'BARD', 'ALPINE', 'WLD', 'SNX', 'BAND', 'MIRA', 'QTUM', 'W', '0G']
        qty_step_1_symbols = ['ADA', 'DOGE', 'MATIC', 'XLM', 'XPL', 'SQD', 'FARTCOIN', 'MYX', 'ORDER', 'SOLV', 'AIA', 'ASTER', 'HEMI', 'TA', 'AVNT', 'DOLO', 'MAV', 'PLUME', 'OPEN', 'STBL']
        qty_step_10_symbols = ['PENGU', 'LINEA', 'BLESS', 'MEME', 'H', 'SUN', 'AIO']
        qty_step_100_symbols = ['1000BONK', 'AKE', '1000PEPE']

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
            orderLinkId=order_link_id,
        )
        if result.get('retCode') == 0:
            print(f"[SELL] {symbol}: qty={qty} reason={reason}")
            return True
        print(f"[SELL_FAIL] {symbol}: {result.get('retMsg')}")
        return False
    except Exception as e:
        print(f"[SELL_FAIL] {symbol}: Exception: {e}")
        return False


def _has_real_position(client, symbol: str) -> bool:
    """Check on exchange if a real position is open for symbol"""
    try:
        resp = client._session.get_positions(category="linear", symbol=f"{symbol}USDT")
        if resp.get('retCode') != 0:
            return False
        for pos in resp.get('result', {}).get('list', []) or []:
            try:
                size = float(pos.get('size') or 0)
            except Exception:
                size = 0.0
            if size > 0:
                return True
        return False
    except Exception:
        return False


def _reconcile_positions_with_exchange(client, state: Dict[str, Dict]) -> int:
    """Remove symbols from state that have no real position on exchange"""
    removed = 0
    positions = state.get('positions', {})
    for sym in list(positions.keys()):
        if not _has_real_position(client, sym):
            print(f"[RECONCILE] Removing stale state for {sym} (no open position)")
            positions.pop(sym, None)
            removed += 1
    if removed:
        save_state(state)
    return removed


def main():
    """Main portfolio momentum loop."""
    print("🚀 Portfolio Momentum Manager Starting...")

    load_telegram_config()

    cfg, settings = load_config()
    if not cfg.get("enable", False):
        print("❌ Portfolio system disabled in config")
        return

    client = bybitwrapper.bybit(
        test=False,
        api_key=settings['key'],
        api_secret=settings['secret']
    )

    state = load_state()
    positions: Dict[str, Dict] = state.setdefault('positions', {})
    cooldowns: Dict[str, float] = state.setdefault('cooldowns', {})
    allowlist = load_allowlist()

    print(f"📊 Config: ${cfg['buy_amount_usdt']}/trade, max {cfg['max_open_positions']} positions")
    print(f"📋 Allowlist: {len(allowlist)} symbols loaded")
    print(f"💾 State: {len(positions)} active positions")
    print()

    scan_interval = cfg['scan_interval_sec']
    last_scan_time = 0.0
    remaining_budget = 0.0

    print(f"🎯 BUDGET CONTROL: max {cfg['max_budget_pct']}% equity")
    print(f"🛡️  WIN/LOSS RESERVED: {cfg['reserve_for_winloss_pct']}% equity")
    print(f"🔝 TOP-K LIMIT: {cfg['top_k']} best symbols per scan")
    print(f"🏠 MAX POSITIONS: {cfg['max_open_positions']}")
    print(f"⏰ SCAN INTERVAL: {scan_interval}s (slow mode)")
    print()

    while True:
        try:
            current_time = time.time()
            portfolio_invested = sum(pos['entry'] * pos['size'] for pos in positions.values())

            if current_time - last_scan_time >= scan_interval:
                print(f"🔍 [SCHEDULER] [{datetime.now().strftime('%H:%M:%S')}] Full portfolio scan")

                # Reconcile stale positions before scanning
                removed = _reconcile_positions_with_exchange(client, state)
                if removed:
                    print(f"🧹 [RECONCILE] Cleaned {removed} stale position(s) from state")

                effective_budget = get_effective_budget(client, cfg)
                used_budget = portfolio_invested
                remaining_budget = max(0.0, effective_budget - portfolio_invested)

                print(
                    f"💰 [BUDGET] Equity budget: used ${used_budget:.0f} / cap ${effective_budget:.0f}"
                    f" | available ${remaining_budget:.0f}"
                )
                print(
                    f"🛡️  [RESERVE] Win/Loss reserve: {cfg['reserve_for_winloss_pct']}%"
                )

                candidates = []
                for symbol in allowlist:
                    can_enter, _reason, candidate_data = can_buy_limited(
                        client,
                        cfg,
                        symbol,
                        positions,
                        cooldowns,
                        allowlist,
                        used_budget,
                        effective_budget,
                        current_time,
                    )
                    if can_enter:
                        candidates.append(candidate_data)

                entries_found = 0

                if not candidates:
                    print("🔍 [SCAN] No eligible candidates this cycle")
                else:
                    dc_values = [c['daily_change'] for c in candidates]
                    liq_values = [c['liq_usd'] for c in candidates]
                    dc_mean = statistics.mean(dc_values) if dc_values else 0.0
                    dc_stdev = statistics.stdev(dc_values) if len(dc_values) > 1 else 1.0
                    liq_mean = statistics.mean(liq_values) if liq_values else 0.0
                    liq_stdev = statistics.stdev(liq_values) if len(liq_values) > 1 else 1.0

                    for c in candidates:
                        dc_zscore = (c['daily_change'] - dc_mean) / dc_stdev if dc_stdev else 0.0
                        liq_zscore = (c['liq_usd'] - liq_mean) / liq_stdev if liq_stdev else 0.0
                        c['score'] = (
                            cfg['score']['w_daily_change'] * dc_zscore
                            + cfg['score']['w_liq_usd'] * liq_zscore
                        )

                    candidates.sort(key=lambda x: x['score'], reverse=True)
                    top_picks = candidates[: cfg['top_k']]

                    print(f"🔝 [TOP-K] {len(top_picks)} selected from {len(candidates)} candidates")
                    for idx, pick in enumerate(top_picks, start=1):
                        print(
                            f"  {idx}. {pick['symbol']} score={pick['score']:.2f}"
                            f" (dc={pick['daily_change']:.1f}%, liq=${pick['liq_usd']:.0f})"
                        )

                    for pick in top_picks:
                        if len(positions) >= cfg['max_open_positions']:
                            print("🏠 [LIMIT] Max portfolio positions reached; stopping entries")
                            break
                        if remaining_budget < cfg['buy_amount_usdt']:
                            print("💸 [LIMIT] Portfolio budget exhausted; stopping entries")
                            break

                        symbol = pick['symbol']
                        price = last_price(client, symbol)
                        if price <= 0:
                            print(f"[PRICE] {symbol}: unable to fetch price, skipping")
                            continue

                        if place_buy_order(client, cfg, symbol, price):
                            qty = cfg['buy_amount_usdt'] / price
                            positions[symbol] = {
                                "entry": price,
                                "peak": price,
                                "size": qty,
                                "adds_done": 0,
                                "breakeven_moved": False,
                                "timestamp": current_time,
                            }
                            cooldowns[symbol] = current_time
                            save_state(state)

                            telegram_msg = (
                                f"🟢 <b>[PORTFOLIO BUY]</b> {symbol}\n"
                                f"💰 Size: {qty:.3f}\n💵 Price: ${price:.4f}\n"
                                f"📊 Investment: ${cfg['buy_amount_usdt']}\n🏆 Score: {pick['score']:.2f}"
                            )
                            send_telegram_sync(telegram_msg)

                            entries_found += 1
                            portfolio_invested += cfg['buy_amount_usdt']
                            remaining_budget = max(0.0, effective_budget - portfolio_invested)
                            used_budget = portfolio_invested

                current_positions = len(positions)
                print(f"🔍 [SCHEDULER] Entry scan complete: {entries_found} new positions")

                next_scan = datetime.fromtimestamp(current_time + scan_interval)
                scheduler_msg = (
                    "🔍 <b>[PM-SCHEDULER]</b> Limited scan complete\n"
                    f"📊 New entries: {entries_found}/{cfg['top_k']}\n"
                    f"🎯 Portfolio positions: {current_positions}/{cfg['max_open_positions']}\n"
                    f"💰 Budget used: ${used_budget:.0f}/${effective_budget:.0f}\n"
                    f"⏰ Next scan: {next_scan.strftime('%H:%M:%S')} (in {scan_interval // 60} min)"
                )
                send_telegram_sync(scheduler_msg)

                last_scan_time = current_time
                print(f"⏰ [SCHEDULER] Next scan at {next_scan.strftime('%H:%M:%S')}")

            for symbol, position in list(positions.items()):
                current_price = last_price(client, symbol)
                if current_price <= 0:
                    continue

                if current_price > position["peak"]:
                    position["peak"] = current_price
                    save_state(state)

                if not position["breakeven_moved"]:
                    initial_stop = position["entry"] * (1 - cfg['exit']['initial_stop_pct'] / 100)
                    move_to_breakeven, breakeven_price = should_move_to_breakeven(
                        position["entry"],
                        initial_stop,
                        current_price,
                        position["breakeven_moved"],
                    )
                    if move_to_breakeven:
                        position["breakeven_moved"] = True
                        save_state(state)
                        print(f"🛡️  {symbol}: Moved stop to breakeven @ ${breakeven_price:.4f}")

                peak_dd = (position["peak"] - current_price) / position["peak"] * 100 if position["peak"] else 0.0
                profit_pct = (current_price - position["entry"]) / position["entry"] * 100 if position["entry"] else 0.0

                should_exit = False
                exit_reason = ""

                if peak_dd >= cfg['exit']['trail_from_peak_pct']:
                    should_exit = True
                    exit_reason = f"trailing stop (peak DD {peak_dd:.1f}%)"
                elif profit_pct >= cfg['exit']['hard_take_profit_pct']:
                    should_exit = True
                    exit_reason = f"hard TP {profit_pct:.1f}%"
                elif (
                    not position['breakeven_moved']
                    and current_price <= position['entry'] * (1 - cfg['exit']['initial_stop_pct'] / 100)
                ):
                    should_exit = True
                    exit_reason = f"initial SL {profit_pct:.1f}%"

                if should_exit:
                    if place_sell_order(client, symbol, position['size'], exit_reason):
                        profit_emoji = "🟢" if profit_pct > 0 else "🔴"
                        telegram_msg = (
                            f"{profit_emoji} <b>[PORTFOLIO SELL]</b> {symbol}\n"
                            f"💰 Size: {position['size']:.3f}\n💵 Exit: ${current_price:.4f}\n"
                            f"📊 PnL: {profit_pct:+.1f}%\n🎯 Reason: {exit_reason}"
                        )
                        send_telegram_sync(telegram_msg)

                        positions.pop(symbol, None)
                        save_state(state)
                        portfolio_invested = sum(pos['entry'] * pos['size'] for pos in positions.values())
                        remaining_budget = max(0.0, get_effective_budget(client, cfg) - portfolio_invested)
                        continue


                if (
                    cfg['pyramiding']['enable']
                    and position['adds_done'] < cfg['pyramiding']['max_adds']
                ):
                    add_threshold = position['peak'] * (1 + cfg['pyramiding']['add_on_move_pct'] / 100)
                    if current_price >= add_threshold:
                        available_for_add = max(
                            0.0,
                            get_effective_budget(client, cfg)
                            - sum(pos['entry'] * pos['size'] for pos in positions.values()),
                        )
                        if available_for_add < cfg['buy_amount_usdt']:
                            print(f"💸 {symbol}: Skipping pyramid add, budget unavailable")
                            continue

                        if place_buy_order(client, cfg, symbol, current_price):
                            position['adds_done'] += 1
                            position['size'] += cfg['buy_amount_usdt'] / current_price
                            save_state(state)
                            print(f"📈 {symbol}: Pyramid add #{position['adds_done']} @ ${current_price:.4f}")
                            portfolio_invested = sum(pos['entry'] * pos['size'] for pos in positions.values())
                            remaining_budget = max(0.0, get_effective_budget(client, cfg) - portfolio_invested)

            if positions and (current_time - last_scan_time < 60):
                total_invested = sum(pos['entry'] * pos['size'] for pos in positions.values())
                print(
                    f"📊 [PORTFOLIO] {len(positions)}/{cfg['max_open_positions']} positions,"
                    f" invested ~${total_invested:.0f}"
                )
                for symbol, pos in positions.items():
                    price = last_price(client, symbol)
                    if price > 0:
                        pnl_pct = (price - pos['entry']) / pos['entry'] * 100
                        peak_dd = (pos['peak'] - price) / pos['peak'] * 100 if pos['peak'] else 0.0
                        print(
                            f"  📈 {symbol}: PnL {pnl_pct:+.1f}% | Peak DD {peak_dd:.1f}% | Adds {pos['adds_done']}"
                        )

            time.sleep(60)

        except KeyboardInterrupt:
            print("\n🛑 Portfolio Manager stopping...")
            break
        except Exception as e:
            print(f"❌ Error in main loop: {e}")
            time.sleep(10)


if __name__ == "__main__":
    main()
