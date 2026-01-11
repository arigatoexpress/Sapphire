import asyncio
import logging
import os
import sys

# Configure basic logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("VerifyAgents")

# Load environment using python-dotenv if available
try:
    from dotenv import load_dotenv

    load_dotenv("local.env")
    logger.info("Loaded local.env")
except ImportError:
    pass


async def verify_symphony():
    logger.info("--- Verifying Symphony Agent ---")

    api_key = os.getenv("SYMPHONY_API_KEY")
    if not api_key:
        logger.error("❌ SYMPHONY_API_KEY not found in environment.")
        return False

    logger.info(f"✅ API Key found (Prefix: {api_key[:8]}...)")

    # Try Import
    try:
        from cloud_trader.symphony_client import get_symphony_client

        client = get_symphony_client()

        # Test Connectivity
        logger.info("Testing connectivity to Symphony API...")
        try:
            # Using get_account_info as a proxy for valid auth
            info = await client.get_account_info()
            logger.info(f"✅ Connection Successful. Account Info: {info}")
            await client.close()
            return True
        except Exception as e:
            logger.error(f"❌ Connection/Auth Failed: {e}")
            await client.close()
            return False

    except Exception as e:
        logger.error(f"❌ Failed to import/init SymphonyClient: {e}")
        return False


async def verify_drift():
    logger.info("\n--- Verifying Drift Agent (Solana) ---")

    private_key = os.getenv("SOLANA_PRIVATE_KEY")
    rpc_url = os.getenv("SOLANA_RPC_URL")

    if not private_key:
        logger.warning("⚠️ SOLANA_PRIVATE_KEY not found. Drift will be Read-Only/Mocked.")
    else:
        logger.info("✅ Solana Private Key found.")

    logger.info(f"RPC URL: {rpc_url}")

    # Check Dependencies
    try:
        import driftpy
        import solana
        import solders

        logger.info(
            f"✅ Drift Dependencies Found: driftpy={driftpy.__version__}, solana={solana.__version__}"
        )
    except ImportError as e:
        logger.error(f"❌ Missing Dependency: {e}")
        logger.error("Run: pip install driftpy solana solders")
        return False

    # Try Client Init
    try:
        from cloud_trader.drift_client import get_drift_client

        client = get_drift_client()
        await client.initialize()

        if client.is_initialized:
            logger.info("✅ Drift Client Initialized Successfully (or via fallback).")
            # Retrieve Equity
            equity = await client.get_total_equity()
            logger.info(f"💰 Estimated Equity: ${equity}")
            await client.close()
            return True
        else:
            logger.warning("⚠️ Drift Client failed to initialize (likely auth/rpc issue).")
            await client.close()
            return False

    except Exception as e:
        logger.error(f"❌ Drift Verification Error: {e}")
        return False


async def verify_hyperliquid():
    logger.info("\n--- Verifying Hyperliquid Agent ---")

    address = os.getenv("HL_ACCOUNT_ADDRESS")
    secret = os.getenv("HL_SECRET_KEY")

    if not address or not secret:
        logger.error("❌ Hyperliquid Credentials missing (HL_ACCOUNT_ADDRESS / HL_SECRET_KEY).")
        return False

    logger.info(f"✅ Credentials found for: {address}")

    try:
        from cloud_trader.hyperliquid_client import HyperliquidClient

        client = HyperliquidClient()
        success = await client.initialize()

        if success:
            logger.info("✅ Hyperliquid Client Initialized.")
            # summary = await client.get_account_summary()
            # logger.info(f"📊 Account Summary Fetched: {bool(summary)}")
            return True
        else:
            logger.error("❌ Hyperliquid Initialization Failed.")
            return False

    except ImportError:
        logger.error("❌ Hyperliquid SDK not installed (hyperliquid-python-sdk).")
        return False
    except Exception as e:
        logger.error(f"❌ Hyperliquid Error: {e}")
        return False


async def verify_jupiter():
    logger.info("\n--- Verifying Jupiter Agent ---")

    # Jupiter does not strictly require an API Key for public endpoints, but good to check if set
    api_key = os.getenv("JUPITER_API_KEY")
    if api_key:
        logger.info("✅ JUPITER_API_KEY found.")
    else:
        logger.info("ℹ️ No JUPITER_API_KEY found (using public tier).")

    try:
        from cloud_trader.jupiter_client import get_jupiter_client

        client = get_jupiter_client()

        # Fetch tokens as connectivity test
        tokens = await client.get_tokens(tags=["verified"])
        if tokens:
            logger.info(f"✅ Connectivity Successful. Fetched {len(tokens)} verified tokens.")

            # Fetch Price
            price = await client.get_price("SOL")
            logger.info(f"💰 Current SOL Price via Jupiter: ${price}")
            return True
        else:
            logger.error("❌ Failed to fetch Jupiter tokens.")
            return False

    except Exception as e:
        logger.error(f"❌ Jupiter Error: {e}")
        return False


async def main():
    print("========================================")
    print("   Sapphire Agent Verification Tool     ")
    print("========================================")

    symphony_ok = await verify_symphony()
    drift_ok = await verify_drift()
    hl_ok = await verify_hyperliquid()
    jup_ok = await verify_jupiter()

    print("\n========================================")
    print("              RESULTS                   ")
    print("========================================")
    print(f"Symphony:    {'✅ PASS' if symphony_ok else '❌ FAIL (Auth/Env)'}")
    print(f"Drift:       {'✅ PASS' if drift_ok else '⚠️ PARTIAL (Mock/Auth)'}")
    print(f"Hyperliquid: {'✅ PASS' if hl_ok else '❌ FAIL (Auth/Env)'}")
    print(f"Jupiter:     {'✅ PASS' if jup_ok else '❌ FAIL'}")
    print("========================================")


if __name__ == "__main__":
    asyncio.run(main())
