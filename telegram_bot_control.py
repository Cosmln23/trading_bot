#!/usr/bin/env python3
"""
Telegram Bot Control Entry Point
Run this to enable remote bot control via Telegram.
"""

import sys
import asyncio
from pathlib import Path

# Add current directory to Python path
sys.path.append(str(Path(__file__).parent))

from panic.telegram_control import main

if __name__ == "__main__":
    try:
        print("🤖 Starting Telegram Bot Control...")
        print("Send '/kill' or 'kill' to stop all bots remotely")
        print("Send '/status' to check bot status")
        print("Press Ctrl+C to stop this control bot")
        print("-" * 50)

        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Telegram Bot Control stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)