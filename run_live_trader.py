#!/usr/bin/env python3
"""Executable entrypoint for the lean cloud trader FastAPI service."""

import argparse
import os
import uvicorn

from cloud_trader.api import build_app
from cloud_trader.logging_config import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Cloud Trader service")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int)
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    # Use PORT environment variable if set (for Cloud Run), otherwise use argument
    port = args.port or int(os.getenv("PORT", 8080))
    print(f"Starting server on port {port}")
    print(f"PORT env var: {os.getenv('PORT')}")

    configure_logging(args.log_level)
    print("About to build app...")
    app = build_app()
    print(f"App built successfully: {app}")
    print(f"App routes: {[route.path for route in app.routes]}")
    uvicorn.run(app, host=args.host, port=port, log_level=args.log_level, log_config=None)


if __name__ == "__main__":
    main()
