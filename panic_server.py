#!/usr/bin/env python3
"""
Panic Button Server Entry Point
Run this to start the HTTP server for panic operations.
"""

import sys
from pathlib import Path

# Add the current directory to Python path
sys.path.append(str(Path(__file__).parent))

from panic.server import start_server

if __name__ == "__main__":
    try:
        start_server()
    except KeyboardInterrupt:
        print("\n[SERVER] Panic button server stopped by user")
    except Exception as e:
        print(f"[SERVER] Fatal error: {e}")
        sys.exit(1)