#!/usr/bin/env python3
"""
Telegram Bot Control for Remote Bot Management
Allows killing all trading bots via Telegram commands.
"""

import asyncio
import aiohttp
import json
import subprocess
import signal
import os
import time
from typing import Dict, Any
from datetime import datetime
from pathlib import Path
import sys

class TelegramBotControl:
    """Handles Telegram commands for bot control."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}"

    async def send_message(self, message: str):
        """Send message to Telegram chat."""
        url = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        print(f"[TELEGRAM] Message sent successfully")
                    else:
                        result = await response.text()
                        print(f"[TELEGRAM] Error: {response.status} - {result}")
        except Exception as e:
            print(f"[TELEGRAM] Exception: {e}")

    def get_bot_processes(self) -> Dict[str, list]:
        """Get all running bot processes."""
        processes = {
            "risk_guard": [],
            "profit": [],
            "liquidation": [],
            "panic_server": [],
            "portfolio": []
        }

        try:
            # Get all python processes
            result = subprocess.run(
                ['ps', 'aux'],
                capture_output=True,
                text=True
            )

            for line in result.stdout.split('\n'):
                if 'python' in line:
                    if 'risk_guard' in line:
                        pid = line.split()[1]
                        processes["risk_guard"].append(pid)
                    elif 'profit.py' in line:
                        pid = line.split()[1]
                        processes["profit"].append(pid)
                    elif 'liquidation_ws.py' in line or 'liquidation.py' in line:
                        pid = line.split()[1]
                        processes["liquidation"].append(pid)
                    elif 'portfolio_manager.py' in line:
                        pid = line.split()[1]
                        processes["portfolio"].append(pid)
                    elif 'panic_server' in line:
                        pid = line.split()[1]
                        processes["panic_server"].append(pid)
                    elif 'telegram_bot_control.py' in line:
                        # Don't kill the telegram control bot itself
                        pass

        except Exception as e:
            print(f"[CONTROL] Error getting processes: {e}")

        return processes

    def kill_bot_processes(self) -> Dict[str, Any]:
        """Kill all bot processes."""
        result = {
            "killed": {},
            "errors": [],
            "total_killed": 0
        }

        processes = self.get_bot_processes()

        for bot_type, pids in processes.items():
            result["killed"][bot_type] = []

            for pid in pids:
                try:
                    # Send SIGTERM first (graceful shutdown)
                    os.kill(int(pid), signal.SIGTERM)
                    result["killed"][bot_type].append(pid)
                    result["total_killed"] += 1
                    print(f"[CONTROL] Killed {bot_type} process {pid}")

                except ProcessLookupError:
                    print(f"[CONTROL] Process {pid} already dead")
                except Exception as e:
                    error_msg = f"Error killing {bot_type} {pid}: {str(e)}"
                    result["errors"].append(error_msg)
                    print(f"[CONTROL] {error_msg}")

        # Wait a moment, then force kill any remaining
        time.sleep(2)

        # Force kill any stubborn processes
        for bot_type, pids in processes.items():
            for pid in pids:
                try:
                    # Check if still running
                    os.kill(int(pid), 0)  # Doesn't actually kill, just checks
                    # Still running, force kill
                    os.kill(int(pid), signal.SIGKILL)
                    print(f"[CONTROL] Force killed {bot_type} process {pid}")
                except ProcessLookupError:
                    # Already dead, good
                    pass
                except Exception as e:
                    print(f"[CONTROL] Force kill error: {e}")

        return result

    def get_status_report(self) -> str:
        """Get current status of all bots."""
        processes = self.get_bot_processes()

        status_lines = [
            "🤖 <b>Bot Status Report</b>",
            f"📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "─────────────────"
        ]

        for bot_type, pids in processes.items():
            emoji = "✅" if pids else "❌"
            bot_name = bot_type.replace('_', ' ').title()
            count = len(pids)

            if count > 0:
                status_lines.append(f"{emoji} {bot_name}: {count} process(es) running")
            else:
                status_lines.append(f"{emoji} {bot_name}: Not running")

        return "\n".join(status_lines)

    async def handle_kill_command(self):
        """Handle kill all bots command."""
        # Send confirmation message
        await self.send_message("🚨 <b>KILLING ALL BOTS...</b>\n\nStopping all trading processes...")

        # Kill processes
        result = self.kill_bot_processes()

        # Prepare result message
        if result["total_killed"] > 0:
            message_lines = [
                "✅ <b>BOTS STOPPED SUCCESSFULLY</b>",
                f"📊 Total processes killed: {result['total_killed']}",
                "─────────────────"
            ]

            for bot_type, pids in result["killed"].items():
                if pids:
                    bot_name = bot_type.replace('_', ' ').title()
                    message_lines.append(f"🔴 {bot_name}: {len(pids)} stopped")

            if result["errors"]:
                message_lines.append("\n⚠️ <b>Errors:</b>")
                for error in result["errors"][:3]:  # Show max 3 errors
                    message_lines.append(f"• {error}")

            message_lines.extend([
                "",
                "💡 <b>Next Steps:</b>",
                "• Manually close positions in Bybit",
                "• Cancel any remaining orders",
                "• Verify account status"
            ])

        else:
            message_lines = [
                "ℹ️ <b>NO BOTS RUNNING</b>",
                "All trading processes are already stopped.",
                "",
                "Status: Ready for manual control"
            ]

        await self.send_message("\n".join(message_lines))

    async def handle_status_command(self):
        """Handle status check command."""
        status = self.get_status_report()
        await self.send_message(status)

    def _init_bybit_client(self):
        """Initialize Bybit client via project settings and bybitwrapper."""
        try:
            # Add project paths to import bybitwrapper
            root = Path(__file__).resolve().parent.parent
            bybit_dir = root / 'BybitUSDT'
            if str(bybit_dir) not in sys.path:
                sys.path.insert(0, str(bybit_dir))

            import bybitwrapper  # type: ignore

            # Load API keys
            settings_path = root / 'settings.json'
            with open(settings_path, 'r') as f:
                settings = json.load(f)

            client = bybitwrapper.bybit(
                test=False,
                api_key=settings['key'],
                api_secret=settings['secret']
            )
            return client
        except Exception as e:
            print(f"[CONTROL] Bybit client init failed: {e}")
            return None

    async def handle_close_all_command(self):
        """Close all open positions across symbols.
        Prefer panic server if available; fallback to direct Bybit reduce-only orders.
        """
        await self.send_message("🚨 <b>CLOSE ALL POSITIONS</b>\n\nAttempting to flatten all positions...")

        # 1) Try Panic Server
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                resp = await session.post('http://127.0.0.1:8787/panic')
                if resp.status == 200:
                    data = await resp.json()
                    await self.send_message("✅ <b>ALL POSITIONS CLOSED via Panic Server</b>\n🔒 Trading disabled.")
                    return
                else:
                    txt = await resp.text()
                    print(f"[CONTROL] Panic server close failed: {resp.status} {txt}")
        except Exception as e:
            print(f"[CONTROL] Panic server not available: {e}")

        # 2) Fallback: direct close via Bybit
        client = self._init_bybit_client()
        if client is None:
            await self.send_message("❌ Could not initialize Bybit client for fallback close.")
            return

        try:
            resp = client._session.get_positions(category="linear")
            if resp.get('retCode') != 0:
                await self.send_message(f"❌ Positions API error: {resp.get('retMsg')}")
                return

            closed = 0
            errors = 0
            for pos in (resp.get('result', {}) or {}).get('list', []) or []:
                size = float(pos.get('size') or 0)
                if size <= 0:
                    continue
                symbol = pos.get('symbol', '')
                side = str(pos.get('side','')).lower()
                # Determine close
                if side == 'buy':
                    close_side = 'Sell'
                    idx = 1
                else:
                    close_side = 'Buy'
                    idx = 2

                try:
                    r = client._session.place_order(
                        category="linear",
                        symbol=symbol,
                        side=close_side,
                        orderType="Market",
                        qty=str(size),
                        timeInForce="IOC",
                        reduceOnly=True,
                        positionIdx=idx
                    )
                    if r.get('retCode') == 0:
                        closed += 1
                    else:
                        errors += 1
                        print(f"[CONTROL] Close fail {symbol}: {r.get('retMsg')}")
                except Exception as e:
                    errors += 1
                    print(f"[CONTROL] Close exception {symbol}: {e}")

            msg = f"✅ <b>CLOSE ALL COMPLETED</b>\n✔️ Closed: {closed}\n❗ Errors: {errors}"
            await self.send_message(msg)
        except Exception as e:
            await self.send_message(f"❌ Exception during close-all: {e}")

    async def listen_for_commands(self):
        """Listen for Telegram commands and respond."""
        last_update_id = 0

        print(f"[TELEGRAM] Listening for commands from chat {self.chat_id}")

        while True:
            try:
                # Get updates
                url = f"{self.api_url}/getUpdates"
                params = {"offset": last_update_id + 1, "limit": 10, "timeout": 30}

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params) as response:
                        if response.status != 200:
                            await asyncio.sleep(5)
                            continue

                        data = await response.json()

                        if not data.get("ok"):
                            await asyncio.sleep(5)
                            continue

                        updates = data.get("result", [])

                        for update in updates:
                            last_update_id = update["update_id"]

                            message = update.get("message", {})
                            chat_id = str(message.get("chat", {}).get("id", ""))
                            text = message.get("text", "").lower().strip()

                            # Only respond to messages from authorized chat
                            if chat_id != self.chat_id:
                                continue

                            # Handle commands
                            if text in ["/kill", "/stop", "/killall", "kill", "stop"]:
                                print(f"[TELEGRAM] Kill command received from chat {chat_id}")
                                await self.handle_kill_command()

                            elif text in ["/status", "/check", "status", "check"]:
                                print(f"[TELEGRAM] Status command received from chat {chat_id}")
                                await self.handle_status_command()

                            elif text in ["/close", "/closeall", "/close_all", "close all", "closeall", "/flatten", "flatten"]:
                                print(f"[TELEGRAM] Close-all command received from chat {chat_id}")
                                await self.handle_close_all_command()

                            elif text in ["/help", "/start", "help"]:
                                help_msg = """🤖 <b>Bot Control Commands</b>

<b>Available Commands:</b>
• /kill or /stop - Kill all trading bots
• /status or /check - Check bot status
• /close - Close all positions (panic fallback)
• /help - Show this help

<b>Emergency Usage:</b>
Send "kill" to immediately stop all bots.

⚠️ After killing bots, manually close positions in Bybit interface."""
                                await self.send_message(help_msg)

            except Exception as e:
                print(f"[TELEGRAM] Error in command listener: {e}")
                await asyncio.sleep(10)

async def main():
    """Main entry point for Telegram control."""
    # Load config
    try:
        with open('config/panic.yaml', 'r') as f:
            import yaml
            config = yaml.safe_load(f)

        bot_token = config['alert']['telegram']['bot_token']
        chat_id = config['alert']['telegram']['chat_id']

        if not bot_token or not chat_id:
            print("ERROR: Telegram bot_token or chat_id not configured")
            return

    except Exception as e:
        print(f"ERROR: Could not load Telegram config: {e}")
        return

    # Start control bot
    control = TelegramBotControl(bot_token, chat_id)

    # Send startup message
    await control.send_message("🤖 <b>Bot Control Active</b>\n\nSend /help for commands.")

    # Listen for commands
    await control.listen_for_commands()

if __name__ == "__main__":
    asyncio.run(main())
