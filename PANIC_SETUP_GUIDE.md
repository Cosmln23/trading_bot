# 🚨 Panic Button Setup Guide

## 📋 Overview

The Panic Button system provides emergency kill-switch functionality for your Bybit-Futures-Bot. With a single command or hotkey, it will:

1. **Disable Trading** - Stop all new signals
2. **Cancel All Orders** - Every pending order on all symbols
3. **Flatten All Positions** - Close everything with market orders
4. **Verify Clean State** - Ensure 100% closure
5. **Create Safety Lock** - Prevent accidental re-enabling
6. **Send Alerts** - Telegram notifications with full report

## 🚀 Quick Setup (3 Steps)

### Step 1: Install Dependencies

```bash
cd ~/Desktop/Bybit-Futures-Bot
pip install -r requirements_panic.txt
```

### Step 2: Configure Telegram (Optional but Recommended)

1. Create Telegram bot via [@BotFather](https://t.me/botfather)
2. Get your chat ID by messaging [@userinfobot](https://t.me/userinfobot)
3. Edit `config/panic.yaml`:

```yaml
alert:
  telegram:
    bot_token: "YOUR_BOT_TOKEN_HERE"
    chat_id: "YOUR_CHAT_ID_HERE"
```

### Step 3: Start the Server

```bash
python3 panic_server.py
```

✅ **Done!** The panic button is now active on `http://127.0.0.1:8787`

## 🎯 Usage Options

### Option 1: Via Claude (MCP Tools)

In Claude Code, you can now run:
- `panic_stop` - Execute emergency panic
- `panic_status` - Check system status
- `panic_reset` - Reset after verification

### Option 2: Via HTTP API

```bash
# Execute panic
curl -X POST http://127.0.0.1:8787/panic

# Check status
curl http://127.0.0.1:8787/panic/status

# Reset (after manual verification)
curl -X POST http://127.0.0.1:8787/panic/reset
```

### Option 3: Via System Hotkey

See `ops/hotkey/README.md` for platform-specific setup:
- **Windows:** AutoHotkey script (`panic_hotkey.ahk`)
- **Linux:** xbindkeys configuration
- **macOS:** Hammerspoon setup

Default hotkey: **Shift+T** (with confirmation)

## 📊 System Status

### Health Check

```bash
curl http://127.0.0.1:8787/healthz
```

### Response Example

```json
{
  "status": "healthy",
  "trading_enabled": true,
  "panic_tripped": false,
  "client_available": true
}
```

## 🔧 Configuration

Edit `config/panic.yaml` to customize:

```yaml
# Verification timeouts
verify:
  timeout_sec: 120      # Max wait for complete flatten
  poll_ms: 200          # Check interval
  max_retries: 10       # Retry attempts

# Server settings
http:
  port: 8787            # Change if port conflicts
  host: "127.0.0.1"     # Localhost only (secure)

# Rate limiting
backoff:
  initial_ms: 100       # Starting delay
  max_ms: 5000         # Maximum delay
  multiplier: 2.0       # Backoff multiplier
```

## 🧪 Testing (IMPORTANT)

### Before Going Live

1. **Test on Testnet:**
   - Change API keys to testnet in `settings.json`
   - Open small test positions
   - Execute panic and verify complete closure

2. **Test Telegram Alerts:**
   - Configure bot token and chat ID
   - Execute `panic_stop` via Claude
   - Confirm you receive formatted alerts

3. **Test Hotkey (if using):**
   - Install platform-specific hotkey system
   - Test status check first (`Ctrl+Alt+S`)
   - Test panic on testnet only

### Test Commands

```bash
# Check server is running
curl http://127.0.0.1:8787/healthz

# Test status (should show unlocked)
curl http://127.0.0.1:8787/panic/status

# Test panic on testnet (destructive!)
# curl -X POST http://127.0.0.1:8787/panic
```

## 🔒 Security & Safety

### Network Security
- Server only accepts localhost connections
- No external network access
- No authentication needed for local requests

### Safety Features
- **Idempotent:** Multiple panic triggers are safe
- **Atomic Operations:** Cancel → Close → Verify sequence
- **Safety Locks:** Cannot re-enable until manual verification
- **Comprehensive Logging:** Full audit trail with timing

### Emergency Access
If server fails:
1. Stop trading bots manually (`Ctrl+C`)
2. Use Bybit web interface to close positions
3. Verify via API or mobile app

## 📈 Integration with Existing Bot

The panic system integrates seamlessly:

### Automatic Integration
- Uses your existing `settings.json` for API keys
- Reads `coins.json` for symbol configuration
- Compatible with your current `bybitwrapper` setup
- Zero changes to existing trading logic

### Trading State Detection
- Monitors existing bot processes
- Respects current position management
- Works with both hedged and one-way modes

## 🚨 Execution Report

After panic execution, you'll receive:

### Telegram Alert Example
```
✅ PANIC BUTTON COMPLETED
Bot: Bybit-Futures-Bot
Time: 2025-01-25 12:34:56
─────────────────
✅ Orders canceled: 7
✅ Positions closed: 3
✅ Symbols: BTC, ETH, DOGE
⏱️ Duration: 8.67s
🔒 Status: LOCKED

Phase Timings:
✅ Disable Trading: 0.05s
✅ Cancel All: 2.30s
✅ Flatten All: 4.10s
✅ Verify Clean: 1.80s
✅ Arm Lock: 0.02s
✅ Send Alert: 0.40s
```

### JSON Response
```json
{
  "started_at": "2025-01-25T12:34:56Z",
  "ended_at": "2025-01-25T12:35:05Z",
  "success": true,
  "total_duration_sec": 8.67,
  "orders_canceled": 7,
  "positions_closed": 3,
  "symbols_touched": ["BTCUSDT", "ETHUSDT", "DOGEUSDT"],
  "phase_timings": {
    "disable_trading": 0.05,
    "cancel_all": 2.30,
    "flatten_all": 4.10,
    "verify_clean": 1.80,
    "arm_lock": 0.02,
    "send_alert": 0.40
  },
  "warnings": [],
  "locked": true
}
```

## 🔄 Reset Procedure

After panic execution, system is locked. To reset:

### Verification Steps
1. **Manually verify** all positions are closed
2. **Check** no pending orders remain
3. **Confirm** account balance is correct

### Reset Options

**Via Claude:**
```
Use MCP tool: panic_reset
```

**Via HTTP:**
```bash
curl -X POST http://127.0.0.1:8787/panic/reset
```

**Via Hotkey:**
```
Ctrl+Alt+R (with confirmation dialog)
```

### Safety Checks
Reset will fail if:
- Positions still exist
- Orders are still pending
- Account verification fails

## 📞 Support & Troubleshooting

### Common Issues

**Server won't start:**
- Check port 8787 isn't in use: `netstat -an | grep 8787`
- Verify Python dependencies: `pip install -r requirements_panic.txt`
- Check `settings.json` exists with valid API keys

**Hotkey not working:**
- Ensure AutoHotkey/xbindkeys is running
- Test manual curl command first
- Check for key conflicts

**Telegram alerts not sending:**
- Verify bot token and chat ID in `config/panic.yaml`
- Test bot with direct message
- Check internet connectivity

**API errors during panic:**
- Verify API keys have futures trading permissions
- Check Bybit API limits and restrictions
- Enable UNIFIED trading mode

### Debug Mode

Enable detailed logging in `config/panic.yaml`:

```yaml
logging:
  level: "DEBUG"
  file: "panic/logs/panic.log"
```

### Manual Recovery

If panic fails partially:
1. Check `panic/logs/panic.log` for errors
2. Manually close remaining positions via Bybit
3. Use `panic_reset` only after complete verification
4. Contact support with log files if needed

## 🎯 Production Deployment

### Final Checklist

- [ ] Tested thoroughly on testnet
- [ ] Telegram alerts working
- [ ] Hotkeys configured and tested
- [ ] Team members trained on usage
- [ ] Emergency procedures documented
- [ ] API keys have correct permissions
- [ ] Backup recovery methods established

### Monitoring

- Server health: `curl http://127.0.0.1:8787/healthz`
- Status checks: Regular `panic_status` via Claude
- Log monitoring: `tail -f panic/logs/panic.log`
- Telegram alerts: Test monthly

### Best Practices

1. **Use confirmation dialogs** for manual triggers
2. **Test monthly** on testnet to verify functionality
3. **Document procedures** for team members
4. **Monitor API limits** to avoid rate limiting
5. **Keep backups** of configuration files
6. **Review logs** after any panic execution

---

## ⚠️ Final Warning

This system will immediately close **ALL** positions and cancel **ALL** orders when triggered. It affects **REAL MONEY**.

- Only use in genuine emergency situations
- Always verify on testnet first
- Ensure team members understand the consequences
- Have manual backup procedures ready

**The panic button is a last resort - use it responsibly!**