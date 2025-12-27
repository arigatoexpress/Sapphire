import asyncio
import json
import time
from typing import Any, Dict, List

import websockets

# Handle websockets exceptions import - version compatibility
try:
    from websockets.exceptions import ConnectionClosedError, InvalidURI
except (ImportError, AttributeError):
    # Fallback for newer websockets versions
    try:
        ConnectionClosedError = websockets.exceptions.ConnectionClosedError
        InvalidURI = websockets.exceptions.InvalidURI
    except AttributeError:
        # If exceptions don't exist, use base Exception
        ConnectionClosedError = Exception
        InvalidURI = Exception

from .exchange import AsterClient


class VPINDataStreamer:
    def __init__(self, output_queue: asyncio.Queue, batch_size: int = 50):
        self.output_queue = output_queue
        self.batch_size = batch_size
        self.base_url = "wss://fstream.asterdex.com"
        self.rest_client = AsterClient()
        self.tick_buffer: Dict[str, List[Dict[str, Any]]] = {}
        self._stop_event = asyncio.Event()

    async def _get_all_symbols(self) -> List[str]:
        try:
            # Add timeout to prevent hanging during startup
            symbols_info = await asyncio.wait_for(self.rest_client.get_all_symbols(), timeout=10.0)
            return [
                info["symbol"]
                for info in symbols_info
                if info.get("symbol") and info.get("status") == "TRADING"
            ]
        except asyncio.TimeoutError:
            print("Timeout fetching symbols for VPIN streamer, using empty list")
            return []
        except Exception as e:
            print(f"Error fetching symbols: {e}")
            return []

    async def _handle_message(self, message: str):
        data = json.loads(message)
        stream_data = data.get("data", {})

        if stream_data.get("e") == "aggTrade":
            symbol = stream_data.get("s")
            if not symbol:
                return

            tick = {
                "price": float(stream_data.get("p", 0.0)),
                "volume": float(stream_data.get("q", 0.0)),
                "timestamp": stream_data.get("T"),
            }

            if symbol not in self.tick_buffer:
                self.tick_buffer[symbol] = []

            self.tick_buffer[symbol].append(tick)

            if len(self.tick_buffer[symbol]) >= self.batch_size:
                batch = self.tick_buffer[symbol]
                self.tick_buffer[symbol] = []
                await self.output_queue.put({"symbol": symbol, "batch": batch})

    async def run(self):
        backoff_time = 5
        while not self._stop_event.is_set():
            try:
                symbols = await self._get_all_symbols()
                if not symbols:
                    print("No symbols found to subscribe. Retrying in 60s.")
                    await asyncio.sleep(60)
                    continue

                streams = [f"{symbol.lower()}@aggTrade" for symbol in symbols]
                # Limit streams to avoid overwhelming the connection, e.g., 100 at a time
                stream_url = f"{self.base_url}/stream?streams={'/'.join(streams[:100])}"

                async with websockets.connect(stream_url) as websocket:
                    print(f"Connected to WebSocket stream for {len(streams[:100])} symbols.")
                    backoff_time = 5  # Reset backoff time on successful connection
                    while not self._stop_event.is_set():
                        message = await websocket.recv()
                        await self._handle_message(message)

            except (ConnectionClosedError, InvalidURI) as e:
                print(f"WebSocket connection error: {e}")
            except Exception as e:
                print(f"An unexpected error occurred in data streamer: {e}")

            if not self._stop_event.is_set():
                print(f"Disconnected. Reconnecting in {backoff_time} seconds...")
                await asyncio.sleep(backoff_time)
                backoff_time = min(backoff_time * 2, 60)  # Exponential backoff

    def stop(self):
        self._stop_event.set()


if __name__ == "__main__":

    async def main():
        q = asyncio.Queue()
        streamer = VPINDataStreamer(output_queue=q)

        async def consumer():
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=1.0)
                    print(f"Consumed: {item['symbol']} batch of {len(item['batch'])} ticks")
                except asyncio.TimeoutError:
                    pass

        streamer_task = asyncio.create_task(streamer.run())
        consumer_task = asyncio.create_task(consumer())

        try:
            await asyncio.sleep(60)  # Run for 60 seconds
        finally:
            streamer.stop()
            await streamer_task
            consumer_task.cancel()

    asyncio.run(main())
