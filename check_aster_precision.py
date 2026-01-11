import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from cloud_trader.exchange import AsterClient


async def main():
    # Use dummy keys as we only need public info
    client = AsterClient(api_key="test", secret_key="test")

    try:
        print("Fetching info for NEARUSDT...")
        info = await client.get_symbol_info("NEARUSDT")
        print("\n=== NEARUSDT ===")
        print(f"Quantity Precision: {info.quantity_precision}")
        print(f"Price Precision: {info.price_precision}")
        print(f"Step Size: {info.step_size}")
        print(f"Tick Size: {info.tick_size}")
        print(f"Min Qty: {info.min_qty}")
        print(f"Raw: {info.raw_data}")

        print("\nFetching info for SOLUSDT...")
        info_sol = await client.get_symbol_info("SOLUSDT")
        print("\n=== SOLUSDT ===")
        print(f"Quantity Precision: {info_sol.quantity_precision}")
        print(f"Step Size: {info_sol.step_size}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
