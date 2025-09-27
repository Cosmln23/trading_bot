#!/usr/bin/env python3
"""
Test Manual Position - Verifică dacă profit.py detectează poziții noi
"""
import json
import bybitwrapper

# Load settings
with open('../settings.json', 'r') as f:
    settings = json.load(f)

# Initialize Bybit client
client = bybitwrapper.bybit(test=False, api_key=settings['key'], api_secret=settings['secret'])

def open_test_position():
    """Open a small test position on ETHUSDT"""
    try:
        print("[TEST] Opening small ETHUSDT position...")

        # Place small market buy order (0.01 ETH ≈ $24-30)
        order = client.LinearOrder.LinearOrder_new(
            side="Buy",
            symbol="ETHUSDT",
            order_type="Market",
            qty="0.01",
            time_in_force="IOC"
        ).result()

        print(f"[TEST] Order placed: {order}")

        if order[0].get('ret_msg') == 'OK':
            print("✅ [TEST] Position opened successfully!")
            print("🔍 Now check profit.py logs to see if it detects this position...")
            print("📋 Expected: profit.py should show 'Position found for ETH entry price of X.XX'")
            return True
        else:
            print(f"❌ [TEST] Order failed: {order}")
            return False

    except Exception as e:
        print(f"❌ [TEST] Error opening position: {e}")
        return False

def check_existing_positions():
    """Check current positions"""
    try:
        positions = client.LinearPositions.LinearPositions_myPosition(symbol="ETHUSDT").result()
        if positions[0]['ret_msg'] == 'OK':
            for position in positions[0]['result']:
                if float(position['entry_price']) > 0:
                    print(f"📍 [TEST] Found existing position: {position['symbol']} {position['side']} size={position['size']} entry={position['entry_price']}")
                    return position
        print("📍 [TEST] No existing ETHUSDT position found")
        return None
    except Exception as e:
        print(f"❌ [TEST] Error checking positions: {e}")
        return None

if __name__ == "__main__":
    print("=== TEST POSITION SCRIPT ===")
    print("This will open a small ETHUSDT position to test profit.py detection")
    print()

    # Check existing positions first
    existing = check_existing_positions()

    if existing:
        print("⚠️  [TEST] ETHUSDT position already exists. Test not needed.")
        print("🔍 Check profit.py logs - it should already be managing this position")
    else:
        # Open test position
        success = open_test_position()

        if success:
            print()
            print("✅ [TEST] Position created! Now monitor profit.py for 30-60 seconds.")
            print("🔍 Look for: 'Position found for ETH entry price of X.XX'")
            print("🔍 Then: '[TP/SL] calc start symbol=ETH side=Buy size=0.01'")
            print()
            print("📌 Remember to manually close this test position later!")
        else:
            print("❌ [TEST] Failed to create test position")