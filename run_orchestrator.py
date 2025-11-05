#!/usr/bin/env python3
"""Entry point for the centralized wallet risk orchestrator."""

import argparse
import logging

import uvicorn

from risk_orchestrator.main import app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the wallet risk orchestrator service")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(message)s")
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
