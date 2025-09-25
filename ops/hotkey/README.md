# Panic Button Hotkey Setup

## 🎯 Overview

Configure a system-wide hotkey (Shift+T or Ctrl+Alt+Shift+T) that instantly triggers the panic button via HTTP request to the local server.

## ⚠️ Safety First

**IMPORTANT:** The hotkey will immediately:
- Disable all trading
- Cancel ALL orders on ALL symbols
- Close ALL positions with market orders
- Lock the system until manual reset

**Only use in genuine emergency situations!**

## 🪟 Windows Setup (AutoHotkey)

### 1. Install AutoHotkey

Download and install from: https://www.autohotkey.com/

### 2. Create Panic Hotkey Script

Create file: `panic_hotkey.ahk`

```autohotkey
; Panic Button Hotkey for Bybit-Futures-Bot
; Shift+T triggers emergency panic procedure

#NoEnv
#SingleInstance Force

; Configuration
PANIC_URL := "http://127.0.0.1:8787/panic"
CURL_PATH := "curl.exe"  ; Assumes curl is in PATH

; Shift+T hotkey (use with caution!)
+t::
    ; Show confirmation dialog for safety
    MsgBox, 4, Panic Button Confirmation,
    (
    🚨 EMERGENCY PANIC BUTTON 🚨

    This will immediately:
    • Stop all trading
    • Cancel ALL orders
    • Close ALL positions
    • Lock the system

    Are you sure you want to continue?
    )

    IfMsgBox Yes
    {
        ; Execute panic request
        TrayTip, Panic Button, 🚨 Executing emergency panic procedure..., 3
        RunWait, %CURL_PATH% -X POST %PANIC_URL%, , Hide

        ; Show completion notification
        TrayTip, Panic Button, ✅ Panic procedure triggered. Check Telegram for results., 5
    }
    else
    {
        TrayTip, Panic Button, ❌ Panic cancelled by user., 2
    }
return

; Alternative: Ctrl+Alt+Shift+T (safer combination)
^!+t::
    TrayTip, Panic Button, 🚨 Emergency panic triggered (no confirmation)!, 2
    RunWait, %CURL_PATH% -X POST %PANIC_URL%, , Hide
    TrayTip, Panic Button, ✅ Emergency panic executed., 5
return

; Status check: Ctrl+Alt+S
^!s::
    TrayTip, Panic Button, 📊 Checking panic status..., 1
    RunWait, %CURL_PATH% -s http://127.0.0.1:8787/panic/status, , Hide
return

; Help: Display available hotkeys
F1::
    MsgBox, 0, Panic Button Hotkeys,
    (
    🔥 PANIC BUTTON HOTKEYS:

    Shift+T          = Panic with confirmation
    Ctrl+Alt+Shift+T = Instant panic (no confirmation)
    Ctrl+Alt+S       = Check status
    F1               = Show this help

    ⚠️ Use responsibly - these affect real money!
    )
return
```

### 3. Run the Script

1. Double-click `panic_hotkey.ahk`
2. AutoHotkey icon appears in system tray
3. Hotkeys are now active

### 4. Auto-Start on Boot (Optional)

1. Press `Win+R`, type `shell:startup`
2. Copy `panic_hotkey.ahk` to the startup folder

## 🐧 Linux Setup (with xbindkeys)

### 1. Install xbindkeys and curl

```bash
sudo apt install xbindkeys curl
```

### 2. Create Configuration

Create `~/.xbindkeysrc`:

```bash
# Panic Button Hotkey Configuration
# Shift+T = Panic with confirmation

"notify-send 'Panic Button' '🚨 Confirm panic in terminal' && gnome-terminal -- bash -c 'read -p \"Execute PANIC BUTTON? (y/N): \" confirm && [[ \$confirm == [yY] ]] && curl -X POST http://127.0.0.1:8787/panic || echo \"Cancelled\"'"
    Shift + t

# Ctrl+Alt+Shift+T = Instant panic (no confirmation)
"curl -X POST http://127.0.0.1:8787/panic && notify-send 'Panic Button' '✅ Emergency panic executed'"
    Control+Alt+Shift + t

# Ctrl+Alt+S = Status check
"curl -s http://127.0.0.1:8787/panic/status | jq '.summary' | xargs notify-send 'Panic Status'"
    Control+Alt + s
```

### 3. Start xbindkeys

```bash
xbindkeys
```

To auto-start, add to your `~/.bashrc` or `~/.profile`:

```bash
xbindkeys
```

## 🍎 macOS Setup (with Hammerspoon)

### 1. Install Hammerspoon

Download from: https://www.hammerspoon.org/

### 2. Create Configuration

Edit `~/.hammerspoon/init.lua`:

```lua
-- Panic Button Hotkey Configuration

-- Configuration
local PANIC_URL = "http://127.0.0.1:8787/panic"
local STATUS_URL = "http://127.0.0.1:8787/panic/status"

-- Shift+T = Panic with confirmation
hs.hotkey.bind({"shift"}, "t", function()
    local choice = hs.dialog.blockAlert(
        "🚨 PANIC BUTTON CONFIRMATION",
        "This will immediately:\n• Stop all trading\n• Cancel ALL orders\n• Close ALL positions\n• Lock the system\n\nAre you sure?",
        "Execute Panic", "Cancel"
    )

    if choice == "Execute Panic" then
        hs.notify.new({title="Panic Button", informativeText="🚨 Executing emergency procedure..."}):send()

        local task = hs.task.new("/usr/bin/curl", function(exitCode, stdOut, stdErr)
            if exitCode == 0 then
                hs.notify.new({title="Panic Button", informativeText="✅ Panic procedure triggered"}):send()
            else
                hs.notify.new({title="Panic Button", informativeText="❌ Panic failed: " .. stdErr}):send()
            end
        end, {"-X", "POST", PANIC_URL})

        task:start()
    else
        hs.notify.new({title="Panic Button", informativeText="❌ Panic cancelled"}):send()
    end
end)

-- Ctrl+Alt+Shift+T = Instant panic
hs.hotkey.bind({"ctrl", "alt", "shift"}, "t", function()
    hs.notify.new({title="Panic Button", informativeText="🚨 Emergency panic executing!"}):send()

    local task = hs.task.new("/usr/bin/curl", function(exitCode, stdOut, stdErr)
        if exitCode == 0 then
            hs.notify.new({title="Panic Button", informativeText="✅ Emergency panic completed"}):send()
        else
            hs.notify.new({title="Panic Button", informativeText="❌ Emergency panic failed"}):send()
        end
    end, {"-X", "POST", PANIC_URL})

    task:start()
end)

-- Ctrl+Alt+S = Status check
hs.hotkey.bind({"ctrl", "alt"}, "s", function()
    local task = hs.task.new("/usr/bin/curl", function(exitCode, stdOut, stdErr)
        if exitCode == 0 then
            hs.notify.new({title="Panic Status", informativeText="Check terminal for details"}):send()
            print("Panic Status:", stdOut)
        end
    end, {"-s", STATUS_URL})

    task:start()
end)

hs.notify.new({title="Panic Button", informativeText="🔥 Hotkeys loaded successfully"}):send()
```

### 3. Reload Configuration

Press `Ctrl+Alt+Cmd+R` or restart Hammerspoon.

## 🧪 Testing Setup

### 1. Test Server Connection

```bash
# Check server is running
curl http://127.0.0.1:8787/healthz

# Check panic status (should show unlocked)
curl http://127.0.0.1:8787/panic/status
```

### 2. Test Hotkey (Safe)

1. Make sure server is running: `python3 panic_server.py`
2. Configure Telegram bot (optional for testing)
3. Test status hotkey first (`Ctrl+Alt+S`)
4. Only test panic hotkey on testnet or with no positions!

### 3. Verify Hotkey Response

Expected flow:
1. Press hotkey → Confirmation dialog (if configured)
2. Confirm → HTTP request sent to localhost:8787
3. Panic procedure executes → Telegram alert sent
4. System locked until manual reset

## 🛡️ Security Considerations

### Network Security

- Server only accepts connections from localhost (127.0.0.1)
- No external access possible
- No authentication needed for local requests

### Hotkey Safety

- Consider using confirmation dialog for accidental presses
- Use complex key combinations (Ctrl+Alt+Shift+T)
- Document the hotkeys clearly for team members

### Emergency Access

If panic server is not running:
1. Manual Bybit interface → close positions
2. Stop trading bots directly (Ctrl+C)
3. Check positions/orders via Bybit web interface

## 🔧 Troubleshooting

### Hotkey Not Working

1. Check if AutoHotkey/xbindkeys/Hammerspoon is running
2. Verify curl is installed and in PATH
3. Test manual curl command first
4. Check for key conflicts with other applications

### Server Connection Failed

1. Verify panic server is running: `python3 panic_server.py`
2. Check port 8787 is not blocked by firewall
3. Test manual connection: `curl http://127.0.0.1:8787/healthz`

### Permission Issues (Linux)

```bash
# Make sure user can execute curl
which curl

# Check xbindkeys permissions
xbindkeys -n  # Test mode
```

## 📋 Quick Reference

| Hotkey | Action | Confirmation |
|--------|--------|--------------|
| `Shift+T` | Panic procedure | Yes |
| `Ctrl+Alt+Shift+T` | Instant panic | No |
| `Ctrl+Alt+S` | Status check | No |
| `F1` | Help dialog | No |

## 🚨 Emergency Procedures

If hotkey fails or server is down:

1. **Immediate:** Stop all trading bots (`Ctrl+C` in terminals)
2. **Manual:** Log into Bybit → Close all positions manually
3. **Verify:** Check all positions are closed
4. **Alert:** Notify team via Telegram/Discord

Remember: The hotkey is for emergencies only. In normal situations, use the regular bot controls or MCP tools via Claude.