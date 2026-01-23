#!/usr/bin/env python3
"""Test Symphony API directly to check fund status."""

import asyncio
import os

import httpx

API_KEY = os.getenv("SYMPHONY_API_KEY")
BASE_URL = "https://api.symphony.io"
MIT_AGENT_ID = "ee5bcfda-0919-469c-ac8f-d665a5dd444e"


async def check_fund_status():
    """Check actual fund status from Symphony API."""
    async with httpx.AsyncClient() as client:
        # Try to get agent info
        headers = {"x-api-key": API_KEY}

        print("🔍 Checking Symphony API endpoints...")
        print("\n1. Testing GET /agent/all")
        try:
            response = await client.get(f"{BASE_URL}/agent/all", headers=headers)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   Response: {data}")
        except Exception as e:
            print(f"   Error: {e}")

        print("\n2. Testing GET /agent/{MIT_AGENT_ID}")
        try:
            response = await client.get(f"{BASE_URL}/agent/{MIT_AGENT_ID}", headers=headers)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   Response: {data}")
            else:
                print(f"   Response: {response.text}")
        except Exception as e:
            print(f"   Error: {e}")


if __name__ == "__main__":
    asyncio.run(check_fund_status())
