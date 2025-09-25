import ccxt
import requests
from datetime import datetime
from time import sleep
import time
import json
import logging
from prettyprinter import pprint
import bybitwrapper

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

def load_symbols(coins):
    symbols = []
    for coin in coins:
        symbols.append(coin['symbol'])
    return symbols

def check_positions(symbol):
    positions = client.LinearPositions.LinearPositions_myPosition(symbol=symbol+"USDT").result()
    if positions[0]['ret_msg'] == 'OK':
        for position in positions[0]['result']:
            if position['entry_price'] > 0:
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

        print(f"[TP] setting for {symbol}: side={tp_side}, price={tp_price}")

        cancel = client.LinearOrder.LinearOrder_cancel(symbol=symbol + "USDT").result()
        order = client.LinearOrder.LinearOrder_new(side=tp_side, symbol=symbol + "USDT", order_type="Limit", qty=size,
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

        print(f"[SL] setting for {symbol}: side={sl_side}, triggerPrice={trigger_price}, direction={trigger_direction}")

        order = client.LinearConditional.LinearConditional_new(
            order_type="Limit",
            side=sl_side,
            symbol=symbol+"USDT",
            qty=size,
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

print("Starting Take Profit & Order Manager")
# Idempotency state: remember last side/size set time per symbol
LAST_STATE = {}
LAST_SET_TS = {}
IDEMPOTENCY_COOLDOWN_SEC = 45
while True:
    print("Checking for Positions.........")
    # Execute risk commands from command center BEFORE processing positions
    execute_risk_commands()

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
