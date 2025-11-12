import time
import uuid


def now_ms() -> int:
    return int(time.time() * 1000)


def generate_order_id(bot_id: str, symbol: str) -> str:
    timestamp = now_ms()
    suffix = uuid.uuid4().hex[:6]
    return f"{bot_id}_{symbol}_{timestamp}_{suffix}"
