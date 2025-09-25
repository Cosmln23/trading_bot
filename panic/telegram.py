#!/usr/bin/env python3
"""
Telegram Alert Integration for Panic Button
Sends formatted alerts for panic events.
"""

import asyncio
import aiohttp
import json
from typing import Dict, Any, List
from datetime import datetime
from .state import PanicReport
from .config import get_config

class TelegramAlerter:
    """Handles Telegram alert sending."""

    def __init__(self, bot_token: str = None, chat_id: str = None):
        config = get_config()
        self.bot_token = bot_token or config.telegram_bot_token
        self.chat_id = chat_id or config.telegram_chat_id
        self.enabled = bool(self.bot_token and self.chat_id)

        if not self.enabled:
            print("[TELEGRAM] Warning: Bot token or chat ID not configured, alerts disabled")

    def _format_panic_start_message(self, timestamp: str) -> str:
        """Format panic start message."""
        return f"""🚨 PANIC BUTTON ACTIVATED
Bot: Bybit-Futures-Bot
Time: {timestamp}
Status: STARTING...
─────────────────
⚠️ Trading: DISABLED
🔄 Executing emergency procedures...
"""

    def _format_panic_success_message(self, report: PanicReport) -> str:
        """Format successful panic completion message."""
        symbols_str = ", ".join(report.symbols_touched) if report.symbols_touched else "None"
        if len(symbols_str) > 50:  # Truncate if too long
            symbols_str = f"{len(report.symbols_touched)} symbols"

        return f"""✅ PANIC BUTTON COMPLETED
Bot: Bybit-Futures-Bot
Time: {report.ended_at}
─────────────────
✅ Trading: DISABLED
✅ Orders canceled: {report.orders_canceled}
✅ Positions closed: {report.positions_closed}
✅ Symbols: {symbols_str}
⏱️ Duration: {report.total_duration_sec:.2f}s
🔒 Status: LOCKED

Phase Timings:
{self._format_phase_timings(report.phase_timings)}

Use /panic/reset to unlock after verification.
"""

    def _format_panic_failure_message(self, report: PanicReport) -> str:
        """Format panic failure message."""
        symbols_str = ", ".join(report.symbols_touched) if report.symbols_touched else "None"

        warning_text = ""
        if report.warnings:
            warning_text = f"⚠️ Warnings: {len(report.warnings)}\n"

        return f"""❌ PANIC BUTTON FAILED
Bot: Bybit-Futures-Bot
Time: {report.ended_at}
─────────────────
❌ Error: {report.error_message}
🔄 Orders canceled: {report.orders_canceled}
🔄 Positions closed: {report.positions_closed}
📊 Symbols touched: {symbols_str}
⏱️ Duration: {report.total_duration_sec:.2f}s
{warning_text}
🚨 MANUAL INTERVENTION REQUIRED

Check positions and orders manually!
"""

    def _format_phase_timings(self, timings: Dict[str, float]) -> str:
        """Format phase timing information."""
        if not timings:
            return "No timing data"

        lines = []
        for phase, duration in timings.items():
            emoji = "✅" if duration < 5.0 else "⚠️" if duration < 10.0 else "❌"
            phase_name = phase.replace('_', ' ').title()
            lines.append(f"{emoji} {phase_name}: {duration:.2f}s")

        return "\n".join(lines)

    async def _send_message(self, message: str):
        """Send message to Telegram."""
        if not self.enabled:
            print(f"[TELEGRAM] Would send: {message[:100]}...")
            return

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

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
                        print("[TELEGRAM] Alert sent successfully")
                    else:
                        result = await response.text()
                        print(f"[TELEGRAM] Error sending alert: {response.status} - {result}")
        except Exception as e:
            print(f"[TELEGRAM] Exception sending alert: {e}")

    def send_panic_start_alert(self, timestamp: str = None):
        """Send panic start alert."""
        if timestamp is None:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        message = self._format_panic_start_message(timestamp)

        # Run async function in sync context
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        loop.run_until_complete(self._send_message(message))

    def send_panic_success_alert(self, report: PanicReport):
        """Send panic success alert."""
        message = self._format_panic_success_message(report)

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        loop.run_until_complete(self._send_message(message))

    def send_panic_failure_alert(self, report: PanicReport):
        """Send panic failure alert."""
        message = self._format_panic_failure_message(report)

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        loop.run_until_complete(self._send_message(message))

    def send_reset_alert(self, success: bool, message: str = ""):
        """Send panic reset alert."""
        if success:
            alert_message = f"""🔓 PANIC RESET SUCCESSFUL
Bot: Bybit-Futures-Bot
Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
─────────────────
✅ Lock removed
✅ Trading: ENABLED
📈 Bot ready for normal operations

{message}
"""
        else:
            alert_message = f"""❌ PANIC RESET FAILED
Bot: Bybit-Futures-Bot
Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
─────────────────
❌ Error: {message}
🔒 Status: Still LOCKED

Manual intervention required.
"""

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        loop.run_until_complete(self._send_message(alert_message))

# Global alerter instance
_alerter = None

def get_alerter() -> TelegramAlerter:
    """Get global Telegram alerter instance."""
    global _alerter
    if _alerter is None:
        _alerter = TelegramAlerter()
    return _alerter