# Risk Guard Setup Instructions

## Overview
Risk Guard protects your Bybit UNIFIED account from margin calls by monitoring Initial Margin (IM) utilization and automatically:
- **60-70%**: Alert mode
- **70-80%**: Cancel orders + close positions to reach 60%
- **80-90%**: Emergency deleverage to 58%
- **≥90%**: Hard stop - close everything

## Quick Start

### 1. Set Environment Variables (Required)

**Windows PowerShell:**
```powershell
$env:BYBIT_API_KEY="your_api_key_here"
$env:BYBIT_API_SECRET="your_api_secret_here"
$env:BYBIT_TESTNET="false"
```

**Linux/Mac:**
```bash
export BYBIT_API_KEY="your_api_key_here"
export BYBIT_API_SECRET="your_api_secret_here"
export BYBIT_TESTNET="false"
```

### 2. Install Dependencies (if not already installed)
```bash
pip install pybit
```

### 3. Test First (DRY RUN)
```bash
python risk_guard.py
```

Edit `risk_guard.py` line 281: Change `dry_run=False` to `dry_run=True` for testing.

### 4. Run for Real
Change back to `dry_run=False` and run:
```bash
python risk_guard.py
```

## Current Status Alert
**You are at 71.32% IM utilization** - Risk Guard will immediately:
1. Start in **DERISK mode** (70-80% range)
2. Cancel all pending orders
3. Begin closing positions to reduce to 60%
4. Block new entries via flag system

## File Integration

### Kill-Switch System
Risk Guard creates `risk_flag.json` with current state:
```json
{
  "allow_new_entries": false,
  "trading_enabled": true,
  "last_utilization": 0.7132,
  "timestamp": "2025-01-25T..."
}
```

### Liquidation Bot Integration
Modified `liquidation_ws.py` now checks risk flag before placing orders:
- If `allow_new_entries = false` → skips new entries
- Logs: `[RISK-GUARD] New entries disabled - skipping BTCUSDT Buy order`

## Monitoring

### Console Output
```
[UTIL] Total: 22.67 | Used IM: 16.17 | Free: 6.50 | Utilization: 71.3%
[DERISK] Utilization 71.3% in 70-80% range - REDUCING EXPOSURE TO 60%
[CANCEL] All orders cancelled for BTCUSDT
[CLOSE] BTCUSDT Sell 0.001 (lev:3.0, LOSS)
[DERISK] BTCUSDT freed ~2.15 USDT IM, remaining excess: ~0.85
```

### Risk Thresholds Explained
- **<60%**: Normal trading
- **60-70%**: Warning (recommend smaller orders)
- **70-80%**: Active deleverage (no new entries)
- **80-90%**: Emergency closing (aggressive)
- **≥90%**: Hard stop (close everything)

## Running Alongside Your Bots

### Current Setup
1. **profit.py** - TP/SL manager (unchanged)
2. **liquidation_ws.py** - Entry orders (now with risk flag check)
3. **risk_guard.py** - NEW - Risk protection

### Start All 3 Processes

**Terminal/PowerShell 1:**
```bash
cd BybitUSDT
python profit.py
```

**Terminal/PowerShell 2:**
```bash
cd BybitUSDT
python liquidation_ws.py
```

**Terminal/PowerShell 3:**
```bash
python risk_guard.py
```

## Emergency Manual Override

### Stop Risk Guard
```
Ctrl+C in risk_guard terminal
```

### Force Allow New Entries (Emergency Only)
Edit/delete `risk_flag.json`:
```json
{"allow_new_entries": true}
```

### Manual Position Close (if needed)
```python
# In Python console
from pybit.unified_trading import HTTP
client = HTTP(api_key="...", api_secret="...")

# Close 50% of BTCUSDT long position
client.place_order(
    category="linear",
    symbol="BTCUSDT",
    side="Sell",
    orderType="Market",
    qty="0.001",  # adjust quantity
    reduceOnly=True
)
```

## Troubleshooting

### API Permission Error
- Ensure API key has futures trading permissions
- Check UNIFIED account is enabled

### File Permission Error
- Run from project root directory
- Check `risk_flag.json` can be created/written

### Network Issues
- Risk Guard polls every 5 seconds
- Temporary API failures are logged but don't stop the guard

### Position Not Closing
- Check symbol format (must be exact: "BTCUSDT")
- Verify position size in console output
- Manual close via Bybit UI if needed

## Support

If Risk Guard stops unexpectedly:
1. Check console for error messages
2. Verify API keys are correct
3. Ensure internet connectivity
4. Restart with dry_run=True to test