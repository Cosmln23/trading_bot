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
            "panic_server": []
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
                    elif 'liquidation' in line:
                        pid = line.split()[1]
                        processes["liquidation"].append(pid)
                    elif 'panic_server' in line:
                        pid = line.split()[1]
                        processes["panic_server"].append(pid)

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

                            elif text in ["/help", "/start", "help"]:
                                help_msg = """🤖 <b>Bot Control Commands</b>

<b>Available Commands:</b>
• /kill or /stop - Kill all trading bots
• /status or /check - Check bot status
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