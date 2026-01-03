
import os
import sys
from unittest.mock import MagicMock

# --- MOCKS FOR ARM64/DEPENDENCY ISSUES ---
# 1. Numba / Pandas-TA
sys.modules["pandas_ta"] = MagicMock()
sys.modules["numba"] = MagicMock()
sys.modules["numba.core"] = MagicMock()
sys.modules["numba.core.config"] = MagicMock()
sys.modules["llvmlite"] = MagicMock()
sys.modules["llvmlite.binding"] = MagicMock()

# 2. PyCryptodome / Eth-Account
sys.modules["eth_account"] = MagicMock()
sys.modules["eth_account.account"] = MagicMock()
sys.modules["eth_account.signers"] = MagicMock()
sys.modules["eth_account.signers.local"] = MagicMock()
sys.modules["eth_keyfile"] = MagicMock()
sys.modules["Crypto"] = MagicMock()
sys.modules["Crypto.Cipher"] = MagicMock()
sys.modules["Crypto.Util"] = MagicMock()

# 3. Hyperliquid
sys.modules["hyperliquid"] = MagicMock()
sys.modules["hyperliquid.exchange"] = MagicMock()
sys.modules["hyperliquid.info"] = MagicMock()
sys.modules["hyperliquid.utils"] = MagicMock()
sys.modules["hyperliquid.utils.signing"] = MagicMock()

# --- ENV VARS ---
os.environ["DATABASE_ENABLED"] = "false" # Use in-memory or mocks where possible
os.environ["TELEGRAM_BOT_TOKEN"] = "mock_token"
os.environ["TELEGRAM_CHAT_ID"] = "mock_chat_id"
os.environ["ASTER_API_KEY"] = "mock_key"
os.environ["ASTER_SECRET_KEY"] = "mock_secret"
os.environ["FIREBASE_CREDENTIALS_JSON"] = "{}" # Minimal invalid JSON to prevent crash if not used immediately

import uvicorn
from cloud_trader.api import app

if __name__ == "__main__":
    print("🚀 Starting MOCKED Local Backend on port 8080...")
    uvicorn.run(app, host="0.0.0.0", port=8080)
