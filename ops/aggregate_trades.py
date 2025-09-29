#!/usr/bin/env python3
"""
Aggregate trades from snapshots (and events) into a CSV for analysis.

Usage:
  python ops/aggregate_trades.py --date YYYY-MM-DD

Creates logs/trades/trades_YYYY-MM-DD.csv with columns:
  date_open, date_close, symbol, side, qty, entry_price, exit_price, pnl_usd, pnl_pct

Notes:
  - Uses logs/snapshots/YYYY-MM-DD.jsonl as the primary source
  - Simple heuristic: when size > 0 and previously 0 => open; when size == 0 and was > 0 => close
  - entry_price uses avgPrice at open; exit_price uses markPrice when size transitions to 0
  - If position size changes while open, the latest avgPrice is used (approximation)
"""

import argparse
import csv
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
SNAPDIR = ROOT / 'logs' / 'snapshots'
TRADEDIR = ROOT / 'logs' / 'trades'


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', help='YYYY-MM-DD (single day)')
    ap.add_argument('--days', type=int, help='Aggregate last N days (uses --end or today)')
    ap.add_argument('--end', help='End date YYYY-MM-DD for --days range (defaults to today)')
    return ap.parse_args()


def load_snapshots(day: str):
    path = SNAPDIR / f'{day}.jsonl'
    if not path.exists():
        return []
    rows = []
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                j = json.loads(line)
                rows.append(j)
            except Exception:
                pass
    # sort by timestamp
    rows.sort(key=lambda r: r.get('ts', ''))
    return rows


def aggregate(day: str):
    snaps = load_snapshots(day)
    if not snaps:
        print(f'No snapshots for {day}')
        return []

    open_positions = {}  # key: symbol -> dict(open_ts, side, qty, entry_price)
    trades = []

    for snap in snaps:
        ts = snap.get('ts')
        positions = snap.get('positions', []) or []
        seen = set()
        for p in positions:
            symbol = p.get('symbol', '')
            side = str(p.get('side', '')).lower()
            qty = float(p.get('size') or 0)
            avg = float(p.get('avgPrice') or 0)
            mark = float(p.get('markPrice') or 0)
            seen.add(symbol)

            # If newly opened
            if symbol not in open_positions and qty > 0:
                open_positions[symbol] = {
                    'date_open': ts,
                    'symbol': symbol,
                    'side': 'Buy' if side == 'buy' else 'Sell',
                    'qty': qty,
                    'entry_price': avg or mark,
                }
            # If changed while open, update approx entry/qty
            elif symbol in open_positions and qty > 0:
                op = open_positions[symbol]
                if qty != op['qty']:
                    op['qty'] = qty
                if avg:
                    op['entry_price'] = avg

        # Detect closes for symbols not seen in this snapshot but previously open
        to_close = []
        for symbol, op in open_positions.items():
            if symbol not in seen:
                # Closed between previous snapshot and now
                exit_price = op.get('entry_price', 0.0)  # fallback
                # Try to approximate with last snapshot's markPrice if available
                # Not perfect, but acceptable for rough analysis
                qty = op['qty']
                side = op['side']
                pnl_usd = 0.0
                if side == 'Buy':
                    pnl_usd = (exit_price - op['entry_price']) * qty
                else:
                    pnl_usd = (op['entry_price'] - exit_price) * qty
                pnl_pct = 0.0
                if op['entry_price'] > 0:
                    if side == 'Buy':
                        pnl_pct = (exit_price - op['entry_price']) / op['entry_price'] * 100
                    else:
                        pnl_pct = (op['entry_price'] - exit_price) / op['entry_price'] * 100
                trades.append({
                    'date_open': op['date_open'],
                    'date_close': ts,
                    'symbol': op['symbol'],
                    'side': op['side'],
                    'qty': f"{qty:.6f}",
                    'entry_price': f"{op['entry_price']:.6f}",
                    'exit_price': f"{exit_price:.6f}",
                    'pnl_usd': f"{pnl_usd:.6f}",
                    'pnl_pct': f"{pnl_pct:.3f}",
                })
                to_close.append(symbol)
        for s in to_close:
            open_positions.pop(s, None)

    return trades


def daterange_days(end_day: str | None, days: int):
    if end_day:
        end = datetime.strptime(end_day, '%Y-%m-%d').date()
    else:
        end = datetime.now(timezone.utc).date()
    out = []
    for i in range(days):
        d = end - timedelta(days=i)
        out.append(d.strftime('%Y-%m-%d'))
    out.reverse()
    return out


def save_trades(day: str, trades: list):
    TRADEDIR.mkdir(parents=True, exist_ok=True)
    path = TRADEDIR / f"trades_{day}.csv"
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=[
            'date_open', 'date_close', 'symbol', 'side', 'qty', 'entry_price', 'exit_price', 'pnl_usd', 'pnl_pct'
        ])
        w.writeheader()
        for t in trades:
            w.writerow(t)
    print(f"Saved {len(trades)} trades -> {path}")


def main():
    args = parse_args()
    if args.days and args.days > 0:
        days = daterange_days(args.end, args.days)
        all_trades = []
        for d in days:
            all_trades.extend(aggregate(d))
        if all_trades:
            start = days[0]
            end = days[-1]
            TRADEDIR.mkdir(parents=True, exist_ok=True)
            path = TRADEDIR / f"trades_{start}_to_{end}.csv"
            with open(path, 'w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=[
                    'date_open', 'date_close', 'symbol', 'side', 'qty', 'entry_price', 'exit_price', 'pnl_usd', 'pnl_pct'
                ])
                w.writeheader()
                for t in all_trades:
                    w.writerow(t)
            print(f"Saved {len(all_trades)} trades -> {path}")
        else:
            print('No trades in range')
    elif args.date:
        trades = aggregate(args.date)
        if trades:
            save_trades(args.date, trades)
    else:
        print('Provide --date YYYY-MM-DD or --days N [--end YYYY-MM-DD]')


if __name__ == '__main__':
    main()
