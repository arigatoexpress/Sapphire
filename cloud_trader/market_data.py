from typing import Any, Dict

from .definitions import SYMBOL_CONFIG, SYMPHONY_SYMBOLS


class MarketDataManager:
    """
    Manages market data, including exchange structure (precision, filters)
    and potentially ticker data.
    """

    def __init__(self, exchange_client):
        self.exchange_client = exchange_client
        self.market_structure: Dict[str, Dict[str, Any]] = {}

    async def fetch_structure(self):
        """Fetch all available symbols and their precision/filters from exchange."""
        try:
            print("🌍 Fetching global market structure (all symbols)...")
            # Assuming get_exchange_info returns raw exchange info dict
            # AsterClient.get_exchange_info() usually returns dict with 'symbols' list
            info = await self.exchange_client.get_exchange_info()

            count = 0
            if info and "symbols" in info:
                for s in info["symbols"]:
                    symbol = s["symbol"]
                    if not symbol.endswith("USDT"):  # Focus on USDT pairs for now
                        continue

                    # Extract precision
                    precision = s.get("quantityPrecision", 0)
                    price_precision = s.get("pricePrecision", 2)

                    # Extract Min Qty and Min Notional if available (filters)
                    min_qty = 0.1  # Default safe fallback
                    step_size = 0.1
                    min_notional = 5.0  # Default safe fallback for USDT
                    for f in s.get("filters", []):
                        if f["filterType"] == "LOT_SIZE":
                            min_qty = float(f.get("minQty", 0))
                            step_size = float(f.get("stepSize", 0))
                        elif f["filterType"] == "MIN_NOTIONAL" or f["filterType"] == "NOTIONAL":
                            min_notional = float(f.get("minNotional", f.get("notional", 5.0)))

                    self.market_structure[symbol] = {
                        "precision": precision,
                        "price_precision": price_precision,
                        "min_qty": min_qty,
                        "step_size": step_size,
                        "min_notional": min_notional,
                    }
                    count += 1

            print(f"✅ Loaded market structure for {count} pairs.")

            # --- INJECT SYMPHONY SYMBOLS ---
            print("🎻 Injecting Symphony (Monad/Base) symbols...")
            injected_count = 0
            for sym in SYMPHONY_SYMBOLS:
                if sym not in self.market_structure:
                    # Use config if available, else defaults
                    config = SYMBOL_CONFIG.get(sym, {})
                    self.market_structure[sym] = {
                        "precision": config.get("precision", 2),
                        "price_precision": 2,  # Default
                        "min_qty": config.get(
                            "qty", 1.0
                        ),  # Use default trade size as min qty logic roughly
                        "step_size": 0.1,  # Loose step size
                    }
                    injected_count += 1

            print(
                f"✅ Injected {injected_count} Symphony symbols. Total: {len(self.market_structure)}"
            )

        except Exception as e:
            print(f"⚠️ Failed to fetch market structure: {e}. Falling back to config.")
