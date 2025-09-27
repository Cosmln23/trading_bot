import ccxt
import requests
import os
from datetime import datetime
from time import sleep
import time
from ccxt.base.errors import ExchangeError
import json
import logging
from unicorn_binance_websocket_api.manager import BinanceWebSocketApiManager
from prettyprinter import pprint
import bybitwrapper as bybitwrapper
from math import ceil
from pybit.exceptions import InvalidRequestError

def check_risk_commands():
    """Check risk commands from command center."""
    try:
        with open('../risk_commands.json', 'r') as f:
            command = json.load(f)

        # Check if new entries are allowed
        allow_entries = command.get('allow_new_entries', True)

        # Execute cancel orders if commanded
        if command.get('cancel_all_orders'):
            command_mode = command.get('mode', 'UNKNOWN')
            print(f'[RISK-COMMAND] Cancel all orders commanded by {command_mode} mode')
            # Cancel will be handled by the command itself through profit.py
            # Just block new entries here

        if not allow_entries:
            mode = command.get('mode', 'UNKNOWN')
            message = command.get('message', 'Risk management active')
            print(f'[RISK-BLOCK] New entries disabled by {mode}: {message}')

        return allow_entries

    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return True  # Default: allow if no command file or invalid

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


def load_jsons():
    #print("Checking Settings")
    with open('../coins.json', 'r') as fp:
        coins = json.load(fp)
    fp.close()
    with open('../settings.json', 'r') as fp:
        settings = json.load(fp)
    fp.close()

def fetch_vwap(symbol):
    global longwap, shortwap
    tickerSymbol = symbol + '/USDT'
    tickerDump = binance.fetch_ticker(tickerSymbol)
    vwap = tickerDump['vwap']
    for coin in coins:
        if coin['symbol'] == symbol:
            longwap = round(vwap - (vwap * (coin['long_vwap_offset'] / 100)), 4)
            shortwap = round(vwap + (vwap * (coin['short_vwap_offset'] / 100)), 4)
        else:
            pass

    return vwap, longwap, shortwap

def fetch_lickval(symbol):
    for coin in coins:
        if coin["symbol"] == symbol:
            return coin["lick_value"]
        else:
            pass

def load_symbols(coins):
    symbols = []
    for coin in coins:
        symbols.append(coin['symbol'])
    return symbols

def load_multipliers(coins, symbol):
    multipliers = []
    for coin in coins:
        if coin['symbol'] == symbol:
            multipliers.append(coin['dca_max_buy_level_1'])
            multipliers.append(coin['dca_max_buy_level_2'])
            multipliers.append(coin['dca_max_buy_level_3'])
            multipliers.append(coin['dca_max_buy_level_4'])
    return multipliers

def load_dca(coins, symbol):
    dca = []
    for coin in coins:
        if coin['symbol'] == symbol:
            dca.append(coin['dca_drawdown_percent_1'])
            dca.append(coin['dca_drawdown_percent_2'])
            dca.append(coin['dca_drawdown_percent_3'])
            dca.append(coin['dca_drawdown_percent_4'])
    return dca

def load_dca_values(coins, symbol):
    dca_values = []
    for coin in coins:
        if coin['symbol'] == symbol:
            dca_values.append(coin['dca_size_multiplier_1'])
            dca_values.append(coin['dca_size_multiplier_2'])
            dca_values.append(coin['dca_size_multiplier_3'])
            dca_values.append(coin['dca_size_multiplier_4'])
    return dca_values

def check_positions(symbol):
    positions = client.LinearPositions.LinearPositions_myPosition(symbol=symbol+"USDT").result()
    if positions[0]['ret_msg'] == 'OK':
        for position in positions[0]['result']:
            if position['entry_price'] > 0:
                print("Position found for ", symbol, " entry price of ", position['entry_price'])
                return True, position
            else:
                pass

    else:
        print("API NOT RESPONSIVE AT CHECK ORDER")
        sleep(5)

def fetch_ticker(symbol):
    tickerDump = binance.fetch_ticker(symbol + '/USDT')
    ticker = float(tickerDump['last'])
    return ticker

def fetch_order_size(symbol):
    global qty
    wallet_info = client.Wallet.Wallet_getBalance(coin="USDT").result()
    balance = wallet_info[0]['result']['USDT']['wallet_balance']
    ticker = fetch_ticker(symbol)
    for coin in coins:
        if coin['symbol'] == symbol:
            qtycalc = (balance / ticker) * coin['leverage']
            qty = qtycalc * (coin['order_size_percent_balance'] / 100)
        else:
            pass

    return qty

def set_leverage(symbol):
    for coin in coins:
        if coin['symbol'] == symbol:
            set = client.LinearPositions.LinearPositions_saveLeverage(symbol=symbol+"USDT", buy_leverage=coin['leverage'], sell_leverage=coin['leverage']).result()
        else:
            pass


def place_order(symbol, side, ticker, size):
    # Check if symbol is in Portfolio-Momentum system to avoid conflicts
    try:
        from pathlib import Path
        import json
        portfolio_state_path = Path("portfolio_state.json")
        if portfolio_state_path.exists():
            with open(portfolio_state_path, 'r') as f:
                pm_state = json.load(f)
                if symbol in pm_state:
                    print(f"[SKIP WL] {symbol} is in Portfolio-Momentum system. Skipping Win/Loss entry.")
                    return
    except Exception as e:
        print(f"[CONFLICT_CHECK] Error checking PM state: {e}")

    # Check risk commands before placing new orders
    if not check_risk_commands():
        print(f'[RISK-GUARD] New entries disabled - skipping {symbol} {side} order')
        return

    # Check panic button system integration
    if not check_panic_trading_enabled():
        print(f'[PANIC] Trading disabled by panic button - skipping {symbol} {side} order')
        return

    print('*****************************************************')
    print(symbol, side, " Entry Found!! Placing new order!!")
    print('*****************************************************')

    with open('../ordersize.json', 'r') as fp:
        ordersize = json.load(fp)

    override_size = None
    for entry in ordersize:
        if symbol in entry:
            override_size = entry[symbol]
            break

    if override_size is not None:
        if size < override_size:
            size = override_size
        else:
            size = round(size, 3)
    else:
        print(f"[ORDER_WARN] No preset ordersize for {symbol}; using calculated size")
        size = round(size, 3)

    # Ensure Bybit min notional (~5 USDT)
    def ensure_min_notional(qty, last_price, min_usdt=5.2):
        notional = float(qty) * float(last_price)
        if notional >= float(min_usdt):
            return qty, notional, False
        adj_qty = ceil(float(min_usdt) / max(1e-9, float(last_price)))
        return adj_qty, float(adj_qty) * float(last_price), True

    size, notional, adjusted = ensure_min_notional(size, ticker)

    # Fix quantity precision based on qtyStep requirements
    qty_step_01_symbols = ['XRP', 'DOT', 'UNI', 'SOL', 'LINK', 'FIL', 'EOS', 'APEX', 'BARD', 'ALPINE', 'WLD', 'SNX', 'BAND']  # qtyStep=0.1
    qty_step_1_symbols = ['ADA', 'DOGE', 'MATIC', 'XLM', 'XPL', 'SQD', 'FARTCOIN', 'MYX', 'ORDER', 'SOLV', 'AIA']  # qtyStep=1
    qty_step_10_symbols = ['PENGU', 'LINEA', 'BLESS']  # qtyStep=10
    qty_step_100_symbols = ['1000BONK']  # qtyStep=100

    if symbol in qty_step_01_symbols:
        # Round to 1 decimal place (qtyStep=0.1)
        size = round(float(size), 1)
        notional = float(size) * float(ticker)
        print(f"[QTY_FIX] {symbol} rounded to 1 decimal: {size}")
    elif symbol in qty_step_1_symbols:
        # Round to integer (qtyStep=1)
        size = int(round(float(size)))
        notional = float(size) * float(ticker)
        print(f"[QTY_FIX] {symbol} rounded to integer: {size}")
    elif symbol in qty_step_10_symbols:
        # Round to multiple of 10 (qtyStep=10)
        size = int(round(float(size) / 10) * 10)
        notional = float(size) * float(ticker)
        print(f"[QTY_FIX] {symbol} rounded to multiple of 10: {size}")
    elif symbol in qty_step_100_symbols:
        # Round to multiple of 100 (qtyStep=100)
        size = int(round(float(size) / 100) * 100)
        notional = float(size) * float(ticker)
        print(f"[QTY_FIX] {symbol} rounded to multiple of 100: {size}")

    print(f"[ORDER_CHECK] {symbol} {side} price={ticker} qty={size} notional={notional:.3f} adjusted={adjusted}")

    try:
        # Add Win/Loss orderLinkId prefix to distinguish from Portfolio orders
        order_link_id = f"WL-{symbol}-{int(time.time())}"
        order = client.LinearOrder.LinearOrder_new(side=side, symbol=symbol+"USDT", order_type="Market", qty=size,
                                           time_in_force="GoodTillCancel", reduce_only=False,
                                           close_on_trigger=False, order_link_id=order_link_id).result()
        print("[ORDER_OK]")
    except InvalidRequestError as e:
        print(f"[ORDER_FAIL] InvalidRequestError: {e}")
        return
    except Exception as e:
        print(f"[ORDER_FAIL] Unexpected: {e}")
        return

    #pprint(order)


def calculate_order(symbol, side):
    position = check_positions(symbol)
    if position != None:
        if position[0] == True:
            position = position[1]
            pnl = float(position['unrealised_pnl'])

            if pnl < 0:
                ticker = fetch_ticker(symbol)
                percent_change = ticker - float(position['entry_price'])
                pnl = (percent_change / ticker) * -100
                print("PNL %", symbol, (-1 * pnl))
                min_order = fetch_order_size(symbol)

                multipliers = load_multipliers(coins, symbol)
                size1 = (min_order * multipliers[0])
                size2 = (min_order * multipliers[1])
                size3 = (min_order * multipliers[2])
                size4 = (min_order * multipliers[3])

                dca = load_dca(coins, symbol)
                modifiers = load_dca_values(coins, symbol)
                print(min_order)

                print("Current Position Size for ", symbol, " = ", position['size'])
                if position['size'] <= size1:
                    size = min_order
                    place_order(symbol, side, ticker, size)
                elif size1 < position['size'] <= size2 and pnl > dca[0]:
                    size = min_order * modifiers[0]
                    place_order(symbol, side, ticker, size)
                elif size2 < position['size'] <= size3 and pnl > dca[1]:
                    size = min_order * modifiers[1]
                    place_order(symbol, side, ticker, size)
                elif size3 < position['size'] <= size4 and pnl > dca[2]:
                    size = min_order * modifiers[2]
                    place_order(symbol, side, ticker, size)
                elif size4 < position['size'] and pnl > dca[3]:
                    size = min_order * modifiers[3]
                    place_order(symbol, side, ticker, size)
                else:
                    print("At Max Size for ", symbol, " Tier or Not Outside Drawdown Settings..")

            else:
                print(symbol, "Position is currently in profit so we wont do anything here    :D")

        else:
            print("SEARCH FOR ME THIS SHOULD NOT HAPPEN GNOME LOL")

    else:
        print("No Open Position Found Yet")
        ticker = fetch_ticker(symbol)
        min_order = fetch_order_size(symbol)
        place_order(symbol, side, ticker, min_order)

def check_liquidations():
    binance_websocket_api_manager = BinanceWebSocketApiManager(exchange="binance.com-futures")
    binance_websocket_api_manager.create_stream(['!forceOrder'], [{}])
    cycles = 5000000
    nonce = 0

    while True:
        lick_stream = binance_websocket_api_manager.pop_stream_data_from_stream_buffer()

        #settings update script
        nonce += 1
        if nonce > cycles:
            load_jsons()
            nonce = 0

        if lick_stream:
            data = json.loads(lick_stream)
            #pprint(data)
            try:
                #data = {'stream': '!forceOrder@arr', 'data': {'e': 'forceOrder', 'E': 1629656323555, 'o': {'s': 'BTCUSDT', 'S': 'BUY', 'o': 'LIMIT', 'f': 'IOC', 'q': '6', 'p': '73.2212', 'ap': '80000', 'X': 'FILLED', 'l': '6', 'z': '6', 'T': 1629656323549}}}
                symbol = data['data']['o']['s'][:-4]
                symbols = load_symbols(coins)

                if symbol in symbols:
                    #pprint(data)
                    last = data['data']['o']['ap']
                    side = data['data']['o']['S']
                    amount = data['data']['o']['q']
                    stamp = data['data']['E']
                    lick_size = float(last) * float(amount)
                    d1 = datetime.fromtimestamp(stamp / 1000)
                    now = datetime.now()
                    past = now - d1
                    duration = past.total_seconds()

                    if duration < 5:
                        print("---------------------------------------------------------------------------------")
                        print("Liquidation found for:", amount, "Contracts worth: $", lick_size, "on ", symbol)

                        vwaps = fetch_vwap(symbol)
                        ticker = fetch_ticker(symbol)
                        lick_val = fetch_lickval(symbol)

                        if ticker < vwaps[1] and side == 'SELL' and lick_size > lick_val:
                            side = 'Buy'
                            calculate_order(symbol, side)
                        elif ticker > vwaps[2] and side == "BUY" and lick_size > lick_val:
                            side = 'Sell'
                            calculate_order(symbol, side)
                        else:
                            print("Does not Meet VWAP or Size Requirements")

                    else:
                        pass
                        #print("Lick timestamp to far away")

                else:
                    pass

            except KeyError:
                pass


load_jsons()

print("🚀 Launching Win/Loss Liquidation System (Live Mode)")
print("📋 Mode: Fast liquidation entries + Portfolio conflict avoidance")
print("⚡ Speed: Real-time liquidation detection and entry")
print()

if settings['check_leverage'].lower() == 'true':
    for coin in coins:
        print("Setting Leverage for ", coin['symbol']+'USDT', " before Starting Bot")
        set_leverage(coin['symbol'])

check_liquidations()


