% AGENTS Guide – Bybit Futures Bot

This document gives agents a precise picture of how the project works now, what was changed recently, and how to operate safely without disrupting live trading.

**Project Overview**
- Win/Loss engine: `BybitUSDT/liquidation_ws.py`
  - Listens to Binance liquidations and places entries on Bybit with VWAP offsets.
  - Enforces min notional and symbol-specific qty step.
  - Skips symbols managed by the Portfolio system (anti-conflict).
  - New: IM% guard blocks new entries if risk is elevated.
- Profit & Risk manager: `BybitUSDT/profit.py`
  - Manages TP/SL for Win/Loss positions using the exact position size (prevents Bybit error 110017).
  - New: Daily control (+10% target, -5% stop) – closes all and disables trading for the day.
  - New: IM% monitor – warns >80%, auto-reduces 20% exposure >100%.
  - New: CSV logging of daily PnL (`pnl_log.csv`) and daily state (`state/daily_pnl.json`).
- Portfolio Momentum: `BybitUSDT/portfolio_manager.py`
  - Momentum entries at 1x, budget control, trailing stop, pyramiding.
  - New: Allowlist hot‑reload each scan (no restart needed).
- Panic Button HTTP server: `panic_server.py` (+ `panic/`)
  - `POST /panic`: cancel all orders, close all positions, verify, lock.
  - `POST /panic/reset`: safe reset only when flat.
  - Access allowed only from `127.0.0.1` by default.
- Telegram control: `telegram_bot_control.py`
  - `/status`, `/kill`, `/close`, `/help`.
  - Improved process detection (files and modules; uvicorn panic server).
  - `/close` prefers Panic Server; fallback closes directly via Bybit V5 reduceOnly (requires `pybit`).
- Beginner docs: `BEGINNER_GUIDE.md` (Romanian) – full setup and usage.

**Changes Made (This Session)**
1) Risk config
- `settings.json`: set `risk_management.daily_target_pct = 10` and `risk_management.equity_usdt = 350` (daily stop remains -5%).
2) Profit manager (`BybitUSDT/profit.py`)
- Added Telegram alerts (reads `config/panic.yaml`).
- Daily baseline equity in UTC; computes daily PnL%, logs to `pnl_log.csv`.
- Enforces daily stop at +10% and -5%: flattens (reduceOnly) and writes `trading_disabled.flag`.
- IM% monitoring: warn >80%, reduce 20% exposure >100% with cooldowns.
- Helpers for safe reduceOnly closes with qty rounding per symbol group.
3) Win/Loss engine (`BybitUSDT/liquidation_ws.py`)
- Added `compute_im_percent()` and pre‑entry IM% guard: skip entries if IM%>80 (warn) or >100 (block).
4) Portfolio Momentum (`BybitUSDT/portfolio_manager.py`)
- Hot‑reload `allowlist_updated.json` every scan; logs added/removed symbols.
5) Telegram control (`panic/telegram_control.py`)
- Process detection improved to find: `BybitUSDT.portfolio_manager`, `panic.server`/uvicorn.
- `/close` fallback uses Bybit V5 reduceOnly with `positionIdx` and a retry without it.
6) Docs
- Added `BEGINNER_GUIDE.md` in Romanian.

**Live Editing vs Restart**
- Live (no restart):
  - Portfolio allowlist (`allowlist_updated.json`) – reloads at next scan (default 300s).
  - Panic/Telegram: `/status`, `/close`, `/kill` work without changes.
- Restart needed (current implementation):
  - Win/Loss (`liquidation_ws.py`) – if `coins.json` or `settings.json` change.
  - Profit manager (`profit.py`) – if `settings.json` or `coins.json` change.
  - Note: mtime-based hot‑reload can be added on request.

**Operational Notes**
- Use the repository venv so `pybit` is available (needed by Telegram `/close` fallback and wrappers).
- Error 110017 (reduceOnly same side) is mitigated: exact position size + correct close side + qty step rounding.
- Conflict avoidance: WL skips PM-managed symbols; Profit avoids touching PM-managed positions.
- Panic integration: logic respects `state/panic.lock` and `trading_disabled.flag`.

**File Pointers**
- Win/Loss: `BybitUSDT/liquidation_ws.py`
- Profit & Risk: `BybitUSDT/profit.py`
- Portfolio (hot‑reload): `BybitUSDT/portfolio_manager.py`
- Panic server: `panic/server.py`, `panic_server.py`
- Telegram: `panic/telegram_control.py`, `telegram_bot_control.py`
- Global settings: `settings.json`
- Per‑symbol config: `coins.json`
- Allowlist (PM): `allowlist_updated.json`

**Suggested Next Steps**
- Optional hot‑reload for WL/Profit configs (`coins.json`, `settings.json`).
- Add tests for qty rounding and IM% thresholds.
- Consider removing Binance dependency for prices if needed.

**Security**
- Keep API keys private; do not commit them.
- Panic API restricted to localhost by default; do not expose publicly.

