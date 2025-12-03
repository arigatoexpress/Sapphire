#!/usr/bin/env python3
"""
Startup script to initialize TradingService and start FastAPI server.
This ensures TradingService is initialized before uvicorn starts.
"""

import logging
import sys
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

def main():
    """Main startup function."""
    logger.info("🚀 STARTING SAPPHIRE TRADING SERVICE...")

    # Debug environment variables
    logger.info("🔍 Checking environment variables...")
    key_env_vars = ['ASTER_API_KEY', 'ASTER_SECRET_KEY', 'GCP_PROJECT_ID', 'ENABLE_PAPER_TRADING']
    for var in key_env_vars:
        value = os.getenv(var, 'NOT_SET')
        if var in ['ASTER_API_KEY', 'ASTER_SECRET_KEY']:
            # Don't log actual secret values
            logger.info(f"  {var}: {'SET' if value != 'NOT_SET' else 'NOT_SET'}")
        else:
            logger.info(f"  {var}: {value}")

    try:
        dev_mode = os.getenv("DEV_MODE", "false").lower() == "true"
        
        if dev_mode:
            logger.info("🔥 DEV_MODE ENABLED: Starting with hot-reload...")
            import uvicorn
            uvicorn.run(
                "cloud_trader.api:app",
                host="0.0.0.0",
                port=8080,
                reload=True,
                log_level="debug"
            )
        else:
            # Import the app first (this will trigger module-level initialization)
            logger.info("🔧 IMPORTING AND INITIALIZING TRADING SERVICE...")
            from cloud_trader.api import app
            logger.info("✅ TRADING SERVICE IMPORTED AND INITIALIZED")

            # Now start uvicorn with the initialized app
            logger.info("🌟 STARTING FASTAPI SERVER...")
            import uvicorn

            logger.info("🚀 SERVER STARTING ON 0.0.0.0:8080")
            uvicorn.run(
                app,
                host="0.0.0.0",
                port=8080,
                workers=1,
                loop="uvloop",
                http="httptools",
                access_log=True,
                log_level="info"
            )

    except Exception as e:
        logger.error(f"❌ STARTUP FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
