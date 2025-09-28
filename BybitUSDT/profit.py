import ccxt
import requests
import os
from datetime import datetime, timezone
from time import sleep
import time
import json
import logging
from prettyprinter import pprint
import bybitwrapper
from pathlib import Path
import csv
try:
    import yaml
except Exception:
    yaml = None

def execute_risk_commands():
    """Execute risk commands from command center if available."""
    try:
        with open('../risk_commands.json', 'r') as f:
            command = json.load(f)

        command_mode = command.get('mode', 'NORMAL')
        if command_mode in ['NORMAL', 'ALERT']:
            return  # No action needed

        print(f"[RISK-EXEC] Executing command: {command_mode} - {command.get('message', '')}")

        # Execute position closing if commanded
        if command.get('close_positions') and command.get('close_fraction'):
            close_fraction = command['close_fraction']
            print(f"[RISK-EXEC] Closing {close_fraction:.0%} of positions as commanded")

            # Get all symbols from coins.json to close
            for coin in coins:
                symbol = coin['symbol']
                position = check_positions(symbol)
                if position and position['size'] > 0:
                    try:
                        # Calculate quantity to close
                        close_qty = float(position['size']) * close_fraction
                        if close_qty > 0:
                            # Determine opposite side for closing
                            close_side = 'Sell' if position['side'] == 'Buy' else 'Buy'

                            # Close position with reduceOnly market order
                            print(f"[RISK-CLOSE] {symbol} {close_side} {close_qty} (reduceOnly)")
                            close_order = client.LinearOrder.LinearOrder_new(
                                side=close_side,
                                symbol=symbol + "USDT",
                                order_type="Market",
                                qty=close_qty,
                                reduce_only=True,
                                time_in_force="IOC"
                            ).result()
                            print(f"[RISK-CLOSE] {symbol} executed: {close_order.get('ret_msg', 'OK')}")
                    except Exception as e:
                        print(f"[RISK-CLOSE] Error closing {symbol}: {e}")

        # Cancel all orders if commanded
        if command.get('cancel_all_orders'):
            print(f"[RISK-EXEC] Cancelling all orders as commanded")
            for coin in coins:
                symbol = coin['symbol']
                try:
                    cancel_orders(symbol, 1, 'Buy')  # Use existing function
                    cancel_stops(symbol, 1, 'Buy')   # Use existing function
                except Exception as e:
                    print(f"[RISK-CANCEL] Error cancelling {symbol}: {e}")

    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        # No command file or invalid - continue normally
        pass
    except Exception as e:
        print(f"[RISK-EXEC] Error executing commands: {e}")

def check_panic_trading_enabled():
    """Check if panic button has disabled trading."""
    try:
        # Check for panic lock file
        panic_lock_path = '../state/panic.lock'
        if os.path.exists(panic_lock_path):
            with open(panic_lock_path, 'r') as f:
                data = json.load(f)
                if data.get('panic_tripped', False):
                    return False

        # Check for trading disabled flag
        if os.path.exists('../trading_disabled.flag'):
            return False

        # Check panic server status via HTTP
        try:
            import requests
            response = requests.get('http://127.0.0.1:8787/healthz', timeout=1)
            if response.status_code == 200:
                health = response.json()
                if not health.get('trading_enabled', True):
                    return False
        except:
            pass  # If panic server is down, continue trading

        return True

    except Exception as e:
        print(f"[PANIC-CHECK] Error checking panic status: {e}")
        return True  # Default to allowing trading if check fails

with open('../settings.json', 'r') as fp:
    settings = json.load(fp)
fp.close()
with open('../coins.json', 'r') as fp:
    coins = json.load(fp)
fp.close()


exchange_id = 'binance'
exchange_class = getattr(ccxt, exchange_id)
binance = exchange_class({
    'apiKey': None,
    'secret': None,
    'timeout': 30000,
    'enableRateLimit': True,
    'options': {'defaultType': 'future'},
})
binance.load_markets()

client = bybitwrapper.bybit(test=False, api_key=settings['key'], api_secret=settings['secret'])

"""
Telegram + Risk utilities (daily PnL, IM%)
"""
# Telegram
TELEGRAM_BOT_TOKEN = None
TELEGRAM_CHAT_ID = None

def _load_telegram_config():
    global TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    try:
        cfg_path = Path('../config/panic.yaml')
        if cfg_path.exists() and yaml is not None:
            with open(cfg_path, 'r') as f:
                cfg = yaml.safe_load(f)
            TELEGRAM_BOT_TOKEN = cfg['alert']['telegram']['bot_token']
            TELEGRAM_CHAT_ID = cfg['alert']['telegram']['chat_id']
    except Exception as e:
        print(f"[TELEGRAM] Config load error: {e}")

def send_telegram(message: str):
    try:
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            _load_telegram_config()
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        requests.post(url, json=payload, timeout=3)
    except Exception as e:
        print(f"[TELEGRAM] send error: {e}")

# Daily state + IM helpers
DAILY_STATE_PATH = Path('../state/daily_pnl.json')
PNL_CSV_PATH = Path('pnl_log.csv')

def _utc_date_str(ts: float | None = None) -> str:
    dt = datetime.now(timezone.utc) if ts is None else datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime('%Y-%m-%d')

def get_equity(client) -> float:
    try:
        sess = getattr(client, '_session', None)
        if sess is not None:
            r = sess.get_wallet_balance(accountType="UNIFIED")
            lst = (r.get('result', {}) or {}).get('list', [])
            if lst:
                eq = float(lst[0].get('totalEquity') or 0.0)
                if eq > 0:
                    return eq
        # Fallback legacy
        balance_body, _ = client.Wallet.Wallet_getBalance(coin="USDT").result()
        return float(balance_body.get("result", {}).get("USDT", {}).get("wallet_balance", 0.0))
    except Exception as e:
        print(f"[EQUITY] error: {e}")
        return 0.0

def compute_im_percent(client) -> float:
    try:
        sess = getattr(client, '_session', None)
        equity = get_equity(client)
        if equity <= 0:
            return 0.0
        if sess is not None:
            try:
                r = sess.get_wallet_balance(accountType="UNIFIED")
                lst = (r.get('result', {}) or {}).get('list', [])
                if lst:
                    acct = lst[0]
                    total_im = float(acct.get('totalInitialMargin') or acct.get('accountIM') or acct.get('totalIM') or 0.0)
                    if total_im > 0:
                        return (total_im / equity) * 100.0
            except Exception:
                pass
            # Approx from positions
            im_sum = 0.0
            rp = sess.get_positions(category="linear")
            for p in (rp.get('result', {}) or {}).get('list', []) or []:
                size = float(p.get('size') or 0)
                if size <= 0:
                    continue
                price = float(p.get('markPrice') or p.get('avgPrice') or 0)
                lev = float(p.get('leverage') or 1)
                if price > 0 and lev > 0:
                    im_sum += (size * price) / max(1.0, lev)
            if im_sum > 0:
                return (im_sum / equity) * 100.0
        return 0.0
    except Exception as e:
        print(f"[IM%] error: {e}")
        return 0.0

def _load_daily_state() -> dict:
    if DAILY_STATE_PATH.exists():
        try:
            with open(DAILY_STATE_PATH, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_daily_state(state: dict):
    try:
        DAILY_STATE_PATH.parent.mkdir(exist_ok=True)
        with open(DAILY_STATE_PATH, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[DAILY_STATE] save error: {e}")

def ensure_daily_baseline(equity_now: float) -> tuple[float, str]:
    state = _load_daily_state()
    today = _utc_date_str()
    day = state.get('date')
    baseline = state.get('baseline_equity')
    if day != today or not baseline:
        state.update({'date': today, 'baseline_equity': equity_now, 'num_trades': 0})
        _save_daily_state(state)
        print(f"[DAILY] baseline set {today}: equity={equity_now:.2f}")
        send_telegram(f"🛠️ Config updated to equity={settings['risk_management'].get('equity_usdt', 'N/A')}, aggressive mode ON")
        return equity_now, today
    return float(baseline), today

def update_closed_trades_counter():
    try:
        sess = getattr(client, '_session', None)
        if sess is None:
            return
        r = sess.get_positions(category="linear")
        current = set()
        for p in (r.get('result', {}) or {}).get('list', []) or []:
            if float(p.get('size') or 0) > 0:
                current.add(p.get('symbol', '').replace('USDT', ''))
        prev = set(update_closed_trades_counter.prev_open or [])
        closed = prev - current
        if closed:
            state = _load_daily_state()
            state['num_trades'] = int(state.get('num_trades', 0)) + len(closed)
            _save_daily_state(state)
        update_closed_trades_counter.prev_open = list(current)
    except Exception:
        pass
update_closed_trades_counter.prev_open = []

def log_pnl_csv(daily_profit_pct: float, daily_profit_usd: float):
    try:
        file_exists = PNL_CSV_PATH.exists()
        with open(PNL_CSV_PATH, 'a', newline='') as f:
            w = csv.writer(f)
            if not file_exists:
                w.writerow(['date', 'daily_profit_pct', 'daily_profit_usd', 'num_trades'])
            state = _load_daily_state()
            w.writerow([_utc_date_str(), f"{daily_profit_pct:.2f}", f"{daily_profit_usd:.2f}", int(state.get('num_trades', 0))])
    except Exception as e:
        print(f"[PNL-CSV] error: {e}")

def _round_qty_for_symbol(symbol: str, qty: float) -> float:
    qty_step_01_symbols = ['XRP', 'DOT', 'UNI', 'SOL', 'LINK', 'FIL', 'EOS', 'APEX', 'BARD', 'ALPINE', 'WLD', 'SNX', 'BAND', 'MIRA', 'QTUM', 'W', '0G']
    qty_step_1_symbols = ['ADA', 'DOGE', 'MATIC', 'XLM', 'XPL', 'SQD', 'FARTCOIN', 'MYX', 'ORDER', 'SOLV', 'AIA', 'ASTER', 'HEMI', 'TA', 'AVNT', 'DOLO', 'MAV', 'PLUME', 'OPEN', 'STBL']
    qty_step_10_symbols = ['PENGU', 'LINEA', 'BLESS', 'MEME', 'H', 'SUN', 'AIO']
    qty_step_100_symbols = ['1000BONK', 'AKE', '1000PEPE']
    if symbol in qty_step_01_symbols:
        return round(qty, 1)
    if symbol in qty_step_1_symbols:
        return int(qty)
    if symbol in qty_step_10_symbols:
        return int(qty // 10) * 10
    if symbol in qty_step_100_symbols:
        return int(qty // 100) * 100
    return round(qty, 3)

def close_all_positions_reduce_only():
    try:
        sess = getattr(client, '_session', None)
        if sess is None:
            return 0, 0
        r = sess.get_positions(category="linear")
        closed, errors = 0, 0
        for p in (r.get('result', {}) or {}).get('list', []) or []:
            size = float(p.get('size') or 0)
            if size <= 0:
                continue
            full_symbol = p.get('symbol', '')
            symbol = full_symbol.replace('USDT', '')
            side = str(p.get('side', '')).lower()
            if side == 'buy':
                close_side = 'Sell'; idx = 1
            else:
                close_side = 'Buy'; idx = 2
            qty = _round_qty_for_symbol(symbol, size)
            try:
                resp = sess.place_order(
                    category="linear", symbol=full_symbol, side=close_side,
                    orderType="Market", qty=str(qty), timeInForce="IOC",
                    reduceOnly=True, positionIdx=idx)
                if resp.get('retCode') == 0:
                    closed += 1
                else:
                    resp2 = sess.place_order(
                        category="linear", symbol=full_symbol, side=close_side,
                        orderType="Market", qty=str(qty), timeInForce="IOC",
                        reduceOnly=True)
                    if resp2.get('retCode') == 0:
                        closed += 1
                    else:
                        errors += 1
                        print(f"[CLOSE-ALL] {symbol} fail: {resp2.get('retMsg')}")
            except Exception as e:
                errors += 1
                print(f"[CLOSE-ALL] {symbol} exception: {e}")
        try:
            Path('../trading_disabled.flag').write_text('1')
        except Exception:
            pass
        return closed, errors
    except Exception as e:
        print(f"[CLOSE-ALL] fatal: {e}")
        return 0, 1

def reduce_positions_by_fraction(frac: float):
    try:
        sess = getattr(client, '_session', None)
        if sess is None:
            return 0, 0
        r = sess.get_positions(category="linear")
        reduced, errors = 0, 0
        for p in (r.get('result', {}) or {}).get('list', []) or []:
            size = float(p.get('size') or 0)
            if size <= 0:
                continue
            full_symbol = p.get('symbol', '')
            symbol = full_symbol.replace('USDT', '')
            side = str(p.get('side', '')).lower()
            qty = max(0.0, size * float(frac))
            if qty <= 0:
                continue
            qty = _round_qty_for_symbol(symbol, qty)
            close_side = 'Sell' if side == 'buy' else 'Buy'
            idx = 1 if side == 'buy' else 2
            try:
                resp = sess.place_order(
                    category="linear", symbol=full_symbol, side=close_side,
                    orderType="Market", qty=str(qty), timeInForce="IOC",
                    reduceOnly=True, positionIdx=idx)
                if resp.get('retCode') == 0:
                    reduced += 1
                else:
                    resp2 = sess.place_order(
                        category="linear", symbol=full_symbol, side=close_side,
                        orderType="Market", qty=str(qty), timeInForce="IOC",
                        reduceOnly=True)
                    if resp2.get('retCode') == 0:
                        reduced += 1
                    else:
                        errors += 1
                        print(f"[REDUCE] {symbol} fail: {resp2.get('retMsg')}")
            except Exception as e:
                errors += 1
                print(f"[REDUCE] {symbol} exception: {e}")
        return reduced, errors
    except Exception as e:
        print(f"[REDUCE] fatal: {e}")
        return 0, 1


def load_jsons():
    #print("Checking Settings")
    with open('../coins.json', 'r') as fp:
        coins = json.load(fp)
    fp.close()
    with open('../settings.json', 'r') as fp:
        settings = json.load(fp)
    fp.close()

def load_symbols(coins):
    symbols = []
    for coin in coins:
        symbols.append(coin['symbol'])
    return symbols

def check_positions(symbol):
    # Read Portfolio-Momentum state (if any), but only skip if real position exists
    skip_if_managed = False
    try:
        from pathlib import Path
        import json as _json
        portfolio_state_path = Path("portfolio_state.json")
        if portfolio_state_path.exists():
            with open(portfolio_state_path, 'r') as f:
                pm_state = _json.load(f)
            pm_positions = pm_state.get("positions", pm_state if isinstance(pm_state, dict) else {})
            if isinstance(pm_positions, dict) and symbol in pm_positions:
                skip_if_managed = True
    except Exception as e:
        print(f"[PM_CHECK] Error checking PM state: {e}")

    positions = client.LinearPositions.LinearPositions_myPosition(symbol=symbol+"USDT").result()
    if positions[0]['ret_msg'] == 'OK':
        for position in positions[0]['result']:
            if position['entry_price'] > 0:
                if skip_if_managed:
                    print(f"[SKIP] {symbol} is managed by Portfolio-Momentum system")
                    return None
                print("Position found for ", symbol, " entry price of ", position['entry_price'])
                return position
            else:
                pass

    else:
        print("API NOT RESPONSIVE AT CHECK ORDER")
        sleep(5)

def get_price_precision(symbol):
    precision = client.Symbol.Symbol_get().result()
    pprecsion = precision[0]["result"]

    for x in range(len(pprecsion)):
        if pprecsion[x]["name"] == symbol+"USDT":
            numbers = pprecsion[x]["price_filter"]["tick_size"]
            return len(numbers) - 2
    return None
        
def _extract_entry_price_by_side(entry_result, expected_side, fallback_ticker):
    """
    Selectează entry_price pe baza side-ului poziției.
    entry_result: structura returnată de client.LinearPositions...().result()[0]
    expected_side: 'Buy' sau 'Sell'
    fallback_ticker: preț curent dacă nu găsim nimic valid
    """
    try:
        positions = entry_result.get("result", []) or []
        # Caută întâi poziția cu side așteptat
        for pos in positions:
            side_val = str(pos.get("side", ""))
            if side_val.lower().startswith(str(expected_side).lower()[:1]) and float(pos.get("entry_price", 0) or 0) > 0:
                return float(pos.get("entry_price"))
        # Fallback: orice poziție cu entry_price > 0
        for pos in positions:
            if float(pos.get("entry_price", 0) or 0) > 0:
                return float(pos.get("entry_price"))
    except Exception:
        pass
    # Ultimul fallback: folosește prețul curent (ticker)
    return float(fallback_ticker)
        
def tp_calc(symbol, side):
    entry_price_data = client.LinearPositions.LinearPositions_myPosition(symbol=symbol + 'USDT').result()
    for coin in coins:
        if coin['symbol'] == symbol:
            precision = get_price_precision(symbol)
            # Preț curent pentru fallback
            current_ticker = fetch_ticker(symbol)
            entry_price = _extract_entry_price_by_side(entry_price_data[0], side, current_ticker)

            if side == 'Buy':
                price = round(entry_price + (entry_price * (coin['take_profit_percent'] / 100)), precision)
                next_side = 'Sell'
                return price, next_side
            else:
                next_side = 'Buy'
                # Păstrăm formula existentă din proiect pentru short TP
                price = round(((entry_price * (coin['take_profit_percent'] / 100) - entry_price) * -1), precision)
                return price, next_side
        else:
            pass    
 
def fetch_ticker(symbol):
    tickerDump = binance.fetch_ticker(symbol + '/USDT')
    ticker = float(tickerDump['last'])
    return ticker

def fetch_price(symbol, side):
    ticker = fetch_ticker(symbol)
    for coin in coins:
        if coin['symbol'] == symbol:
            if side == 'Buy':
                price = round(ticker + (ticker * (coin['take_profit_percent'] / 100)), 3)
                side = 'Sell'
                return price, side
            else:
                side = 'Buy'
                price = round(((ticker * (coin['take_profit_percent'] / 100) - ticker) * -1), 3)
                return price, side
        else:
            pass

def fetch_stop_price(symbol, side):
    ticker = fetch_ticker(symbol)
    for coin in coins:
        if coin['symbol'] == symbol:
            if side == 'Buy':
                price = round(ticker - (ticker * (coin['stop_loss_percent'] / 100)), 3)
                side = 'Sell'
                return price, side, price
            else:
                side = 'Buy'
                price = round(ticker + (ticker * (coin['stop_loss_percent'] / 100)), 3)
                return price, side, ticker
        else:
            pass

def cancel_orders(symbol, size, side):
    orders = client.LinearOrder.LinearOrder_getOrders(symbol=symbol+"USDT", limit='5').result()
    try:
        for order in orders[0]['result']['data']:
            if order['order_status'] != 'Filled' and order['order_status'] != 'Cancelled':
                prices = fetch_price(symbol, side)
                if size != order['qty']:
                    #print("Canceling Open Orders ", symbol)
                    cancel = client.LinearOrder.LinearOrder_cancel(symbol=symbol+"USDT", order_id=order['order_id']).result()
                    sleep(0.25)
                else:
                    pass
                    #print("No Changes needed for ", symbol, " Take Profit")
            else:
                pass

    except TypeError:
        pass

def cancel_stops(symbol, size, side):
    orders = client.LinearConditional.LinearConditional_getOrders(symbol=symbol+"USDT", limit='5').result()
    try:
        for order in orders[0]['result']['data']:
            #pprint(order)
            if order['order_status'] != 'Deactivated':
                #print("Canceling Open Stop Orders ", symbol)
                cancel = client.LinearConditional.LinearConditional_cancel(symbol=symbol+"USDT", stop_order_id=order['stop_order_id']).result()
                #pprint(cancel)
            else:
                pass

    except TypeError:
        pass


def set_tp(symbol, size, side):
    try:
        prices = tp_calc(symbol, side)
        current_price = fetch_ticker(symbol)
        tp_price = prices[0]
        tp_side = prices[1]

        # Optional: Validate TP direction makes sense
        if side == 'Buy':  # LONG position
            # TP should be Sell Limit with price > current
            if tp_side == 'Sell' and tp_price <= current_price:
                print(f"[TP] skip {symbol}: LONG but TP price={tp_price} <= current={current_price}")
                return {"ret_msg": "TP price validation failed - skipped"}
        elif side == 'Sell':  # SHORT position
            # TP should be Buy Limit with price < current
            if tp_side == 'Buy' and tp_price >= current_price:
                print(f"[TP] skip {symbol}: SHORT but TP price={tp_price} >= current={current_price}")
                return {"ret_msg": "TP price validation failed - skipped"}

        # Fix quantity precision for TP orders - use exact position size
        # Get current position to get actual size
        current_position = client.LinearPositions.LinearPositions_myPosition(symbol=symbol+"USDT").result()
        actual_size = size  # default to passed size

        if current_position[0]['ret_msg'] == 'OK':
            for pos in current_position[0]['result']:
                if float(pos['entry_price']) > 0:
                    actual_size = pos['size']  # Use exact position size
                    break

        print(f"[TP] setting for {symbol}: side={tp_side}, price={tp_price}")

        cancel = client.LinearOrder.LinearOrder_cancel(symbol=symbol + "USDT").result()
        order = client.LinearOrder.LinearOrder_new(side=tp_side, symbol=symbol + "USDT", order_type="Limit", qty=actual_size,
                                           price=tp_price, time_in_force="GoodTillCancel",
                                           reduce_only=True, close_on_trigger=False).result()
        return order

    except Exception as e:
        error_msg = str(e)
        print(f"[TP] error for {symbol}: {error_msg} - continue")
        return {"ret_msg": f"TP error: {error_msg}"}

def set_sl(symbol, size, side):
    try:
        # Check for existing SL orders first (idempotency)
        existing_orders = client.LinearConditional.LinearConditional_getOrders(symbol=symbol + "USDT", limit='5').result()
        has_active_sl = False
        try:
            for order in existing_orders[0]['result']['data']:
                if order['order_status'] not in ['Deactivated', 'Cancelled']:
                    has_active_sl = True
                    print(f"[SL] existing active SL found for {symbol}, skip setting new one")
                    break
        except (TypeError, KeyError):
            pass

        if has_active_sl:
            return {"ret_msg": "SL already exists"}

        prices = fetch_stop_price(symbol, side)
        current_price = fetch_ticker(symbol)
        trigger_price = prices[0]  # stop_px
        sl_side = prices[1]        # opposite side for SL

        # Determine correct triggerDirection based on Bybit v5 rules
        trigger_direction = None

        if side == 'Buy':  # LONG position
            # SL should be Sell with triggerPrice < current (Falling = 2)
            if sl_side == 'Sell' and trigger_price < current_price:
                trigger_direction = 2  # Falling
            else:
                print(f"[SL] skip (direction/trigger mismatch) {symbol}: LONG but triggerPrice={trigger_price} >= current={current_price}")
                return {"ret_msg": "SL direction mismatch - skipped"}

        elif side == 'Sell':  # SHORT position
            # SL should be Buy with triggerPrice > current (Rising = 1)
            if sl_side == 'Buy' and trigger_price > current_price:
                trigger_direction = 1  # Rising
            else:
                print(f"[SL] skip (direction/trigger mismatch) {symbol}: SHORT but triggerPrice={trigger_price} <= current={current_price}")
                return {"ret_msg": "SL direction mismatch - skipped"}

        if trigger_direction is None:
            print(f"[SL] skip {symbol}: unable to determine triggerDirection")
            return {"ret_msg": "SL triggerDirection error - skipped"}

        # Cancel existing stops before placing new one
        cancel_stops(symbol, size, side)

        # Fix quantity precision for SL orders - use exact position size
        # Get current position to get actual size
        current_position = client.LinearPositions.LinearPositions_myPosition(symbol=symbol+"USDT").result()
        actual_size = size  # default to passed size

        if current_position[0]['ret_msg'] == 'OK':
            for pos in current_position[0]['result']:
                if float(pos['entry_price']) > 0:
                    actual_size = pos['size']  # Use exact position size
                    break

        print(f"[SL] setting for {symbol}: side={sl_side}, triggerPrice={trigger_price}, direction={trigger_direction}")

        order = client.LinearConditional.LinearConditional_new(
            order_type="Limit",
            side=sl_side,
            symbol=symbol+"USDT",
            qty=actual_size,
            price=trigger_price,
            base_price=prices[2],
            stop_px=trigger_price,
            time_in_force="GoodTillCancel",
            reduce_only=True,  # Fixed: SL should be reduceOnly=True
            trigger_by='LastPrice',
            close_on_trigger=False,
            trigger_direction=trigger_direction  # Pass explicit trigger direction
        ).result()

        return order

    except Exception as e:
        # Handle error 110092 and other errors gracefully
        error_msg = str(e)
        if "110092" in error_msg:
            print(f"[SL] error 110092 for {symbol}: {error_msg} - continue")
        else:
            print(f"[SL] error for {symbol}: {error_msg} - continue")
        return {"ret_msg": f"SL error: {error_msg}"}
    #pprint(order)
def fetch_positions():

    for coin in coins:
        symbol = coin['symbol']

        position = check_positions(symbol)

        if position != None:
            cancel_orders(symbol, position['size'], position['side'])
            # Safe TP/SL logging wrapper
            try:
                print(f"[TP/SL] calc start symbol={symbol} side={position['side']} size={position['size']}")
                tp_prices = tp_calc(symbol, position['side'])
                print(f"[TP/SL] prices -> {tp_prices}")
                r1 = set_tp(symbol, position['size'], position['side'])
                print(f"[TP] resp -> {r1}")
                r2 = set_sl(symbol, position['size'], position['side'])
                print(f"[SL] resp -> {r2}")
                print(f"[TP/SL] OK symbol={symbol}")
            except Exception as e:
                import traceback
                print(f"[TP/SL] FAIL symbol={symbol} err={e}")
                traceback.print_exc()
                sleep(1.5)
        else:
            cancel_stops(symbol, 1, 'Buy')


load_jsons()

print("🎯 Starting Take Profit & Order Manager (Live Mode)")
print("📋 Mode: Rapid TP/SL management + Portfolio conflict avoidance")
print("⚡ Speed: Fast response for Win/Loss positions")
print()
# Idempotency state: remember last side/size set time per symbol
LAST_STATE = {}
LAST_SET_TS = {}
IDEMPOTENCY_COOLDOWN_SEC = 45
while True:
    print("Checking for Positions.........")
    # =========================
    # Daily PnL + IM% controls
    # =========================
    try:
        equity_now = get_equity(client)
        baseline, _ = ensure_daily_baseline(equity_now)
        if baseline > 0:
            daily_usd = equity_now - baseline
            daily_pct = (daily_usd / baseline) * 100.0
        else:
            daily_usd = 0.0
            daily_pct = 0.0

        # IM% monitoring (alerts and auto-reduce)
        im_pct = compute_im_percent(client)
        now_ts = time.time()
        last_im_warn = globals().get('_LAST_IM_WARN', 0)
        last_im_reduce = globals().get('_LAST_IM_REDUCE', 0)
        if im_pct > 80 and (now_ts - last_im_warn) > 300:
            send_telegram(f"⚠️ Warning: IM% > 80% (IM={im_pct:.1f}%). High leverage risk.")
            globals()['_LAST_IM_WARN'] = now_ts
        if im_pct > 100 and (now_ts - last_im_reduce) > 300:
            r_ok, r_err = reduce_positions_by_fraction(0.20)
            send_telegram(f"⛔ Danger: IM% exceeded 100% (IM={im_pct:.1f}%). Exposure reduced 20% | OK {r_ok}, Err {r_err}.")
            globals()['_LAST_IM_REDUCE'] = now_ts

        # Daily stop/target
        target_pct = float(settings.get('risk_management', {}).get('daily_target_pct', 10))
        max_dd_pct = float(settings.get('risk_management', {}).get('daily_max_dd_pct', 5))

        if daily_pct >= target_pct:
            c_ok, c_err = close_all_positions_reduce_only()
            send_telegram(f"🎯 Daily profit target hit (+{daily_pct:.1f}%). Closed all ({c_ok} OK/{c_err} Err) and stopped.")
            log_pnl_csv(daily_pct, daily_usd)
            # Disable trading, then idle
            sleep(settings['cooldown'])
            continue
        if daily_pct <= -max_dd_pct:
            c_ok, c_err = close_all_positions_reduce_only()
            send_telegram(f"🛑 Daily stop-loss hit ({daily_pct:.1f}%). Closed all ({c_ok} OK/{c_err} Err) and stopped.")
            log_pnl_csv(daily_pct, daily_usd)
            sleep(settings['cooldown'])
            continue

        # Update closed trades counter (for CSV)
        update_closed_trades_counter()
    except Exception as e:
        print(f"[DAILY/IM] error: {e}")

    # Execute risk commands from command center BEFORE processing positions
    execute_risk_commands()

    # Check panic button system integration
    if not check_panic_trading_enabled():
        print("[PANIC] Trading disabled by panic button - skipping all operations")
        sleep(settings['cooldown'])
        continue

    # Idempotent wrapper around fetch_positions
    try:
        for coin in coins:
            symbol = coin['symbol']
            position = check_positions(symbol)
            if position != None:
                prev = LAST_STATE.get(symbol)
                last_ts = LAST_SET_TS.get(symbol, 0)
                unchanged = prev == (position['side'], position['size'])
                recent = (time.time() - last_ts) < IDEMPOTENCY_COOLDOWN_SEC
                if unchanged and recent:
                    print(f"[TP/SL] already set recently for {symbol}, skip")
                    continue

                cancel_orders(symbol, position['size'], position['side'])
                try:
                    print(f"[TP/SL] calc start symbol={symbol} side={position['side']} size={position['size']}")
                    tp_prices = tp_calc(symbol, position['side'])
                    print(f"[TP/SL] prices -> {tp_prices}")
                    r1 = set_tp(symbol, position['size'], position['side'])
                    print(f"[TP] resp -> {r1}")
                    r2 = set_sl(symbol, position['size'], position['side'])
                    print(f"[SL] resp -> {r2}")
                    print(f"[TP/SL] OK symbol={symbol}")
                    LAST_STATE[symbol] = (position['side'], position['size'])
                    LAST_SET_TS[symbol] = time.time()
                except Exception as e:
                    import traceback
                    print(f"[TP/SL] FAIL symbol={symbol} err={e}")
                    traceback.print_exc()
                    sleep(1.5)
            else:
                cancel_stops(symbol, 1, 'Buy')
                if symbol in LAST_STATE:
                    del LAST_STATE[symbol]
                    LAST_SET_TS.pop(symbol, None)
    except Exception as e:
        import traceback
        print(f"[LOOP] FAIL err={e}")
        traceback.print_exc()
    sleep(settings['cooldown'])
