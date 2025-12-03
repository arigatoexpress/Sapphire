
import asyncio
import os
import sys
from eth_account.account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

# Add parent dir to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cloud_trader.exchange import AsterClient
from cloud_trader.credentials import load_credentials

async def close_aster_positions():
    print("\n🟦 CLOSING ASTER POSITIONS...")
    try:
        creds = load_credentials()
        client = AsterClient(credentials=creds)
        
        positions = await client.get_position_risk()
        active = [p for p in positions if float(p.get("positionAmt", 0)) != 0]
        
        if not active:
            print("✅ No active Aster positions.")
            return

        print(f"Found {len(active)} active positions. Closing...")
        for p in active:
            symbol = p["symbol"]
            amt = float(p["positionAmt"])
            side = "SELL" if amt > 0 else "BUY"
            qty = abs(amt)
            
            print(f"   Closing {symbol} ({side} {qty})...")
            res = await client.place_order(
                symbol=symbol,
                side=side,
                order_type="MARKET",
                quantity=qty,
                reduce_only=True
            )
            print(f"   -> {res.get('status', 'UNKNOWN')}")
            
        print("✅ Aster positions closed.")
        await client.close()
    except Exception as e:
        print(f"❌ Error closing Aster positions: {e}")

def close_hyperliquid_positions():
    print("\n🟩 CLOSING HYPERLIQUID POSITIONS...")
    try:
        secret = os.getenv("HL_SECRET_KEY")
        address = os.getenv("HL_ACCOUNT_ADDRESS")
        
        if not secret:
            print("⚠️ No HL_SECRET_KEY found.")
            return

        account = Account.from_key(secret)
        info = Info(constants.MAINNET_API_URL, skip_ws=True)
        exchange = Exchange(account, constants.MAINNET_API_URL, account_address=address)
        
        user_state = info.user_state(account.address)
        positions = user_state.get("assetPositions", [])
        
        active = [p for p in positions if float(p["position"]["szi"]) != 0]
        
        if not active:
            print("✅ No active Hyperliquid positions.")
            return

        print(f"Found {len(active)} active positions. Closing...")
        for p in active:
            coin = p["position"]["coin"]
            print(f"   Closing {coin}...")
            # Close at market
            res = exchange.market_close(coin)
            print(f"   -> {res['status']}")
            
        print("✅ Hyperliquid positions closed.")
    except Exception as e:
        print(f"❌ Error closing Hyperliquid positions: {e}")

async def main():
    print("🚨 INITIATING GLOBAL POSITION RESET 🚨")
    print("=======================================")
    
    # 1. Close Aster
    await close_aster_positions()
    
    # 2. Close Hyperliquid (Synchronous SDK method)
    close_hyperliquid_positions()
    
    print("\n✨ SYSTEM PRISTINE. READY FOR COMPETITION.")

if __name__ == "__main__":
    asyncio.run(main())

