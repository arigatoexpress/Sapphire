#!/usr/bin/env python3
"""
Test script for Aster API connection and capabilities enumeration.
Run this script to verify Aster API connectivity and discover available features.
"""

import asyncio
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cloud_trader.exchange import test_api_connection

if __name__ == "__main__":
    print("🚀 Starting Aster API Connection Test...")
    asyncio.run(test_api_connection())
