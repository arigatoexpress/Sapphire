"""Order tag generation and parsing."""

import time
from typing import NamedTuple, Optional

class OrderTag(NamedTuple):
    bot_id: str
    symbol: str
    timestamp: int

def generate_order_tag(bot_id: str, symbol: str) -> str:
    """Generate a unique order tag for tracking."""
    timestamp = int(time.time() * 1000)
    return f"{bot_id}:{symbol}:{timestamp}"

def parse_order_tag(tag: str) -> Optional[OrderTag]:
    """Parse an order tag into its components."""
    parts = tag.split(":")
    if len(parts) != 3:
        return None
    try:
        return OrderTag(bot_id=parts[0], symbol=parts[1], timestamp=int(parts[2]))
    except (ValueError, IndexError):
        return None

