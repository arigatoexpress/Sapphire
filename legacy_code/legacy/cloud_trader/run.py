import logging
import os

import uvicorn

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        port = int(os.getenv("PORT", 8080))
        logger.info(f"🚀 Starting Cloud Trader on port {port}...")

        # Start Uvicorn
        # This will trigger api.lifespan which starts the TradingService
        uvicorn.run(
            "cloud_trader.api:app",
            host="0.0.0.0",
            port=port,
            log_level="info",
            proxy_headers=True,
            forwarded_allow_ips="*",
            ws="wsproto",  # Use wsproto instead of websockets for WebSocket handling
        )
    except KeyboardInterrupt:
        logger.info("👋 User stopped server.")
    except Exception as e:
        logger.critical(f"💥 Fatal error: {e}", exc_info=True)
