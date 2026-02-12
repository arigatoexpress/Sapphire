import asyncio
import logging
import os
import sys

# Setup Logging to Console
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Mock keys to prevent Pydantic validation errors
os.environ["DATABASE_ENABLED"] = "false"
os.environ["TELEGRAM_BOT_TOKEN"] = "mock_token"
os.environ["TELEGRAM_CHAT_ID"] = "mock_chat_id"
os.environ["ASTER_API_KEY"] = "mock_key"
os.environ["ASTER_SECRET_KEY"] = "mock_secret"

# --- MOCK HEAVY DEPENDENCIES ---
# Bypass Numba/Pandas-TA crashes on ARM Mac for simple logic verification
from unittest.mock import MagicMock

sys.modules["pandas_ta"] = MagicMock()
sys.modules["numba"] = MagicMock()
sys.modules["numba.core"] = MagicMock()
sys.modules["numba.core.config"] = MagicMock()
sys.modules["numba.core.config"] = MagicMock()
sys.modules["llvmlite"] = MagicMock()
sys.modules["llvmlite.binding"] = MagicMock()

# Bypass Crypto/Eth-Account architecture mismatch
sys.modules["eth_account"] = MagicMock()
sys.modules["eth_account.account"] = MagicMock()
sys.modules["eth_account.signers"] = MagicMock()
sys.modules["eth_account.signers.local"] = MagicMock()
sys.modules["eth_keyfile"] = MagicMock()
sys.modules["Crypto"] = MagicMock()
sys.modules["Crypto.Cipher"] = MagicMock()
sys.modules["Crypto.Util"] = MagicMock()

# Bypass Lighter's deep eth_account imports
sys.modules["lighter"] = MagicMock()
sys.modules["lighter.exchange"] = MagicMock()
sys.modules["lighter.info"] = MagicMock()
sys.modules["lighter.utils"] = MagicMock()
sys.modules["lighter.utils.signing"] = MagicMock()

from cloud_trader.trading_service import TradingService


async def verify_monitoring():
    logger.info("🧪 STATING MONITORING VERIFICATION...")

    # Initialize Service
    service = TradingService()

    # Mock Telegram to intercept messages instead of failing
    class MockTelegram:
        async def send_message(self, msg):
            logger.info(f"📨 [TELEGRAM MOCK] Sent: {msg.replace(chr(10), ' ')}")

        async def start(self):
            logger.info("🤖 [TELEGRAM MOCK] Bot Started")

    service._telegram = MockTelegram()

    # Start Service (Should check for startup notification)
    logger.info("🚀 Calling service.start()...")
    await service.start()

    # Wait to see "Scanning market..." logs (from heartbeat or loop)
    logger.info("⏳ Waiting 5 seconds to capture 'Scanning market...' logs...")
    await asyncio.sleep(5)

    # Verify Heartbeat (manually trigger if loop didn't catch it)
    logger.info("💓 Triggering manual heartbeat check...")
    await service._send_heartbeat()

    logger.info("✅ VERIFICATION COMPLETE")


if __name__ == "__main__":
    asyncio.run(verify_monitoring())
