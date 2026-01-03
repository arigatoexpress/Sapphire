import asyncio
import websockets
import sys
import json

URI = "wss://sapphire-cloud-trader-s77j6bxyra-nn.a.run.app/ws/dashboard"

async def test_no_token():
    print(f"Testing connection to {URI} WITHOUT token...")
    try:
        async with websockets.connect(URI) as websocket:
            print("❌ Connection ACCEPTED (Should have been rejected)")
            msg = await websocket.recv()
            print(f"Received: {msg}")
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"✅ Connection Rejected: {e.status_code}")
    except Exception as e:
        print(f"✅ Connection Failed (Expected): {e}")

async def test_fake_token():
    uri_with_token = f"{URI}?token=invalid-token"
    print(f"Testing connection to {uri_with_token} with FAKE token...")
    try:
        async with websockets.connect(uri_with_token) as websocket:
            print("❌ Connection ACCEPTED (Should have been rejected)")
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"✅ Connection Rejected: {e.status_code}")
    except Exception as e:
        print(f"✅ Connection Failed (Expected): {e}")

async def main():
    await test_no_token()
    await test_fake_token()

if __name__ == "__main__":
    asyncio.run(main())
