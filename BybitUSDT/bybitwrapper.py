#!/usr/bin/env python

import json
from typing import Any, Dict, List, Optional

try:
    # V5 unified trading client (preferred)
    from pybit.unified_trading import HTTP as UnifiedHTTP
    _HAS_UNIFIED = True
except Exception:
    # Older pybit fallback
    from pybit import HTTP as LegacyHTTP  # type: ignore
    _HAS_UNIFIED = False


class _ResponseWrapper:
    # Mimic bravado's .result() return style: (body, response)
    def __init__(self, body: Dict[str, Any]):
        self._body = body

    def result(self):
        return self._body, None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _map_order_status(status: Optional[str]) -> str:
    # Pass-through when unknown; scripts only check for 'Filled'/'Cancelled'
    return status or "New"


class _LinearPositions:
    def __init__(self, session):
        self._session = session

    def LinearPositions_myPosition(self, symbol: str):
        if _HAS_UNIFIED:
            r = self._session.get_positions(category="linear", symbol=symbol)
            ret_msg = r.get("retMsg", "")
            items = r.get("result", {}).get("list", []) or []
            positions: List[Dict[str, Any]] = []
            for p in items:
                positions.append({
                    "entry_price": _safe_float(p.get("avgPrice"), 0.0),
                    "size": _safe_float(p.get("size"), 0.0),
                    "side": p.get("side"),
                })
            body = {"ret_msg": ret_msg, "result": positions}
            return _ResponseWrapper(body)
        else:
            # Legacy pybit: attempt to use linear endpoint
            r = self._session.my_position(symbol=symbol)
            positions: List[Dict[str, Any]] = []
            for p in r.get("result", []) or []:
                positions.append({
                    "entry_price": _safe_float(p.get("entry_price"), 0.0),
                    "size": _safe_float(p.get("size"), 0.0),
                    "side": p.get("side"),
                })
            return _ResponseWrapper({"ret_msg": r.get("ret_msg", ""), "result": positions})

    def LinearPositions_saveLeverage(self, symbol: str, buy_leverage: Any, sell_leverage: Any):
        if _HAS_UNIFIED:
            self._session.set_leverage(
                category="linear",
                symbol=symbol,
                buyLeverage=str(buy_leverage),
                sellLeverage=str(sell_leverage),
            )
            return _ResponseWrapper({"ret_msg": "OK"})
        else:
            r = self._session.set_leverage(symbol=symbol, buy_leverage=buy_leverage, sell_leverage=sell_leverage)
            return _ResponseWrapper({"ret_msg": r.get("ret_msg", "")})


class _Wallet:
    def __init__(self, session):
        self._session = session

    def Wallet_getBalance(self, coin: str = "USDT"):
        balance_val = 0.0
        if _HAS_UNIFIED:
            r = self._session.get_wallet_balance(accountType="UNIFIED", coin=coin)
            # Try multiple shapes
            lst = (r.get("result", {}) or {}).get("list", [])
            for acct in lst:
                for c in acct.get("coin", []) or []:
                    if c.get("coin") == coin:
                        balance_val = _safe_float(c.get("walletBalance")) or _safe_float(c.get("equity"))
                        break
        else:
            r = self._session.get_wallet_balance(coin=coin)
            try:
                balance_val = _safe_float(r.get("result", {}).get(coin, {}).get("wallet_balance"), 0.0)
            except Exception:
                balance_val = 0.0

        body = {"result": {coin: {"wallet_balance": balance_val}}}
        return _ResponseWrapper(body)


class _LinearOrder:
    def __init__(self, session):
        self._session = session

    def _map_time_in_force(self, tif: Optional[str]) -> Optional[str]:
        if tif is None:
            return None
        mapping = {
            "GoodTillCancel": "GTC",
            "ImmediateOrCancel": "IOC",
            "FillOrKill": "FOK",
            # accept already-short codes as-is
            "GTC": "GTC",
            "IOC": "IOC",
            "FOK": "FOK",
            "PostOnly": "PostOnly",
        }
        return mapping.get(tif, tif)

    def LinearOrder_new(
        self,
        side: str,
        symbol: str,
        order_type: str,
        qty: Any,
        time_in_force: str = "GoodTillCancel",
        reduce_only: bool = False,
        close_on_trigger: bool = False,
        price: Optional[Any] = None,
    ):
        if _HAS_UNIFIED:
            tif = self._map_time_in_force(time_in_force)
            params: Dict[str, Any] = {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": str(qty),
                "timeInForce": tif,
                "reduceOnly": reduce_only,
                "closeOnTrigger": close_on_trigger,
            }
            if order_type == "Limit" and price is not None:
                params["price"] = str(price)
            r = self._session.place_order(**params)
            return _ResponseWrapper({"ret_msg": r.get("retMsg", "OK"), "result": r.get("result")})
        else:
            r = self._session.place_active_order(
                symbol=symbol,
                side=side,
                order_type=order_type,
                qty=qty,
                price=price,
                time_in_force=time_in_force,
                reduce_only=reduce_only,
                close_on_trigger=close_on_trigger,
            )
            return _ResponseWrapper({"ret_msg": r.get("ret_msg", "")})

    def LinearOrder_getOrders(self, symbol: str, limit: Any = 5):
        data: List[Dict[str, Any]] = []
        if _HAS_UNIFIED:
            r = self._session.get_open_orders(category="linear", symbol=symbol)
            for o in (r.get("result", {}) or {}).get("list", []) or []:
                data.append({
                    "qty": _safe_float(o.get("qty"), 0.0),
                    "order_status": _map_order_status(o.get("orderStatus")),
                    "order_id": o.get("orderId"),
                })
        else:
            r = self._session.get_active_order(symbol=symbol, limit=limit)
            for o in r.get("result", {}).get("data", []) or []:
                data.append({
                    "qty": _safe_float(o.get("qty"), 0.0),
                    "order_status": _map_order_status(o.get("order_status")),
                    "order_id": o.get("order_id"),
                })
        return _ResponseWrapper({"result": {"data": data}})

    def LinearOrder_cancel(self, symbol: str, order_id: Optional[str] = None):
        if _HAS_UNIFIED:
            if order_id:
                self._session.cancel_order(category="linear", symbol=symbol, orderId=order_id)
            else:
                self._session.cancel_all_orders(category="linear", symbol=symbol)
            return _ResponseWrapper({"ret_msg": "OK"})
        else:
            if order_id:
                r = self._session.cancel_active_order(symbol=symbol, order_id=order_id)
            else:
                r = self._session.cancel_all_active_orders(symbol=symbol)
            return _ResponseWrapper({"ret_msg": r.get("ret_msg", "")})


class _LinearConditional:
    def __init__(self, session):
        self._session = session

    def _map_time_in_force(self, tif: Optional[str]) -> Optional[str]:
        if tif is None:
            return None
        mapping = {
            "GoodTillCancel": "GTC",
            "ImmediateOrCancel": "IOC",
            "FillOrKill": "FOK",
            "GTC": "GTC",
            "IOC": "IOC",
            "FOK": "FOK",
            "PostOnly": "PostOnly",
        }
        return mapping.get(tif, tif)

    def LinearConditional_getOrders(self, symbol: str, limit: Any = 5):
        data: List[Dict[str, Any]] = []
        if _HAS_UNIFIED:
            r = self._session.get_open_orders(category="linear", symbol=symbol, orderFilter="StopOrder")
            for o in (r.get("result", {}) or {}).get("list", []) or []:
                data.append({
                    "order_status": _map_order_status(o.get("orderStatus")),
                    "stop_order_id": o.get("orderId"),
                })
        else:
            r = self._session.query_conditional_order(symbol=symbol, limit=limit)
            for o in r.get("result", {}).get("data", []) or []:
                data.append({
                    "order_status": _map_order_status(o.get("order_status")),
                    "stop_order_id": o.get("stop_order_id"),
                })
        return _ResponseWrapper({"result": {"data": data}})

    def LinearConditional_cancel(self, symbol: str, stop_order_id: str):
        if _HAS_UNIFIED:
            self._session.cancel_order(category="linear", symbol=symbol, orderId=stop_order_id)
            return _ResponseWrapper({"ret_msg": "OK"})
        else:
            r = self._session.cancel_conditional_order(symbol=symbol, stop_order_id=stop_order_id)
            return _ResponseWrapper({"ret_msg": r.get("ret_msg", "")})

    def LinearConditional_new(
        self,
        order_type: str,
        side: str,
        symbol: str,
        qty: Any,
        price: Any,
        base_price: Any,
        stop_px: Any,
        time_in_force: str = "GoodTillCancel",
        reduce_only: bool = False,
        trigger_by: str = "LastPrice",
        close_on_trigger: bool = False,
    ):
        if _HAS_UNIFIED:
            tif = self._map_time_in_force(time_in_force)
            # Derive triggerDirection: 1 = rise to trigger, 2 = fall to trigger
            try:
                base_val = float(base_price)
                stop_val = float(stop_px)
                trigger_direction = 1 if stop_val >= base_val else 2
            except Exception:
                trigger_direction = None

            params: Dict[str, Any] = {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": str(qty),
                "price": str(price),
                "timeInForce": tif,
                "reduceOnly": reduce_only,
                "closeOnTrigger": close_on_trigger,
                "orderFilter": "StopOrder",
                "triggerPrice": str(stop_px),
                "triggerBy": trigger_by,
            }
            if trigger_direction is not None:
                params["triggerDirection"] = trigger_direction
            self._session.place_order(**params)
            return _ResponseWrapper({"ret_msg": "OK"})
        else:
            r = self._session.place_conditional_order(
                order_type=order_type,
                side=side,
                symbol=symbol,
                qty=qty,
                price=price,
                base_price=base_price,
                stop_px=stop_px,
                time_in_force=time_in_force,
                reduce_only=reduce_only,
                trigger_by=trigger_by,
                close_on_trigger=close_on_trigger,
            )
            return _ResponseWrapper({"ret_msg": r.get("ret_msg", "")})


class _Symbol:
    def __init__(self, session):
        self._session = session

    def Symbol_get(self):
        if _HAS_UNIFIED:
            r = self._session.get_instruments_info(category="linear")
            out: List[Dict[str, Any]] = []
            for itm in (r.get("result", {}) or {}).get("list", []) or []:
                out.append({
                    "name": itm.get("symbol"),
                    "price_filter": {"tick_size": str((itm.get("priceFilter", {}) or {}).get("tickSize", "0.001"))},
                })
            return _ResponseWrapper({"result": out})
        else:
            r = self._session.query_symbol()
            return _ResponseWrapper({"result": r.get("result", [])})


class _ClientCompat:
    def __init__(self, session):
        self._session = session
        self.LinearPositions = _LinearPositions(session)
        self.Wallet = _Wallet(session)
        self.LinearOrder = _LinearOrder(session)
        self.LinearConditional = _LinearConditional(session)
        self.Symbol = _Symbol(session)


def bybit(test: bool = True, config: Optional[Dict[str, Any]] = None, api_key: Optional[str] = None, api_secret: Optional[str] = None):
    # Create pybit session using V5 unified trading when available
    if _HAS_UNIFIED:
        session = UnifiedHTTP(testnet=test, api_key=api_key, api_secret=api_secret)
    else:
        # Legacy fallback
        session = LegacyHTTP(endpoint="https://api-testnet.bybit.com" if test else "https://api.bybit.com", api_key=api_key, api_secret=api_secret)
    return _ClientCompat(session)